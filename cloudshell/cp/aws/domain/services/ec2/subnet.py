from cloudshell.cp.aws.domain.services.ec2.tags import TagService
from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter

SUBNET_NAME = "VPC Name: {}"


class SubnetService:
    def __init__(self, tag_service: TagService, subnet_waiter: SubnetWaiter):
        self.tag_service = tag_service
        self.subnet_waiter = subnet_waiter

    def create_subnet_for_vpc(
        self, vpc, cidr, subnet_name, availability_zone, reservation
    ):
        """Will create a subnet for the given vpc.

        :param reservation: reservation model
        :type reservation: cloudshell.cp.aws.models.reservation_model.ReservationModel
        :param vpc: VPC instanve
        :param str cidr: CIDR
        :param str subnet_name:
        :param str availability_zone:
        :return:
        """
        subnet = vpc.create_subnet(CidrBlock=cidr, AvailabilityZone=availability_zone)
        self.subnet_waiter.wait(subnet, self.subnet_waiter.AVAILABLE)

        tags = self.tag_service.get_default_tags(subnet_name, reservation)
        self.tag_service.set_ec2_resource_tags(subnet, tags)
        return subnet

    def create_subnet_nowait(
        self,
        vpc,
        cidr,
        availability_zone,
    ):
        return vpc.create_subnet(CidrBlock=cidr, AvailabilityZone=availability_zone)

    def get_vpc_subnets(self, vpc):
        subnets = list(vpc.subnets.all())
        if not subnets:
            raise ValueError(f"The given VPC({vpc.id}) has no subnets")
        return subnets

    @staticmethod
    def get_first_subnet_from_vpc(vpc):
        subnets = list(vpc.subnets.all())
        if not subnets:
            raise ValueError(f"The given VPC({vpc.id}) has no subnet")
        return subnets[0]

    def get_first_or_none_subnet_from_vpc(self, vpc, cidr=None):
        subnets = list(vpc.subnets.all())
        if cidr:
            subnets = [s for s in subnets if s.cidr_block == cidr]
        if not subnets:
            return None
        return subnets[0]

    @staticmethod
    def _get_subnet_name(name):
        return SUBNET_NAME.format(name)

    def delete_subnet(self, subnet):
        subnet.delete()
        return True

    def set_subnet_route_table(self, ec2_client, subnet_id, route_table_id):
        ec2_client.associate_route_table(
            RouteTableId=route_table_id, SubnetId=subnet_id
        )
