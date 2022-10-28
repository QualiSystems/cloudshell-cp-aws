from logging import Logger
from typing import TYPE_CHECKING, Generator, Iterable, List, Optional

import attr

from .route_handler import RouteHandler
from .tags_handler import TagsHandler

from cloudshell.cp.aws.common.cached_property import cached_property, invalidated_cache

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import RouteTable, Vpc  # noqa: I900

    from cloudshell.cp.aws.models.reservation_model import ReservationModel


PRIVATE_RT_NAME_FORMAT = "Private RoutingTable Reservation: {}"
PUBLIC_RT_NAME_FORMAT = "Public RoutingTable Reservation: {}"
MAIN_RT_NAME_FORMAT = "Main RoutingTable Reservation: {}"


class RouteTableError(Exception):
    ...


class RouteTableNotFound(RouteTableError):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Route Table {name} is not found.")


class MainRouteTableNotFound(RouteTableError):
    def __init__(self, vpc: "Vpc"):
        super().__init__(f"Main Route Table for the VPC {vpc.id} is not found.")


def get_public_rt_name(reservation_id: str) -> str:
    return PUBLIC_RT_NAME_FORMAT.format(reservation_id)


def get_private_rt_name(reservation_id: str) -> str:
    return PRIVATE_RT_NAME_FORMAT.format(reservation_id)


def get_main_rt_name(reservation_id: str) -> str:
    return MAIN_RT_NAME_FORMAT.format(reservation_id)


def get_vpc_name(vpc: "Vpc") -> str:
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService

    return VPCService.get_name(vpc)


@attr.s(auto_attribs=True)
class RouteTableHandler:
    _aws_rt: "RouteTable"

    @classmethod
    def get_all_rts(cls, vpc: "Vpc") -> Iterable["RouteTableHandler"]:
        return map(cls, vpc.route_tables.all())

    @classmethod
    def get_rt_by_name(cls, vpc: "Vpc", name: str) -> "RouteTableHandler":
        for rt in cls.get_all_rts(vpc):
            if rt.name == name:
                return rt
        raise RouteTableNotFound(name)

    @classmethod
    def get_public_rt(cls, vpc: "Vpc", reservation_id: str) -> "RouteTableHandler":
        return cls.get_rt_by_name(vpc, get_public_rt_name(reservation_id))

    @classmethod
    def get_private_rt(cls, vpc: "Vpc", reservation_id: str) -> "RouteTableHandler":
        return cls.get_rt_by_name(vpc, get_private_rt_name(reservation_id))

    @classmethod
    def create_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel", rt_name: str
    ) -> "RouteTableHandler":
        tags = TagsHandler.create_default_tags(rt_name, reservation)
        rt = cls(vpc.create_route_table())
        rt.add_tags(tags)
        return rt

    @classmethod
    def create_private_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel"
    ) -> "RouteTableHandler":
        rt_name = get_private_rt_name(reservation.reservation_id)
        return cls.create_rt(vpc, reservation, rt_name)

    @classmethod
    def create_public_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel"
    ) -> "RouteTableHandler":
        rt_name = get_public_rt_name(reservation.reservation_id)
        return cls.create_rt(vpc, reservation, rt_name)

    @classmethod
    def get_or_create_private_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel", logger: "Logger"
    ):
        vpc_name = get_vpc_name(vpc)
        rid = reservation.reservation_id
        logger.info(
            f"Searching for a private route table for reservation {rid} in the VPC "
            f"'{vpc_name}'"
        )
        try:
            rt = cls.get_private_rt(vpc, rid)
        except RouteTableNotFound:
            logger.info(
                f"Private route table for reservation {rid} not found in the VPC "
                f"{vpc_name}. Creating a new one."
            )
            rt = cls.create_private_rt(vpc, reservation)
        return rt

    @classmethod
    def get_or_create_public_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel", logger: "Logger"
    ):
        vpc_name = get_vpc_name(vpc)
        rid = reservation.reservation_id
        logger.info(
            f"Searching for a public route table for reservation {rid} in the VPC "
            f"'{vpc_name}'"
        )
        try:
            rt = cls.get_public_rt(vpc, rid)
        except RouteTableNotFound:
            logger.info(
                f"Public route table for reservation {rid} not found in the VPC "
                f"{vpc_name}. Creating a new one."
            )
            rt = cls.create_public_rt(vpc, reservation)
        return rt

    @classmethod
    def get_main_rt(
        cls, vpc: "Vpc", reservation: "ReservationModel"
    ) -> "RouteTableHandler":
        for rt in cls.get_all_rts(vpc):
            if rt.is_main:
                break
        else:
            raise MainRouteTableNotFound(vpc)

        rt_name = get_main_rt_name(reservation.reservation_id)
        tags = TagsHandler.create_default_tags(rt_name, reservation)
        rt.add_tags(tags)
        return rt

    @classmethod
    def yield_custom_rts(cls, vpc: "Vpc") -> Generator["RouteTableHandler", None, None]:
        for rt in cls.get_all_rts(vpc):
            if not rt.is_main:
                yield rt

    @cached_property
    def tags(self) -> "TagsHandler":
        self._aws_rt.load()
        return TagsHandler.from_tags_list(self._aws_rt.tags)

    @property
    def name(self) -> str:
        return self.tags.get_name()

    @cached_property
    def is_main(self) -> bool:
        for att in self._aws_rt.associations_attribute:
            if att.get("Main") is True:
                return True
        return False

    @cached_property
    def routes(self) -> Iterable["RouteHandler"]:
        self._aws_rt.load()
        aws_routes = self._aws_rt.routes
        if not isinstance(aws_routes, Iterable):
            aws_routes = [aws_routes]
        return map(RouteHandler, aws_routes)

    def _update_routes(self):
        invalidated_cache(self, "routes")

    def _update_tags(self):
        invalidated_cache(self, "tags")

    def delete_blackhole_routes(self) -> bool:
        is_blackhole_list = [route.delete_if_blackhole() for route in self.routes]
        is_any_deleted = any(is_blackhole_list)
        if is_any_deleted:
            self._update_routes()
        return is_any_deleted

    def delete(self):
        self._aws_rt.delete()

    def add_tags(self, tags: "TagsHandler"):
        tags.add_tags_to_obj(self._aws_rt)
        self._update_tags()

    def find_route_to_gateway(
        self, gateway_id: str, dst_cidr: str
    ) -> Optional["RouteHandler"]:
        for route in self.routes:
            if route.gateway_id == gateway_id and route.dst_cidr == dst_cidr:
                return route

    def find_route_to_tgw(self, tgw_id: str, dst_cidr: str) -> Optional["RouteHandler"]:
        for route in self.routes:
            if route.tgw_id == tgw_id and route.dst_cidr == dst_cidr:
                return route

    def find_route_by_dst_cidr(self, cidr: str) -> Optional["RouteHandler"]:
        for route in self.routes:
            if route.dst_cidr == cidr:
                return route

    def add_routes_to_gw(self, gateway_id: str, dst_cidrs: List[str]):
        missed_dst_cidrs = []
        for dst_cidr in dst_cidrs:
            if not self.find_route_to_gateway(gateway_id, dst_cidr):
                missed_dst_cidrs.append(dst_cidr)

        for dst_cidr in missed_dst_cidrs:
            self._aws_rt.create_route(
                GatewayId=gateway_id, DestinationCidrBlock=dst_cidr
            )
        if missed_dst_cidrs:
            self._update_routes()

    def add_default_route_to_gw(self, gateway_id: str):
        self.add_routes_to_gw(gateway_id, ["0.0.0.0/0"])

    def _add_route_to_peering(self, peering_id: str, dst_cidr: str):
        self._aws_rt.create_route(
            VpcPeeringConnectionId=peering_id, DestinationCidrBlock=dst_cidr
        )
        self._update_routes()

    def add_route_to_peering(self, peering_id: str, dst_cid: str):
        route = self.find_route_by_dst_cidr(dst_cid)
        if route:
            route.replace_peering_connection(peering_id)
        else:
            self._add_route_to_peering(peering_id, dst_cid)

    def add_routes_to_tgw(self, tgw_id: str, dst_cidrs: List[str]):
        missed_dst_cidrs = []
        for dst_cidr in dst_cidrs:
            if not self.find_route_to_tgw(tgw_id, dst_cidr):
                missed_dst_cidrs.append(dst_cidr)

        for dst_cidr in missed_dst_cidrs:
            self._aws_rt.create_route(
                TransitGatewayId=tgw_id, DestinationCidrBlock=dst_cidr
            )
        if missed_dst_cidrs:
            self._update_routes()

    def associate_with_subnet(self, subnet_id: str):
        self._aws_rt.associate_with_subnet(SubnetId=subnet_id)
