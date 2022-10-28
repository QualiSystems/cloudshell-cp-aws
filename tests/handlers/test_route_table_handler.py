import pytest

from ..base import RouteTableTest

from cloudshell.cp.aws.domain.handlers.ec2 import (
    RouteTableHandler,
    RouteTableNotFound,
    TagsHandler,
)
from cloudshell.cp.aws.domain.handlers.ec2.route_table_handler import (
    MainRouteTableNotFound,
    get_private_rt_name,
    get_public_rt_name,
)


def test_get_main_rt(vpc, reservation):
    rth = RouteTableHandler.get_main_rt(vpc, reservation)

    assert rth.name == f"Main RoutingTable Reservation: {reservation.reservation_id}"


def test_main_rt_is_missed(vpc, reservation):
    del vpc._rts[1]

    with pytest.raises(MainRouteTableNotFound):
        RouteTableHandler.get_main_rt(vpc, reservation)


def test_get_public_rt_is_missed(vpc, reservation):
    rt_name = get_public_rt_name(reservation.reservation_id)
    with pytest.raises(RouteTableNotFound) as e:
        RouteTableHandler.get_public_rt(vpc, reservation)
        assert e.value.name == rt_name


def test_get_public_rt(vpc, reservation):
    rt_name = get_public_rt_name(reservation.reservation_id)
    tags = TagsHandler.create_default_tags(rt_name, reservation)
    aws_rt = RouteTableTest(tags=tags.aws_tags)
    vpc._rts.append(aws_rt)

    public_rt = RouteTableHandler.get_public_rt(vpc, reservation.reservation_id)

    assert public_rt.name == rt_name
    assert public_rt._aws_rt == aws_rt


def test_get_private_rt(vpc, reservation):
    rt_name = get_private_rt_name(reservation.reservation_id)
    tags = TagsHandler.create_default_tags(rt_name, reservation)
    aws_rt = RouteTableTest(tags=tags.aws_tags)
    vpc._rts.append(aws_rt)

    private_rt = RouteTableHandler.get_private_rt(vpc, reservation.reservation_id)

    assert private_rt.name == rt_name
    assert private_rt._aws_rt == aws_rt


def test_create_rt(vpc, reservation):
    rt_name = "RT name"
    new_rt = RouteTableHandler.create_rt(vpc, reservation, rt_name)

    assert new_rt.name == rt_name
    assert new_rt.is_main is False
