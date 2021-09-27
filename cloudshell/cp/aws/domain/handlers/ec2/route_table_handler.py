from typing import TYPE_CHECKING, Iterable

import attr

from cloudshell.cp.aws.common.cached_property import cached_property, invalidated_cache
from cloudshell.cp.aws.domain.handlers.ec2.route_handler import RouteHandler
from cloudshell.cp.aws.domain.handlers.ec2.tags_handler import TagsHandler

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import RouteTable, Vpc


PRIVATE_RT_NAME_FORMAT = "Private RoutingTable Reservation: {}"
PUBLIC_RT_NAME_FORMAT = "Public RoutingTable Reservation: {}"


class RouteTableError(Exception):
    ...


class RouteTableNotFound(RouteTableError):
    def __init__(self, name: str):
        super().__init__(f"Route Table {name} is not found.")


def get_public_rt_name(reservation_id: str) -> str:
    return PUBLIC_RT_NAME_FORMAT.format(reservation_id)


def get_private_rt_name(reservation_id: str) -> str:
    return PRIVATE_RT_NAME_FORMAT.format(reservation_id)


@attr.s(auto_attribs=True)
class RouteTableHandler:
    _aws_rt: "RouteTable"

    @classmethod
    def get_all(cls, vpc: "Vpc") -> Iterable["RouteTableHandler"]:
        return map(cls, vpc.route_tables.all())

    @classmethod
    def get_by_name(cls, vpc: "Vpc", name: str) -> "RouteTableHandler":
        for rt in cls.get_all(vpc):
            if rt.name == name:
                return rt
        raise RouteTableNotFound(name)

    @classmethod
    def get_public(cls, vpc: "Vpc", reservation_id: str) -> "RouteTableHandler":
        return cls.get_by_name(vpc, get_public_rt_name(reservation_id))

    @classmethod
    def get_private(cls, vpc: "Vpc", reservation_id: str) -> "RouteTableHandler":
        return cls.get_by_name(vpc, get_private_rt_name(reservation_id))

    @cached_property
    def tags(self) -> "TagsHandler":
        return TagsHandler.from_tags_list(self._aws_rt.tags)

    @cached_property
    def name(self) -> str:
        return self.tags.get_name()

    @cached_property
    def routes(self) -> Iterable["RouteHandler"]:
        aws_routes = self._aws_rt.routes
        if not isinstance(aws_routes, Iterable):
            aws_routes = [aws_routes]
        return map(RouteHandler, aws_routes)

    def delete_blackhole_routes(self) -> bool:
        is_blackhole_list = [route.delete_if_blackhole() for route in self.routes]
        is_any_deleted = any(is_blackhole_list)
        if is_any_deleted:
            invalidated_cache(self, "routes")
        return is_any_deleted

    def delete(self):
        self._aws_rt.delete()
