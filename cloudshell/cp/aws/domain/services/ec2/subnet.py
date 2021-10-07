from typing import TYPE_CHECKING, List, Optional

from cloudshell.cp.aws.domain.services.ec2.tags import TagService
from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Subnet, Vpc


def get_subnet_reservation_name(subnet_alias: str, reservation_id: str) -> str:
    return f"{subnet_alias} Reservation: {reservation_id}"


class SubnetService:
    def __init__(self, tag_service: TagService, subnet_waiter: SubnetWaiter):
        self.tag_service = tag_service
        self.subnet_waiter = subnet_waiter

    def create_subnet_nowait(
        self,
        vpc,
        cidr,
        availability_zone,
    ):
        return vpc.create_subnet(CidrBlock=cidr, AvailabilityZone=availability_zone)

    def get_vpc_subnets(self, vpc: "Vpc") -> List["Subnet"]:
        subnets = list(vpc.subnets.all())
        if not subnets:
            raise ValueError(f"The given VPC({vpc.id}) has no subnets")
        return subnets

    def get_first_subnet_from_vpc(self, vpc: "Vpc") -> "Subnet":
        subnets = self.get_vpc_subnets(vpc)
        return subnets[0]

    def get_subnet_by_reservation_id(self, vpc: "Vpc", rid: str) -> "Subnet":
        reservation_tag = self.tag_service.get_reservation_tag(rid)
        for subnet in self.get_vpc_subnets(vpc):
            if reservation_tag in subnet.tags:
                return subnet
        raise Exception(f"There isn't the subnet for the reservation '{rid}'")

    def get_first_or_none_subnet_from_vpc(self, vpc, cidr=None) -> Optional["Subnet"]:
        subnets = list(vpc.subnets.all())
        if cidr:
            subnets = [s for s in subnets if s.cidr_block == cidr]
        if not subnets:
            return None
        return subnets[0]

    def delete_subnet(self, subnet):
        subnet.delete()
        return True
