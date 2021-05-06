from logging import Logger
from typing import List

from retrying import retry

from cloudshell.cp.core.models import ConnectSubnet, ConnectToSubnetParams

from cloudshell.cp.aws.common.retry_helper import retry_if_client_error
from cloudshell.cp.aws.domain.common.list_helper import first_or_default
from cloudshell.cp.aws.models.deploy_aws_ec2_ami_instance_resource_model import (
    DeployAWSEc2AMIInstanceResourceModel,
)
from cloudshell.cp.aws.models.network_actions_models import DeployNetworkingResultModel


class ElasticIpService:
    def __init__(self):
        pass

    def set_elastic_ips(
        self,
        ec2_session,
        ec2_client,
        instance,
        ami_deployment_model: DeployAWSEc2AMIInstanceResourceModel,
        network_actions: List[ConnectSubnet],
        network_config_results: List[DeployNetworkingResultModel],
        logger: Logger,
    ):
        if not ami_deployment_model.allocate_elastic_ip:
            return

        if self._is_single_subnet_mode(network_actions):
            elastic_ip = self.allocate_elastic_address(ec2_client=ec2_client)
            # set elastic ip data in deploy result
            network_config_results[0].public_ip = elastic_ip
            network_config_results[0].is_elastic_ip = True
            self.associate_elastic_ip_to_instance(
                ec2_session=ec2_session, instance=instance, elastic_ip=elastic_ip
            )
            logger.info(
                f"Single subnet mode detected. Allocated & associated elastic ip "
                f"{elastic_ip} to instance {instance.id}"
            )
            return

        # allocate elastic ip for each interface inside a public subnet
        for action in network_actions:
            if (
                not isinstance(action.actionParams, ConnectToSubnetParams)
                or not action.actionParams.isPublic
            ):
                continue

            # find network interface using device index
            action_result = first_or_default(
                network_config_results, lambda x: x.action_id == action.actionId
            )
            interface = next(
                filter(
                    lambda x: x["Attachment"]["DeviceIndex"]
                    == action_result.device_index,
                    instance.network_interfaces_attribute,
                )
            )

            # allocate and assign elastic ip
            elastic_ip = self.allocate_elastic_address(ec2_client=ec2_client)
            action_result.public_ip = elastic_ip  # set elastic ip data in deploy result
            action_result.is_elastic_ip = True
            interface_id = interface["NetworkInterfaceId"]
            self.associate_elastic_ip_to_network_interface(
                ec2_session=ec2_session,
                interface_id=interface_id,
                elastic_ip=elastic_ip,
            )
            logger.info(
                f"Multi-subnet mode detected. Allocated & associated elastic ip "
                f"{elastic_ip} to interface {interface_id}"
            )

    def _is_single_subnet_mode(self, network_actions):
        # todo move code to networking service
        return network_actions is None or (
            isinstance(network_actions, list) and len(network_actions) <= 1
        )

    @retry(
        retry_on_exception=retry_if_client_error,
        stop_max_attempt_number=30,
        wait_fixed=1000,
    )
    def associate_elastic_ip_to_instance(self, ec2_session, instance, elastic_ip: str):
        """Assign an elastic ip to the primary interface.

        and primary private ip of the given instance
        """
        response = list(ec2_session.vpc_addresses.filter(PublicIps=[elastic_ip]))
        if len(response) == 1:
            vpc_address = response[0]
            vpc_address.associate(InstanceId=instance.id, AllowReassociation=False)
        else:
            raise ValueError(f"Failed to find elastic ip {elastic_ip} allocation id")

    @retry(
        retry_on_exception=retry_if_client_error,
        stop_max_attempt_number=30,
        wait_fixed=1000,
    )
    def associate_elastic_ip_to_network_interface(
        self, ec2_session, interface_id: str, elastic_ip: str
    ):
        """Assign an elastic ip to a specific network interface."""
        response = list(ec2_session.vpc_addresses.filter(PublicIps=[elastic_ip]))
        if len(response) == 1:
            vpc_address = response[0]
            vpc_address.associate(
                NetworkInterfaceId=interface_id, AllowReassociation=False
            )
        else:
            raise ValueError(f"Failed to find elastic ip {elastic_ip} allocation id")

    def allocate_elastic_address(self, ec2_client) -> str:
        """Return allocated elastic ip."""
        result = ec2_client.allocate_address(Domain="vpc")
        return result["PublicIp"]

    @retry(
        retry_on_exception=retry_if_client_error,
        stop_max_attempt_number=30,
        wait_fixed=1000,
    )
    def find_and_release_elastic_address(self, ec2_session, elastic_ip):
        response = list(ec2_session.vpc_addresses.filter(PublicIps=[elastic_ip]))
        if len(response) == 1:
            vpc_address = response[0]
            self.release_elastic_address(vpc_address)
        else:
            raise ValueError(f"Failed to find elastic ip {elastic_ip}")

    def release_elastic_address(self, vpc_address):
        vpc_address.release()
