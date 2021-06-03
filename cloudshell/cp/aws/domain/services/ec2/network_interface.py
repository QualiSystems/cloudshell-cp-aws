from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Vpc

    from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode


class NetworkInterfaceService:
    def __init__(self, subnet_service: "SubnetService"):
        self.subnet_service = subnet_service

    def get_network_interface_for_single_subnet_mode(
        self,
        add_public_ip: bool,
        security_group_ids: List[str],
        vpc: "Vpc",
        reservation_id: str,
        vpc_mode: "VpcMode",
        private_ip: Optional[str] = None,
    ):
        if vpc_mode is VpcMode.SHARED:
            subnet = self.subnet_service.get_subnet_by_reservation_id(
                vpc, reservation_id
            )
        else:
            subnet = self.subnet_service.get_first_subnet_from_vpc(vpc)
        return self.build_network_interface_dto(
            subnet_id=subnet.subnet_id,
            device_index=0,
            groups=security_group_ids,
            public_ip=add_public_ip,
            private_ip=private_ip,
        )

    def build_network_interface_dto(
        self, subnet_id, device_index, groups, public_ip=None, private_ip=None
    ):
        net_if = {"SubnetId": subnet_id, "DeviceIndex": device_index, "Groups": groups}

        if public_ip:
            net_if["AssociatePublicIpAddress"] = public_ip

        if private_ip:
            net_if["PrivateIpAddress"] = private_ip

        return net_if
