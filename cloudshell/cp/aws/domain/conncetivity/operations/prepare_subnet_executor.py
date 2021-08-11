import ipaddress
import traceback
from functools import wraps
from typing import TYPE_CHECKING

from cloudshell.cp.core.models import PrepareCloudInfraResult, PrepareSubnet

from cloudshell.cp.aws.domain.services.cloudshell.cs_subnet_service import (
    CsSubnetService,
)
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource
    from mypy_boto3_ec2.service_resource import Vpc

    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.common.cancellation_service import (
        CommandCancellationService,
    )
    from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService
    from cloudshell.cp.aws.domain.services.ec2.tags import TagService
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )
    from cloudshell.cp.aws.models.reservation_model import ReservationModel


class PrepareSubnetExecutor:
    SUBNET_RESERVATION = "{0} Reservation: {1}"

    class ActionItem:
        def __init__(self, action):
            self.action = action  # type: PrepareSubnet
            self.cidr = ""
            self.subnet = None
            self.is_new_subnet = False
            self.subnet_rt = None
            self.error = None

    def __init__(
        self,
        cancellation_service: "CommandCancellationService",
        vpc_service: "VPCService",
        subnet_service: "SubnetService",
        tag_service: "TagService",
        subnet_waiter: "SubnetWaiter",
        reservation: "ReservationModel",
        aws_ec2_datamodel: "AWSEc2CloudProviderResourceModel",
        cancellation_context: "CancellationContext",
        logger: "Logger",
        ec2_session: "EC2ServiceResource",
        ec2_client: "EC2Client",
        cs_subnet_service: "CsSubnetService",
    ):
        self.ec2_client = ec2_client
        self.ec2_session = ec2_session
        self.logger = logger
        self.cancellation_context = cancellation_context
        self.aws_ec2_datamodel = aws_ec2_datamodel
        self.reservation = reservation
        self.cancellation_service = cancellation_service
        self.vpc_service = vpc_service
        self.subnet_service = subnet_service
        self.tag_service = tag_service
        self.subnet_waiter = subnet_waiter
        self.cs_subnet_service = cs_subnet_service

    def execute(self, subnet_actions):
        if any(not isinstance(a, PrepareSubnet) for a in subnet_actions):
            raise ValueError("Not all actions are PrepareSubnet")
        action_items = [PrepareSubnetExecutor.ActionItem(a) for a in subnet_actions]

        # get vpc and availability_zone
        vpc = self.vpc_service.get_vpc(
            self.ec2_session, self.reservation.reservation_id, self.aws_ec2_datamodel
        )

        if not vpc:
            vpcs_count = self.vpc_service.get_active_vpcs_count(
                self.ec2_client, self.logger
            )
            additional_msg = ""
            if vpcs_count:
                additional_msg = (
                    f"\nThere are {vpcs_count} active VPCs in region "
                    f'"{self.aws_ec2_datamodel.region}".'
                    "\nPlease make sure you haven't exceeded your region's VPC limit."
                )
            raise ValueError(
                f"VPC for reservation {self.reservation.reservation_id} "
                f"not found.{additional_msg}"
            )

        availability_zone = self.vpc_service.get_or_pick_availability_zone(
            self.ec2_client, vpc, self.aws_ec2_datamodel
        )

        is_multi_subnet_mode = len(action_items) > 1  # type: bool
        # todo rename Subnet service in setup script
        if self.aws_ec2_datamodel.vpc_mode is VpcMode.SHARED:
            for item in action_items:
                self.cs_subnet_service.patch_subnet_cidr(
                    item, vpc.cidr_block, self.logger
                )
        for item in action_items:
            self._step_set_subnet_cidr(item, is_multi_subnet_mode)
            self._step_validate_subnet_cidr(item, vpc)
            self._step_get_existing_subnet(item, vpc)

        # create new subnet for the non-existing ones
        for item in action_items:
            self._step_create_new_subnet_if_needed(item, vpc, availability_zone)
        for item in action_items:
            self._step_wait_till_available(item)

        for item in action_items:
            self._step_set_tags(item)
            self._step_attach_to_route_table(item, vpc)

        if self.aws_ec2_datamodel.vpc_mode is VpcMode.SHARED:
            for item in action_items:
                self._step_attach_to_vgw(item)
                self._step_create_security_group_for_subnet(item, vpc)

        return [self._create_result(item) for item in action_items]

    # DECORATOR! First argument is the decorated function!
    def step_wrapper(step):
        @wraps(step)
        def wrapper(self, item, *args, **kwargs):
            self.cancellation_service.check_if_cancelled(self.cancellation_context)
            if item.error:
                return
            try:
                step(self, item, *args, **kwargs)
            except Exception as e:
                self.logger.error(
                    f"Error in prepare connectivity. Error: {traceback.format_exc()}"
                )
                item.error = e

        return wrapper

    @step_wrapper
    def _step_set_subnet_cidr(self, item: "ActionItem", is_multi_subnet_mode: bool):
        # VPC CIDR is determined as follows:
        #   if in VPC static mode and its a single subnet mode, use VPC CIDR
        #   if in VPC static mode and its multi subnet mode, we must assume its manual
        #     subnets and use action CIDR
        #   else use action CIDR
        alias = getattr(item.action.actionParams, "alias", "Default Subnet")
        if (
            self.aws_ec2_datamodel.vpc_mode is VpcMode.STATIC
            and self.aws_ec2_datamodel.vpc_cidr
            and not is_multi_subnet_mode
        ):
            cidr = self.aws_ec2_datamodel.vpc_cidr
            self.logger.info(
                f"Decided to use subnet CIDR {cidr} as defined on cloud provider "
                f"for subnet {alias}"
            )
        else:
            cidr = item.action.actionParams.cidr
            self.logger.info(
                f"Decided to use subnet CIDR {cidr} as defined on subnet request "
                f"for subnet {alias}"
            )
        item.cidr = cidr

    @step_wrapper
    def _step_validate_subnet_cidr(self, item: "ActionItem", vpc: "Vpc"):
        vpc_net = ipaddress.IPv4Network(vpc.cidr_block)
        subnet_net = ipaddress.IPv4Network(item.cidr)
        if not vpc_net.supernet_of(subnet_net):
            msg = f"Subnet CIDR {item.cidr} is not inside VPC CIDR {vpc.cidr_block}"
            raise ValueError(msg)

    @step_wrapper
    def _step_get_existing_subnet(self, item: "ActionItem", vpc: "Vpc"):
        rid = self.reservation.reservation_id
        self.logger.info(f"Check if subnet (cidr={item.cidr}) already exists")
        subnet = self.subnet_service.get_first_or_none_subnet_from_vpc(vpc, item.cidr)
        if subnet:
            if self.tag_service.get_reservation_tag(rid) not in subnet.tags:
                msg = (
                    f"Requested subnet with a CIDR {item.cidr} is already used for "
                    f"other purpose. Subnet tags: {subnet.tags}"
                )
                self.logger.error(msg)
                raise ValueError(msg)
            item.subnet = subnet

    @step_wrapper
    def _step_create_new_subnet_if_needed(self, item, vpc, availability_zone):
        if not item.subnet:
            alias = item.action.actionParams.alias
            self.logger.info(
                f"Create subnet (alias: {alias}, cidr: {item.cidr}, availability-zone: "
                f"{availability_zone})"
            )
            item.subnet = self.subnet_service.create_subnet_nowait(
                vpc, item.cidr, availability_zone
            )
            item.is_new_subnet = True

    @step_wrapper
    def _step_wait_till_available(self, item):
        if item.is_new_subnet:
            self.logger.info(f"Waiting for subnet {item.cidr} - start")
            self.subnet_waiter.wait(item.subnet, self.subnet_waiter.AVAILABLE)
            self.logger.info(f"Waiting for subnet {item.cidr} - end")

    @step_wrapper
    def _step_set_tags(self, item):
        alias = item.action.actionParams.alias or f"Subnet-{item.cidr}"
        subnet_name = self.SUBNET_RESERVATION.format(
            alias, self.reservation.reservation_id
        )
        is_public_tag = self.tag_service.get_is_public_tag(
            item.action.actionParams.isPublic
        )
        tags = self.tag_service.get_default_tags(subnet_name, self.reservation)
        tags.append(is_public_tag)
        self.tag_service.set_ec2_resource_tags(item.subnet, tags)

    @step_wrapper
    def _step_attach_to_route_table(self, item: "ActionItem", vpc):
        if (
            item.action.actionParams.isPublic
            and self.aws_ec2_datamodel.vpc_mode is not VpcMode.SHARED
        ):
            self.logger.info(
                "Subnet is public - no need to attach private routing table"
            )
            return

        if item.action.actionParams.isPublic:
            route_table = self.vpc_service.get_or_throw_public_route_table(
                vpc, self.reservation.reservation_id
            )
        else:
            route_table = self.vpc_service.get_or_throw_private_route_table(
                vpc, self.reservation.reservation_id
            )
        item.subnet_rt = route_table
        self.subnet_service.set_subnet_route_table(
            self.ec2_client, item.subnet.subnet_id, route_table.route_table_id
        )

    @step_wrapper
    def _step_attach_to_vgw(self, item: "ActionItem"):
        if (
            item.subnet_rt
            and item.action.actionParams.connectToVpn
            and self.aws_ec2_datamodel.vgw_id
            and self.aws_ec2_datamodel.vgw_cidrs
        ):
            for cidr in self.aws_ec2_datamodel.vgw_cidrs:
                self.vpc_service.route_table_service.add_route_to_gateway(
                    item.subnet_rt, self.aws_ec2_datamodel.vgw_id, cidr
                )

    @step_wrapper
    def _step_create_security_group_for_subnet(self, item: "ActionItem", vpc: "Vpc"):
        sg_service = self.vpc_service.sg_service
        sg_name = sg_service.subnet_sg_name(item.subnet.subnet_id)
        sg = sg_service.get_security_group_by_name(vpc, sg_name)
        if not sg:
            sg = sg_service.create_security_group(self.ec2_session, vpc.vpc_id, sg_name)
            tags = self.tag_service.get_default_tags(sg_name, self.reservation)
            self.tag_service.set_ec2_resource_tags(sg, tags)
            sg_service.set_subnet_sg_rules(sg)

    def _create_result(self, item):
        action_result = PrepareCloudInfraResult()
        action_result.actionId = item.action.actionId
        if item.subnet and not item.error:
            action_result.success = True
            action_result.subnetId = item.subnet.subnet_id
            action_result.infoMessage = "PrepareSubnet finished successfully"
        else:
            action_result.success = False
            action_result.errorMessage = (
                f"PrepareSandboxInfra ended with the error: {item.error}"
            )
        return action_result


class SubnetActionHelper:
    def __init__(
        self, prepare_subnet_params, aws_cp_model, logger, is_multi_subnet_mode
    ):
        """# noqa
        SubnetActionHelper decides what CIDR to use, a requested CIDR from attribute, if exists, or from Server
        and also whether to Enable Nat, & Route traffic through the NAT

        :param cloudshell.cp.core.models.PrepareSubnetParams prepare_subnet_params:
        :param cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model.AWSEc2CloudProviderResourceModel aws_cp_model:
        :param Logger logger:
        """

        # VPC CIDR is determined as follows:
        # if in VPC static mode and its a single subnet mode, use VPC CIDR
        # if in VPC static mode and its multi subnet mode, we must assume its manual
        # subnets and use action CIDR
        # else, use action CIDR
        # alias = prepare_subnet_params.alias if hasattr(prepare_subnet_params, 'alias')
        # else 'Default Subnet'
        alias = getattr(prepare_subnet_params, "alias", "Default Subnet")

        if (
            aws_cp_model.vpc_mode is VpcMode.STATIC
            and aws_cp_model.vpc_cidr != ""
            and not is_multi_subnet_mode
        ):
            self._cidr = aws_cp_model.vpc_cidr
            logger.info(
                f"Decided to use subnet CIDR {self._cidr} as defined on cloud provider "
                f"for subnet {alias}"
            )
        else:
            self._cidr = prepare_subnet_params.cidr
            logger.info(
                f"Decided to use subnet CIDR {self._cidr} as defined on subnet request "
                f"for subnet {alias}"
            )

    @property
    def cidr(self):
        return self._cidr
