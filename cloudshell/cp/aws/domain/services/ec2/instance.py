from typing import TYPE_CHECKING, List, Optional

from cloudshell.cp.aws.domain.handlers.ec2 import TagsHandler
from cloudshell.cp.aws.models.reservation_model import ReservationModel

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource  # noqa: I900
    from mypy_boto3_ec2.service_resource import Instance, Vpc  # noqa: I900

    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.services.ec2.network_interface import (
        NetworkInterfaceService,
    )
    from cloudshell.cp.aws.domain.services.waiters.instance import InstanceWaiter
    from cloudshell.cp.aws.models.ami_deployment_model import AMIDeploymentModel


class InstanceService:
    def __init__(
        self,
        instance_waiter: "InstanceWaiter",
        network_interface_service: "NetworkInterfaceService",
    ):
        self.instance_waiter = instance_waiter
        self.network_interface_service = network_interface_service

    def create_instance(
        self,
        ec2_session: "EC2ServiceResource",
        ami_deployment_info: "AMIDeploymentModel",
    ) -> "Instance":
        instance = ec2_session.create_instances(
            ImageId=ami_deployment_info.aws_ami_id,
            MinCount=ami_deployment_info.min_count,
            MaxCount=ami_deployment_info.max_count,
            InstanceType=ami_deployment_info.instance_type,
            KeyName=ami_deployment_info.aws_key,
            BlockDeviceMappings=ami_deployment_info.block_device_mappings,
            NetworkInterfaces=ami_deployment_info.network_interfaces,
            IamInstanceProfile=ami_deployment_info.iam_role,
            UserData=ami_deployment_info.user_data,
        )[0]
        return instance

    def disable_source_dest_check(self, ec2_client: "EC2Client", instance: "Instance"):
        for nic in instance.network_interfaces_attribute:
            self.network_interface_service.disable_source_dest_check(
                ec2_client, nic["NetworkInterfaceId"]
            )

    def wait_for_instance_to_run_in_aws(
        self,
        ec2_client: "EC2Client",
        instance: "Instance",
        wait_for_status_check: bool,
        status_check_timeout: int,
        cancellation_context: "CancellationContext",
        logger: "Logger",
    ):
        self.instance_waiter.wait(
            instance=instance,
            state=self.instance_waiter.RUNNING,
            cancellation_context=cancellation_context,
        )

        if wait_for_status_check:
            self.instance_waiter.wait_status_ok(
                ec2_client,
                instance,
                logger,
                status_check_timeout,
                cancellation_context,
            )
            logger.info("Instance created with status: instance_status_ok.")

    def terminate_instance(self, instance):
        return self.terminate_instances([instance])[0]

    def terminate_instances(self, instances):
        if len(instances) == 0:
            return

        for instance in instances:
            instance.terminate()
        return self.instance_waiter.multi_wait(
            instances, self.instance_waiter.TERMINATED
        )

    def set_tags(
        self,
        instance: "Instance",
        name: str,
        reservation: "ReservationModel",
        custom_tags: dict,
    ):
        # todo create the name with a name generator
        new_name = f"{name} {instance.instance_id}"
        tags = TagsHandler.create_default_tags(new_name, reservation)
        tags.update_tags(custom_tags)
        tags.add_tags_to_obj(instance)

        for volume in instance.volumes.all():
            tags.add_tags_to_obj(volume)

    @staticmethod
    def get_instance_by_id(ec2_session, id):  # noqa: A002
        return ec2_session.Instance(id=id)

    @staticmethod
    def get_active_instance_by_id(ec2_session, instance_id):
        instance = InstanceService.get_instance_by_id(ec2_session, instance_id)
        if (
            not hasattr(instance, "state")
            or instance.state["Name"].lower() == "terminated"
        ):
            raise Exception("Can't perform action. EC2 instance was terminated/removed")

        return instance

    @staticmethod
    def get_all_instances(vpc: "Vpc") -> List["Instance"]:
        return list(vpc.instances.all())

    @staticmethod
    def get_reservation_id(instance: "Instance") -> Optional[str]:
        return TagsHandler.from_tags_list(instance.tags).get_reservation_id()

    def get_instances_for_reservation(
        self, vpc: "Vpc", reservation_id: str
    ) -> List["Instance"]:
        instances = filter(
            lambda i: self.get_reservation_id(i) == reservation_id,
            self.get_all_instances(vpc),
        )
        return list(instances)
