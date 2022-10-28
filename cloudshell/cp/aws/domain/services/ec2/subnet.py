from typing import TYPE_CHECKING, List, Optional

from cloudshell.cp.aws.domain.handlers.ec2 import TagsHandler
from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Subnet, Vpc  # noqa: I900


def get_subnet_reservation_name(subnet_alias: str, reservation_id: str) -> str:
    return f"{subnet_alias} Reservation: {reservation_id}"


class SubnetService:
    def __init__(self, subnet_waiter: SubnetWaiter):
        self.subnet_waiter = subnet_waiter

    @staticmethod
    def create_subnet_nowait(
        vpc: "Vpc",
        cidr: str,
        availability_zone: str,
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
        for subnet in self.get_vpc_subnets(vpc):
            if TagsHandler.from_tags_list(subnet.tags).get_reservation_id() == rid:
                return subnet
        raise Exception(f"There isn't the subnet for the reservation '{rid}'")

    @staticmethod
    def get_first_or_none_subnet_from_vpc(
        vpc: "Vpc", cidr: Optional[str] = None
    ) -> Optional["Subnet"]:
        subnets = list(vpc.subnets.all())
        if cidr:
            subnets = [s for s in subnets if s.cidr_block == cidr]
        if not subnets:
            return None
        return subnets[0]

    def delete_subnet(self, subnet):
        subnet.delete()
        return True
