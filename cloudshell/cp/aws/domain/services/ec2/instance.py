from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource
    from mypy_boto3_ec2.service_resource import Instance, Vpc

    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.services.ec2.network_interface import (
        NetworkInterfaceService,
    )
    from cloudshell.cp.aws.domain.services.ec2.tags import TagService
    from cloudshell.cp.aws.domain.services.waiters.instance import InstanceWaiter
    from cloudshell.cp.aws.models.ami_deployment_model import AMIDeploymentModel


class InstanceService:
    def __init__(
        self,
        tags_creator_service: "TagService",
        instance_waiter: "InstanceWaiter",
        network_interface_service: "NetworkInterfaceService",
    ):
        self.instance_waiter = instance_waiter
        self.tags_creator_service = tags_creator_service
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

    def set_tags(self, instance, name, reservation, custom_tags):
        # todo create the name with a name generator
        new_name = name + " " + instance.instance_id
        default_tags = self.tags_creator_service.get_default_tags(
            new_name, reservation
        ) + self.tags_creator_service.get_custom_tags(custom_tags)

        self.tags_creator_service.set_ec2_resource_tags(instance, default_tags)

        for volume in instance.volumes.all():
            self.tags_creator_service.set_ec2_resource_tags(volume, default_tags)

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

    def get_instances_for_reservation(
        self, vpc: "Vpc", reservation_id: str
    ) -> List["Instance"]:
        tag = self.tags_creator_service.get_reservation_tag(reservation_id)
        return list(filter(lambda i: tag in i.tags, self.get_all_instances(vpc)))
