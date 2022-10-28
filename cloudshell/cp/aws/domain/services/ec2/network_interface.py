from typing import TYPE_CHECKING, List, Optional

import retrying

from cloudshell.cp.aws.common.retry_helper import retry_if_client_error
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource  # noqa: I900
    from mypy_boto3_ec2.service_resource import SecurityGroup, Vpc  # noqa: I900

    from cloudshell.cp.aws.domain.services.ec2.security_group import (
        SecurityGroupService,
    )
    from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService
    from cloudshell.cp.aws.models.reservation_model import ReservationModel


class NetworkInterfaceService:
    def __init__(
        self,
        subnet_service: "SubnetService",
        security_group_service: "SecurityGroupService",
    ):
        self.subnet_service = subnet_service
        self.security_group_service = security_group_service

    def get_network_interface_for_single_subnet_mode(
        self,
        add_public_ip: bool,
        security_group_ids: List[str],
        vpc: "Vpc",
        ec2_session: "EC2ServiceResource",
        reservation: "ReservationModel",
        vpc_mode: "VpcMode",
        private_ip: Optional[str] = None,
    ):
        if vpc_mode in (VpcMode.SHARED, VpcMode.SINGLE):
            subnet = self.subnet_service.get_subnet_by_reservation_id(
                vpc, reservation.reservation_id
            )
        else:
            subnet = self.subnet_service.get_first_subnet_from_vpc(vpc)
        return self.build_network_interface_dto(
            subnet_id=subnet.subnet_id,
            device_index=0,
            groups=security_group_ids,
            vpc=vpc,
            vpc_mode=vpc_mode,
            public_ip=add_public_ip,
            private_ip=private_ip,
        )

    def _get_subnet_sg(
        self,
        subnet_id: str,
        vpc: "Vpc",
    ) -> "SecurityGroup":
        subnet_sg_name = self.security_group_service.subnet_sg_name(subnet_id)
        subnet_sg = self.security_group_service.get_security_group_by_name(
            vpc, subnet_sg_name
        )
        if not subnet_sg:
            raise ValueError(
                f"{subnet_sg_name} should be created when creating the "
                f"Subnet {subnet_id}"
            )
        return subnet_sg

    def build_network_interface_dto(
        self,
        subnet_id,
        device_index,
        groups: List[str],
        vpc: "Vpc",
        vpc_mode: "VpcMode",
        public_ip=None,
        private_ip=None,
    ):
        if vpc_mode in (VpcMode.SHARED, VpcMode.SINGLE):
            # add SecurityGroup for the subnet
            subnet_sg = self._get_subnet_sg(subnet_id, vpc)
            groups.append(subnet_sg.id)

        net_if = {"SubnetId": subnet_id, "DeviceIndex": device_index, "Groups": groups}

        if public_ip:
            net_if["AssociatePublicIpAddress"] = public_ip

        if private_ip:
            net_if["PrivateIpAddress"] = private_ip

        return net_if

    @retrying.retry(
        retry_on_exception=retry_if_client_error,
        stop_max_attempt_number=30,
        wait_fixed=1000,
    )
    def disable_source_dest_check(self, ec2_client: "EC2Client", nic_id: str):
        ec2_client.modify_network_interface_attribute(
            NetworkInterfaceId=nic_id,
            SourceDestCheck={"Value": False},
        )
