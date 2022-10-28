from abc import ABCMeta, abstractmethod
from functools import wraps
from typing import TYPE_CHECKING, Callable, List, Optional

import attr
from typing_extensions import Protocol

from cloudshell.cp.core.models import PrepareCloudInfraResult

from cloudshell.cp.aws.common.cached_property import cached_property
from cloudshell.cp.aws.domain.common.cancellation_service import check_if_cancelled
from cloudshell.cp.aws.domain.handlers.ec2 import RouteTableHandler, TagsHandler
from cloudshell.cp.aws.domain.handlers.ec2.cidr_block_handler import (
    CidrHandler,
    CidrListHandler,
)
from cloudshell.cp.aws.domain.services.ec2.subnet import get_subnet_reservation_name
from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2.service_resource import Subnet, Vpc  # noqa: I900  # noqa: I900

    from cloudshell.cp.core.models import PrepareSubnet
    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.services.cloudshell.cs_subnet_service import (
        CsSubnetService,
    )
    from cloudshell.cp.aws.domain.services.ec2.security_group import (
        SecurityGroupService,
    )
    from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService
    from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter
    from cloudshell.cp.aws.models.aws_api import AwsApiClients
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )
    from cloudshell.cp.aws.models.reservation_model import ReservationModel


@attr.s(auto_attribs=True)
class ActionItem:
    action: "PrepareSubnet"
    cidr: "CidrHandler"
    subnet: Optional["Subnet"] = None
    is_new_subnet: bool = False
    subnet_rt: Optional["RouteTableHandler"] = None
    error: Optional[Exception] = None

    @classmethod
    def from_action(cls, action: "PrepareSubnet") -> "ActionItem":
        return cls(
            action,
            CidrHandler(action.actionParams.cidr),
        )


class StepFunc(Protocol):
    def __call__(
        self: "PrepareSubnetsAbsStrategy", item: "ActionItem", **kwargs
    ) -> None:
        ...


def subnet_step_wrapper(fn: Callable) -> StepFunc:
    @wraps(fn)
    def wrapper(self: "PrepareSubnetsAbsStrategy", item: "ActionItem", **kwargs):
        check_if_cancelled(self._cancellation_context)
        if item.error:
            return
        try:
            fn(self, item, **kwargs)
        except Exception as e:
            self._logger.exception("Error in prepare subnet")
            item.error = e

    # noinspection PyTypeChecker
    return wrapper


@attr.s(auto_attribs=True)
class PrepareSubnetsAbsStrategy(metaclass=ABCMeta):
    _vpc_service: "VPCService"
    _subnet_service: "SubnetService"
    _subnet_waiter: "SubnetWaiter"
    _cs_subnet_service: "CsSubnetService"
    _sg_service: "SecurityGroupService"
    _cancellation_context: "CancellationContext"
    _aws_model: "AWSEc2CloudProviderResourceModel"
    _aws_clients: "AwsApiClients"
    _reservation: "ReservationModel"
    _subnet_actions: List["PrepareSubnet"]
    _logger: "Logger"

    def prepare(self) -> List["PrepareCloudInfraResult"]:
        availability_zone = self._vpc_service.get_or_pick_availability_zone(
            self._aws_clients.ec2_client, self.vpc, self._aws_model
        )
        is_multi_subnet_mode = len(self._subnet_actions) > 1
        action_items = list(map(ActionItem.from_action, self._subnet_actions))

        for item in action_items:
            self.set_subnet_cidr(item, is_multi_subnet_mode=is_multi_subnet_mode)
            self.get_existing_subnet(item)
            self.create_new_subnet_if_needed(item, availability_zone=availability_zone)
        for item in action_items:
            self.wait_till_available(item)
        for item in action_items:
            self.set_tags(item)
            self.attach_route_table(item)
            self.connect_to_vgw(item)
            self.create_sg_for_subnet(item)

        return list(map(self.create_result, action_items))

    @cached_property
    def vpc(self) -> "Vpc":
        return self._get_vpc()

    @abstractmethod
    def _get_vpc(self) -> "Vpc":
        raise NotImplementedError

    def _validate_subnet_cidr(self, subnet_cidr: "CidrHandler"):
        CidrListHandler.from_vpc(self.vpc).validate_is_supernet_of(subnet_cidr)

    @subnet_step_wrapper
    def set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        self._set_subnet_cidr(item, is_multi_subnet_mode)
        self._validate_subnet_cidr(item.cidr)

    @abstractmethod
    def _set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        raise NotImplementedError

    @subnet_step_wrapper
    def get_existing_subnet(self, item: "ActionItem"):
        rid = self._reservation.reservation_id
        self._logger.info(f"Check if subnet (cidr={item.cidr}) already exists")
        subnet = self._subnet_service.get_first_or_none_subnet_from_vpc(
            self.vpc, str(item.cidr)
        )
        if subnet:
            tags = TagsHandler.from_tags_list(subnet.tags)
            if rid == tags.get_reservation_id():
                item.subnet = subnet
            else:
                msg = (
                    f"Requested subnet with a CIDR {item.cidr} is already used for "
                    f"other purpose. Subnet tags: {tags}"
                )
                self._logger.error(msg)
                raise ValueError(msg)

    @subnet_step_wrapper
    def create_new_subnet_if_needed(self, item: "ActionItem", availability_zone: str):
        if not item.subnet:
            alias = item.action.actionParams.alias
            self._logger.info(
                f"Create subnet (alias: {alias}, cidr: {item.cidr}, availability-zone: "
                f"{availability_zone})"
            )
            item.subnet = self._subnet_service.create_subnet_nowait(
                self.vpc, str(item.cidr), availability_zone
            )
            item.is_new_subnet = True

    @subnet_step_wrapper
    def wait_till_available(self, item: "ActionItem"):
        if item.is_new_subnet:
            self._logger.info(f"Waiting for subnet {item.cidr} - start")
            self._subnet_waiter.wait(item.subnet, self._subnet_waiter.AVAILABLE)
            self._logger.info(f"Waiting for subnet {item.cidr} - end")

    @subnet_step_wrapper
    def set_tags(self, item: "ActionItem"):
        alias = item.action.actionParams.alias or f"Subnet-{item.cidr}"
        subnet_name = get_subnet_reservation_name(
            alias, self._reservation.reservation_id
        )
        tags = TagsHandler.create_default_tags(subnet_name, self._reservation)
        tags.set_is_public_tag(item.action.actionParams.isPublic)
        tags.add_tags_to_obj(item.subnet)

    @subnet_step_wrapper
    def attach_route_table(self, item: "ActionItem"):
        self._attach_route_table(item)

    @abstractmethod
    def _attach_route_table(self, item: "ActionItem"):
        raise NotImplementedError

    @subnet_step_wrapper
    def connect_to_vgw(self, item: "ActionItem"):
        self._connect_to_vgw(item)

    @abstractmethod
    def _connect_to_vgw(self, item: "ActionItem"):
        raise NotImplementedError

    @subnet_step_wrapper
    def create_sg_for_subnet(self, item: "ActionItem"):
        self._create_sg_for_subnet(item)

    @abstractmethod
    def _create_sg_for_subnet(self, item: "ActionItem"):
        raise NotImplementedError

    @staticmethod
    def create_result(item: "ActionItem") -> "PrepareCloudInfraResult":
        result = PrepareCloudInfraResult()
        result.actionId = item.action.actionId
        if item.subnet and not item.error:
            result.success = True
            result.subnetId = item.subnet.subnet_id
            result.infoMessage = "PrepareSubnet finished successfully"
        else:
            result.success = False
            result.errorMessage = f"PrepareSubnet ended with the error: {item.error}"
        return result


class PrepareSubnetsDynamicStrategy(PrepareSubnetsAbsStrategy):
    def _get_vpc(self):
        return self._vpc_service.get_vpc_for_reservation(
            self._aws_clients.ec2_session, self._reservation.reservation_id
        )

    def _set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        alias = getattr(item.action.actionParams, "alias", "Default Subnet")
        self._logger.info(
            f"Decided to use subnet CIDR {item.cidr} as defined on subnet request "
            f"for subnet {alias}"
        )

    def _attach_route_table(self, item: "ActionItem"):
        if not item.action.actionParams.isPublic:
            rt = RouteTableHandler.get_private_rt(
                self.vpc, self._reservation.reservation_id
            )
            item.subnet_rt = rt
            rt.associate_with_subnet(item.subnet.subnet_id)

    def _connect_to_vgw(self, item: "ActionItem"):
        """Do not connect in Dynamic VPC mode."""

    def _create_sg_for_subnet(self, item: "ActionItem"):
        """Do not create in Dynamic VPC mode."""


class PrepareSubnetsStaticStrategy(PrepareSubnetsAbsStrategy):
    def _get_vpc(self):
        return self._vpc_service.get_vpc_for_reservation(
            self._aws_clients.ec2_session, self._reservation.reservation_id
        )

    def _set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        alias = getattr(item.action.actionParams, "alias", "Default Subnet")
        if self._aws_model.static_vpc_cidr and not is_multi_subnet_mode:
            item.cidr = CidrHandler(self._aws_model.static_vpc_cidr)
            self._logger.info(
                f"Decided to use subnet CIDR {item.cidr} as defined on cloud provider "
                f"for subnet {alias}"
            )
        else:
            self._logger.info(
                f"Decided to use subnet CIDR {item.cidr} as defined on subnet request "
                f"for subnet {alias}"
            )

    def _attach_route_table(self, item: "ActionItem"):
        if not item.action.actionParams.isPublic:
            rt = RouteTableHandler.get_private_rt(
                self.vpc, self._reservation.reservation_id
            )
            item.subnet_rt = rt
            rt.associate_with_subnet(item.subnet.subnet_id)

    def _connect_to_vgw(self, item: "ActionItem"):
        """Do not connect in Static VPC mode."""

    def _create_sg_for_subnet(self, item: "ActionItem"):
        """Do not create in Static VPC mode."""


class PrepareSubnetsSharedStrategy(PrepareSubnetsAbsStrategy):
    def _get_vpc(self):
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.shared_vpc_id
        )

    def _patch_subnet_cidr(self, item: "ActionItem"):
        vpc_cidr_block_handler = CidrListHandler.from_vpc(self.vpc)
        cidr = vpc_cidr_block_handler.patch_cidr_to_be_inside(item.cidr, self._logger)
        if not cidr == item.cidr:
            item.cidr = cidr

    def _set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        self._patch_subnet_cidr(item)
        alias = getattr(item.action.actionParams, "alias", "Default Subnet")
        self._logger.info(
            f"Decided to use subnet CIDR {item.cidr} as defined on subnet request "
            f"for subnet {alias}"
        )

    def _attach_route_table(self, item: "ActionItem"):
        if item.action.actionParams.isPublic:
            rt = RouteTableHandler.get_public_rt(
                self.vpc, self._reservation.reservation_id
            )
        else:
            rt = RouteTableHandler.get_private_rt(
                self.vpc, self._reservation.reservation_id
            )
        item.subnet_rt = rt
        rt.associate_with_subnet(item.subnet.subnet_id)

    def _connect_to_vgw(self, item: "ActionItem"):
        vgw_id = self._aws_model.vgw_id
        if item.action.actionParams.connectToVpn and vgw_id:
            item.subnet_rt.add_routes_to_gw(vgw_id, self._aws_model.vgw_cidrs)

    def _create_sg_for_subnet(self, item: "ActionItem"):
        sg_name = self._sg_service.subnet_sg_name(item.subnet.subnet_id)
        sg = self._sg_service.get_security_group_by_name(self.vpc, sg_name)
        if not sg:
            sg = self._sg_service.create_security_group(
                self._aws_clients.ec2_session, self.vpc.vpc_id, sg_name
            )
            tags = TagsHandler.create_default_tags(sg_name, self._reservation)
            tags.add_tags_to_obj(sg)
            self._sg_service.set_subnet_sg_rules(sg)


class PrepareSubnetsSingleStrategy(PrepareSubnetsAbsStrategy):
    def _get_vpc(self):
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.aws_mgmt_vpc_id
        )

    def _set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        alias = getattr(item.action.actionParams, "alias", "Default Subnet")
        self._logger.info(
            f"Decided to use subnet CIDR {item.cidr} as defined on subnet request "
            f"for subnet {alias}"
        )

    def _attach_route_table(self, item: "ActionItem"):
        if item.action.actionParams.isPublic:
            rt = RouteTableHandler.get_public_rt(
                self.vpc, self._reservation.reservation_id
            )
        else:
            rt = RouteTableHandler.get_private_rt(
                self.vpc, self._reservation.reservation_id
            )
        item.subnet_rt = rt
        rt.associate_with_subnet(item.subnet.subnet_id)

    def _connect_to_vgw(self, item: "ActionItem"):
        """Do not connect in Static VPC mode."""

    def _create_sg_for_subnet(self, item: "ActionItem"):
        sg_name = self._sg_service.subnet_sg_name(item.subnet.subnet_id)
        sg = self._sg_service.get_security_group_by_name(self.vpc, sg_name)
        if not sg:
            sg = self._sg_service.create_security_group(
                self._aws_clients.ec2_session, self.vpc.vpc_id, sg_name
            )
            tags = TagsHandler.create_default_tags(sg_name, self._reservation)
            tags.add_tags_to_obj(sg)
            self._sg_service.set_subnet_sg_rules(sg)


STRATEGIES = {
    VpcMode.DYNAMIC: PrepareSubnetsDynamicStrategy,
    VpcMode.STATIC: PrepareSubnetsStaticStrategy,
    VpcMode.SHARED: PrepareSubnetsSharedStrategy,
    VpcMode.SINGLE: PrepareSubnetsSingleStrategy,
}


def get_prepare_subnet_strategy(
    vpc_service: "VPCService",
    subnet_service: "SubnetService",
    subnet_waiter: "SubnetWaiter",
    cs_subnet_service: "CsSubnetService",
    sg_service: "SecurityGroupService",
    subnet_actions: List["PrepareSubnet"],
    aws_clients: "AwsApiClients",
    aws_model: "AWSEc2CloudProviderResourceModel",
    reservation: "ReservationModel",
    cancellation_context: "CancellationContext",
    logger: "Logger",
) -> PrepareSubnetsAbsStrategy:
    # noinspection PyArgumentList
    return STRATEGIES[aws_model.vpc_mode](  # pycharm fails to get correct params
        vpc_service,
        subnet_service,
        subnet_waiter,
        cs_subnet_service,
        sg_service,
        cancellation_context,
        aws_model,
        aws_clients,
        reservation,
        subnet_actions,
        logger,
    )
