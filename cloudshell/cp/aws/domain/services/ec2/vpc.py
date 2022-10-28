from typing import TYPE_CHECKING, Iterable, List, Optional

from botocore.exceptions import ClientError
from retrying import retry

from cloudshell.cp.aws.domain.conncetivity.operations.traffic_mirror_cleaner import (
    TrafficMirrorCleaner,
)
from cloudshell.cp.aws.domain.handlers.ec2 import (
    RouteTableHandler,
    RouteTableNotFound,
    TagsHandler,
)

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2ServiceResource  # noqa: I900
    from mypy_boto3_ec2.service_resource import (  # noqa: I900
        InternetGateway,
        Subnet,
        Vpc,
    )

    from cloudshell.cp.aws.models.reservation_model import ReservationModel


class VpcError(Exception):
    ...


class FailedToDeleteRouteTables(VpcError):
    def __init__(self, errors: List[Exception]):
        super().__init__(f"Failed to remove route tables. Errors: {errors}")


class VpcNotFound(VpcError):
    ...


class VpcNotFoundById(VpcNotFound):
    def __init__(self, vpc_id: str):
        super().__init__(f"Failed to find VPC with id '{vpc_id}'")


class VpcNotFoundByReservationId(VpcNotFound):
    def __init__(self, reservation_id: str):
        super().__init__(f"Failed to find VPC with reservation id {reservation_id}")


class VPCService:
    VPC_RESERVATION = "VPC Reservation: {0}"

    def __init__(
        self,
        subnet_service,
        instance_service,
        vpc_waiter,
        sg_service,
        traffic_mirror_service,
    ):
        """# noqa
        :param subnet_service: Subnet Service
        :type subnet_service: cloudshell.cp.aws.domain.services.ec2.subnet.SubnetService
        :param instance_service: Instance Service
        :type instance_service: cloudshell.cp.aws.domain.services.ec2.instance.InstanceService
        :param vpc_waiter: Vpc Waiter
        :type vpc_waiter: cloudshell.cp.aws.domain.services.waiters.vpc.VPCWaiter
        :param sg_service: Security Group Service
        :type sg_service: cloudshell.cp.aws.domain.services.ec2.security_group.SecurityGroupService
        """
        self.subnet_service = subnet_service
        self.instance_service = instance_service
        self.vpc_waiter = vpc_waiter
        self.sg_service = sg_service
        self.traffic_mirror_service = traffic_mirror_service

    def create_vpc_for_reservation(self, ec2_session, reservation, cidr):
        """# noqa
        Will create a vpc for reservation and will save it in a folder in the s3 bucket
        :param ec2_session: Ec2 Session
        :param reservation: reservation model
        :type reservation: cloudshell.cp.aws.models.reservation_model.ReservationModel
        :param cidr: The CIDR block
        :type cidr: str
        :return: vpc
        """
        vpc = ec2_session.create_vpc(CidrBlock=cidr)

        self.vpc_waiter.wait(vpc=vpc, state=self.vpc_waiter.AVAILABLE)

        vpc_name = self.VPC_RESERVATION.format(reservation.reservation_id)
        self._set_tags(vpc_name=vpc_name, reservation=reservation, vpc=vpc)

        return vpc

    def find_vpc_for_reservation(
        self, ec2_session: "EC2ServiceResource", reservation_id: str
    ) -> Optional["Vpc"]:
        filters = [
            {
                "Name": "tag:Name",
                "Values": [self.VPC_RESERVATION.format(reservation_id)],
            }
        ]

        vpcs = list(ec2_session.vpcs.filter(Filters=filters))

        if not vpcs:
            return None

        if len(vpcs) > 1:
            raise ValueError("Too many vpcs for the reservation")

        return vpcs[0]

    def get_vpc_for_reservation(
        self, ec2_session: "EC2ServiceResource", reservation_id: str
    ) -> "Vpc":
        vpc = self.find_vpc_for_reservation(ec2_session, reservation_id)
        if not vpc:
            raise VpcNotFoundByReservationId(reservation_id)
        return vpc

    @staticmethod
    def get_vpc_by_id(ec2_session: "EC2ServiceResource", vpc_id: str) -> "Vpc":
        vpc = ec2_session.Vpc(vpc_id)
        try:
            vpc.load()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "InvalidVpcID.NotFound":
                raise VpcNotFoundById(vpc_id)
            else:
                raise
        return vpc

    @staticmethod
    def _set_tags(vpc_name: str, reservation: "ReservationModel", vpc: "Vpc"):
        tags = TagsHandler.create_default_tags(vpc_name, reservation)
        tags.add_tags_to_obj(vpc)

    def remove_all_internet_gateways(self, vpc: "Vpc"):
        """Removes all internet gateways from a VPC."""
        for igw in self.get_all_igws(vpc):
            igw.detach_from_vpc(VpcId=vpc.id)
            igw.delete()

    @staticmethod
    def get_all_igws(vpc: "Vpc") -> Iterable["InternetGateway"]:
        """Get all Internet Gateways."""
        return list(vpc.internet_gateways.all())

    @classmethod
    def get_first_igw(cls, vpc: "Vpc") -> Optional["InternetGateway"]:
        return next(iter(cls.get_all_igws(vpc)), None)

    def create_and_attach_internet_gateway(
        self,
        ec2_session: "EC2ServiceResource",
        vpc: "Vpc",
        reservation: "ReservationModel",
    ) -> "InternetGateway":
        igw = ec2_session.create_internet_gateway()

        igw_name = f"IGW {reservation.reservation_id}"
        tags = TagsHandler.create_default_tags(igw_name, reservation)
        tags.add_tags_to_obj(igw)

        vpc.attach_internet_gateway(InternetGatewayId=igw.id)
        return igw

    def get_or_create_igw(
        self,
        ec2_session: "EC2ServiceResource",
        vpc: "Vpc",
        reservation: "ReservationModel",
        logger: "Logger",
    ) -> "InternetGateway":
        vpc_name = self.get_name(vpc)
        logger.info(f"Getting first IGW from the VPC '{vpc_name}'")
        igw = self.get_first_igw(vpc)
        if not igw:
            logger.info(
                f"IGW for the VPC {vpc_name} not found. Creating a new one and "
                f"attaching to the VPC"
            )
            igw = self.create_and_attach_internet_gateway(ec2_session, vpc, reservation)
        return igw

    def remove_all_security_groups(self, vpc: "Vpc"):
        security_groups = list(vpc.security_groups.all())
        for sg in self.sg_service.sort_sg_list(security_groups):
            self.sg_service.delete_security_group(sg)

    def remove_security_groups_for_reservation(self, vpc: "Vpc", reservation_id: str):
        sg_list = self.sg_service.get_security_groups_by_reservation_id(
            vpc, reservation_id
        )
        for sg in self.sg_service.sort_sg_list(sg_list):
            self.sg_service.delete_security_group(sg)

    def remove_all_subnets(self, vpc: "Vpc"):
        """Will remove all attached subnets to that vpc."""
        subnets = list(vpc.subnets.all())
        for subnet in subnets:
            self.subnet_service.delete_subnet(subnet)
        return True

    def remove_subnets_for_reservation(self, vpc: "Vpc", reservation_id: str):
        for subnet in self.find_subnets_by_reservation_id(vpc, reservation_id):
            self.subnet_service.delete_subnet(subnet)

    def delete_all_instances(self, vpc: "Vpc"):
        instances = list(vpc.instances.all())
        self.instance_service.terminate_instances(instances)

    def delete_instances_for_reservation(self, vpc: "Vpc", reservation_id: str):
        instances = self.instance_service.get_instances_for_reservation(
            vpc, reservation_id
        )
        self.instance_service.terminate_instances(instances)

    def delete_vpc(self, vpc):
        """Will delete the vpc instance.

        :param vpc: VPC instance
        :return:
        """
        vpc.delete()
        return True

    @retry(stop_max_attempt_number=30, wait_fixed=1000)
    def modify_vpc_attribute(self, ec2_client, vpc_id, enable_dns_hostnames):
        """Enables VPC Attribute.

        :param ec2_client:
        :param vpc_id:
        :param enable_dns_hostnames:
        :return:
        """
        return ec2_client.modify_vpc_attribute(
            EnableDnsHostnames={"Value": enable_dns_hostnames}, VpcId=vpc_id
        )

    def get_or_pick_availability_zone(self, ec2_client, vpc, aws_ec2_datamodel):
        """Return a list of AvailabilityZones, available.

        :param ec2_client:
        :param vpc:
        :param AWSEc2CloudProviderResourceModel aws_ec2_datamodel:
        :return: str
        """
        # pick one of the vpc's subnets
        used_subnet = self.subnet_service.get_first_or_none_subnet_from_vpc(vpc)
        if used_subnet:
            return used_subnet.availability_zone

        # get one zone from the cloud-provider region's AvailabilityZones
        zones = ec2_client.describe_availability_zones(
            Filters=[
                {"Name": "state", "Values": ["available"]},
                {"Name": "region-name", "Values": [aws_ec2_datamodel.region]},
            ]
        )
        if zones and zones.get("AvailabilityZones"):
            return zones["AvailabilityZones"][0]["ZoneName"]

        # edge case - not supposed to happen
        raise ValueError("No AvailabilityZone is available for this vpc")

    @staticmethod
    def remove_custom_route_tables(vpc: "Vpc"):
        """Will remove all custom routing tables of that vpc."""
        for rt in RouteTableHandler.yield_custom_rts(vpc):
            rt.delete()

    @staticmethod
    def remove_route_tables_for_reservation(vpc: "Vpc", reservation_id: str):
        errors = []
        for fn in RouteTableHandler.get_private_rt, RouteTableHandler.get_public_rt:
            try:
                # noinspection PyArgumentList
                rt = fn(vpc, reservation_id)  # pycharm failed to get correct params
                rt.delete()
            except RouteTableNotFound:
                pass
            except Exception as e:
                errors.append(e)
        if errors:
            raise FailedToDeleteRouteTables(errors)

    def delete_traffic_mirror_elements(self, ec2_client, reservation_id, logger):
        tm_service = self.traffic_mirror_service
        session_ids = tm_service.find_mirror_session_ids_by_reservation_id(
            ec2_client, reservation_id
        )
        filter_ids = tm_service.find_traffic_mirror_filter_ids_by_reservation_id(
            ec2_client, reservation_id
        )
        target_ids = tm_service.find_traffic_mirror_targets_by_reservation_id(
            ec2_client, reservation_id
        )
        try:
            TrafficMirrorCleaner.cleanup(
                logger, ec2_client, session_ids, filter_ids, target_ids
            )
        except Exception:
            logger.exception(
                "Failed to cleanup traffic mirror elements during reservation cleanup"
            )

    @staticmethod
    def find_subnets_by_reservation_id(
        vpc: "Vpc", reservation_id: str
    ) -> List["Subnet"]:
        return list(
            vpc.subnets.filter(
                Filters=[{"Name": "tag:ReservationId", "Values": [reservation_id]}]
            )
        )

    @staticmethod
    def get_name(vpc: "Vpc") -> str:
        name = TagsHandler.from_tags_list(vpc.tags).get_name()
        if not name:
            name = vpc.vpc_id
        return name

    @staticmethod
    def delete_all_blackhole_routes(vpc: "Vpc"):
        for route_handler in RouteTableHandler.get_all_rts(vpc):
            route_handler.delete_blackhole_routes()

    def get_or_create_vpc_for_reservation(
        self,
        reservation: "ReservationModel",
        ec2_session: "EC2ServiceResource",
        vpc_cidr: str,
        logger: "Logger",
    ) -> "Vpc":
        rid = reservation.reservation_id
        logger.info(f"Searching for an exiting VPC for reservation {rid}")
        vpc = self.find_vpc_for_reservation(ec2_session, rid)
        if not vpc:
            logger.info(
                f"VPC for reservation {rid} not found. Creating it with cidr {vpc_cidr}"
            )
            vpc = self.create_vpc_for_reservation(
                ec2_session,
                reservation,
                vpc_cidr,
            )
        return vpc
