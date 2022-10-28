from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, List, Optional

import attr

from cloudshell.cp.core.models import PrepareCloudInfraResult

from cloudshell.cp.aws.common.cached_property import cached_property
from cloudshell.cp.aws.domain.common.cancellation_service import check_if_cancelled
from cloudshell.cp.aws.domain.handlers.ec2 import (
    IsolationTagValue,
    RouteTableHandler,
    TagsHandler,
    TypeTagValue,
)
from cloudshell.cp.aws.domain.handlers.ec2.vpc_peering_handler import (
    VpcPeeringConnectionNotFoundForReservation,
    VpcPeeringHandler,
)
from cloudshell.cp.aws.domain.services.ec2.transit_gateway import (
    get_transit_gateway_cidr_blocks,
)
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode
from cloudshell.cp.aws.models.port_data import PortData

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2.service_resource import (  # noqa: I900
        InternetGateway,
        SecurityGroup,
        Vpc,
    )

    from cloudshell.cp.core.models import PrepareCloudInfra
    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.services.ec2.security_group import (
        SecurityGroupService,
    )
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.models.aws_api import AwsApiClients
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )
    from cloudshell.cp.aws.models.reservation_model import ReservationModel


@attr.s(auto_attribs=True)
class PrepareCloudInfraAbsStrategy(metaclass=ABCMeta):
    _vpc_service: "VPCService"
    _security_group_service: "SecurityGroupService"
    _aws_clients: "AwsApiClients"
    _aws_model: "AWSEc2CloudProviderResourceModel"
    _reservation: "ReservationModel"
    _network_action: "PrepareCloudInfra"
    _cancellation_context: "CancellationContext"
    _logger: "Logger"

    def prepare(self) -> "PrepareCloudInfraResult":
        check_if_cancelled(self._cancellation_context)
        vpc = self.vpc
        self.enable_dns_hostnames(vpc)

        check_if_cancelled(self._cancellation_context)
        igw = self.get_or_create_igw()

        check_if_cancelled(self._cancellation_context)
        public_rt = self.get_or_create_public_rt()
        private_rt = self.get_or_create_private_rt()
        self.add_route_to_igw(public_rt, igw)

        check_if_cancelled(self._cancellation_context)
        self.connect_vpc_to_mgmt_vpc(public_rt, private_rt)

        check_if_cancelled(self._cancellation_context)
        isolated_sg = self.create_isolated_sg()
        default_sg = self.create_default_sg()
        self.set_sg_rules(isolated_sg, default_sg)

        return self.prepare_result([isolated_sg, default_sg])

    @cached_property
    def vpc(self) -> "Vpc":
        """Get or create a VPC based on the VPC mode."""
        return self._get_or_create_vpc()

    @abstractmethod
    def _get_or_create_vpc(self) -> "Vpc":
        raise NotImplementedError

    @cached_property
    def vpc_name(self) -> str:
        return self._vpc_service.get_name(self.vpc)

    def enable_dns_hostnames(self, vpc: "Vpc"):
        self._logger.info(f"Enable dns for the VPC '{self.vpc_name}'")
        self._vpc_service.modify_vpc_attribute(
            self._aws_clients.ec2_client, self.vpc.vpc_id, enable_dns_hostnames=True
        )

    @abstractmethod
    def get_or_create_igw(self) -> Optional["InternetGateway"]:
        raise NotImplementedError

    @abstractmethod
    def get_or_create_public_rt(self) -> "RouteTableHandler":
        raise NotImplementedError

    def get_or_create_private_rt(self) -> "RouteTableHandler":
        return RouteTableHandler.get_or_create_private_rt(
            self.vpc, self._reservation, self._logger
        )

    def add_route_to_igw(
        self, public_rt: "RouteTableHandler", igw: Optional["InternetGateway"]
    ):
        if not igw:
            return

        self._logger.info(
            f"Adding default route to IGW {igw.id} from public route table "
            f"'{public_rt.name}'"
        )
        public_rt.add_default_route_to_gw(igw.id)

    @abstractmethod
    def connect_vpc_to_mgmt_vpc(
        self, public_rt: "RouteTableHandler", private_rt: "RouteTableHandler"
    ):
        raise NotImplementedError

    def create_isolated_sg(self) -> "SecurityGroup":
        sg_name = self._security_group_service.sandbox_isolated_sg_name(
            self._reservation.reservation_id
        )
        self._logger.info(
            f"Searching for an isolated SG '{sg_name}' in the VPC '{self.vpc_name}'"
        )
        sg = self._security_group_service.get_security_group_by_name(self.vpc, sg_name)
        if not sg:
            self._logger.info(
                f"The isolated SG '{sg_name}' not found in the VPC '{self.vpc_name}'. "
                "Creating a new one."
            )
            sg = self._security_group_service.create_security_group(
                self._aws_clients.ec2_session, self.vpc.id, sg_name
            )
            tags = TagsHandler.create_security_group_tags(
                sg_name,
                self._reservation,
                IsolationTagValue.SHARED,
                TypeTagValue.ISOLATED,
            )
            tags.add_tags_to_obj(sg)
        return sg

    def create_default_sg(self) -> "SecurityGroup":
        sg_name = self._security_group_service.sandbox_default_sg_name(
            self._reservation.reservation_id
        )
        self._logger.info(
            f"Searching for a default SG '{sg_name}' in the VPC '{self.vpc_name}'"
        )
        sg = self._security_group_service.get_security_group_by_name(self.vpc, sg_name)
        if not sg:
            self._logger.info(
                f"The default SG '{sg_name}' not found in the VPC '{self.vpc_name}'. "
                "Creating a new one."
            )
            sg = self._security_group_service.create_security_group(
                self._aws_clients.ec2_session, self.vpc.id, sg_name
            )
            tags = TagsHandler.create_security_group_tags(
                sg_name,
                self._reservation,
                IsolationTagValue.SHARED,
                TypeTagValue.DEFAULT,
            )
            tags.add_tags_to_obj(sg)
        return sg

    @abstractmethod
    def set_sg_rules(self, isolated_sg: "SecurityGroup", default_sg: "SecurityGroup"):
        raise NotImplementedError

    def prepare_result(
        self,
        security_groups: List["SecurityGroup"],
    ) -> "PrepareCloudInfraResult":
        result = PrepareCloudInfraResult(
            actionId=self._network_action.actionId,
            success=True,
            infoMessage="PrepareCloudInfra finished successfully",
        )
        result.vpcId = self.vpc.id
        result.securityGroupId = [sg.id for sg in security_groups]
        return result


class PrepareCloudInfraDynamicStrategy(PrepareCloudInfraAbsStrategy):
    def _get_vpc_cidr(self) -> str:
        return self._network_action.actionParams.cidr

    def _get_or_create_vpc(self) -> "Vpc":
        return self._vpc_service.get_or_create_vpc_for_reservation(
            self._reservation,
            self._aws_clients.ec2_session,
            self._get_vpc_cidr(),
            self._logger,
        )

    def get_or_create_igw(self) -> "InternetGateway":
        return self._vpc_service.get_or_create_igw(
            self._aws_clients.ec2_session, self.vpc, self._reservation, self._logger
        )

    def get_or_create_public_rt(self) -> "RouteTableHandler":
        self._logger.info(f"Getting a main route table for the VPC '{self.vpc_name}'")
        return RouteTableHandler.get_main_rt(self.vpc, self._reservation)

    def connect_vpc_to_mgmt_vpc(
        self, public_rt: "RouteTableHandler", private_rt: "RouteTableHandler"
    ):
        try:
            peering = VpcPeeringHandler.get_active_by_reservation_id(
                self._aws_clients.ec2_session, self._reservation.reservation_id
            )
        except VpcPeeringConnectionNotFoundForReservation:
            peering = VpcPeeringHandler.create(
                self._aws_clients.ec2_session,
                self._aws_model.aws_mgmt_vpc_id,
                self.vpc.id,
                self._reservation,
                self._logger,
            )

        # create routes to peering from MGMT VPC
        mgmt_vpc = self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.aws_mgmt_vpc_id
        )
        for rt in RouteTableHandler.get_all_rts(mgmt_vpc):
            rt.add_route_to_peering(peering.id, self.vpc.cidr_block)

        # create routes to peering from sandbox VPC
        for rt in (public_rt, private_rt):
            rt.add_route_to_peering(peering.id, mgmt_vpc.cidr_block)

    def set_sg_rules(self, isolated_sg: "SecurityGroup", default_sg: "SecurityGroup"):
        self._security_group_service.set_isolated_security_group_rules(
            isolated_sg, self._aws_model.aws_mgmt_sg_id, need_management_access=True
        )
        self._security_group_service.set_shared_reservation_security_group_rules(
            security_group=default_sg,
            management_sg_id=self._aws_model.aws_mgmt_sg_id,
            isolated_sg=isolated_sg,
            need_management_sg=True,
        )


class PrepareCloudInfraStaticStrategy(PrepareCloudInfraAbsStrategy):
    def _get_vpc_cidr(self) -> str:
        return self._aws_model.static_vpc_cidr

    def _get_or_create_vpc(self) -> "Vpc":
        return self._vpc_service.get_or_create_vpc_for_reservation(
            self._reservation,
            self._aws_clients.ec2_session,
            self._get_vpc_cidr(),
            self._logger,
        )

    def get_or_create_igw(self) -> "InternetGateway":
        return self._vpc_service.get_or_create_igw(
            self._aws_clients.ec2_session, self.vpc, self._reservation, self._logger
        )

    def get_or_create_public_rt(self) -> "RouteTableHandler":
        self._logger.info(f"Getting a main route table for the VPC '{self.vpc_name}'")
        return RouteTableHandler.get_main_rt(self.vpc, self._reservation)

    def connect_vpc_to_mgmt_vpc(
        self, public_rt: "RouteTableHandler", private_rt: "RouteTableHandler"
    ):
        self._logger.info("In Static VPC mode we do not create peering to MGMT VPC")

    def set_sg_rules(self, isolated_sg: "SecurityGroup", default_sg: "SecurityGroup"):
        self._security_group_service.set_isolated_security_group_rules(
            isolated_sg, self._aws_model.aws_mgmt_sg_id, need_management_access=False
        )
        self._security_group_service.set_shared_reservation_security_group_rules(
            security_group=default_sg,
            management_sg_id=self._aws_model.aws_mgmt_sg_id,
            isolated_sg=isolated_sg,
            need_management_sg=False,
        )


class PrepareCloudInfraSharedStrategy(PrepareCloudInfraAbsStrategy):
    def _get_or_create_vpc(self) -> "Vpc":
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.shared_vpc_id
        )

    def get_or_create_igw(self) -> Optional["InternetGateway"]:
        return self._vpc_service.get_first_igw(self.vpc)

    def get_or_create_public_rt(self) -> "RouteTableHandler":
        return RouteTableHandler.get_or_create_public_rt(
            self.vpc, self._reservation, self._logger
        )

    def connect_vpc_to_mgmt_vpc(
        self, public_rt: "RouteTableHandler", private_rt: "RouteTableHandler"
    ):
        mgmt_vpc = self._vpc_service.get_vpc_by_id(
            self._aws_clients.default_ec2_session, self._aws_model.aws_mgmt_vpc_id
        )
        cidr_blocks = get_transit_gateway_cidr_blocks(
            self._aws_clients.ec2_client, self._aws_model.tgw_id
        )
        cidr_blocks.append(mgmt_vpc.cidr_block)
        cidr_blocks.extend(self._aws_model.additional_mgmt_networks)

        for route_table in (public_rt, private_rt):
            route_table.add_routes_to_tgw(self._aws_model.tgw_id, cidr_blocks)

    def set_sg_rules(self, isolated_sg: "SecurityGroup", default_sg: "SecurityGroup"):
        self._security_group_service.set_isolated_security_group_rules(
            isolated_sg, self._aws_model.aws_mgmt_sg_id, need_management_access=False
        )
        self._security_group_service.set_shared_reservation_security_group_rules(
            security_group=default_sg,
            management_sg_id=self._aws_model.aws_mgmt_sg_id,
            isolated_sg=isolated_sg,
            need_management_sg=False,
        )

        inbound_ports = [
            PortData(from_port="-1", to_port="-1", protocol="-1", destination=cidr)
            for cidr in self._aws_model.additional_mgmt_networks
        ]
        for sg in (isolated_sg, default_sg):
            self._security_group_service.set_security_group_rules(
                sg, inbound_ports, logger=self._logger
            )


class PrepareCloudInfraSingleStrategy(PrepareCloudInfraAbsStrategy):
    def _get_or_create_vpc(self) -> "Vpc":
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.aws_mgmt_vpc_id
        )

    def get_or_create_igw(self) -> Optional["InternetGateway"]:
        return self._vpc_service.get_first_igw(self.vpc)

    def get_or_create_public_rt(self) -> "RouteTableHandler":
        return RouteTableHandler.get_or_create_public_rt(
            self.vpc, self._reservation, self._logger
        )

    def connect_vpc_to_mgmt_vpc(
        self, public_rt: "RouteTableHandler", private_rt: "RouteTableHandler"
    ):
        pass

    def set_sg_rules(self, isolated_sg: "SecurityGroup", default_sg: "SecurityGroup"):
        self._security_group_service.set_isolated_security_group_rules(
            isolated_sg, self._aws_model.aws_mgmt_sg_id, need_management_access=False
        )
        self._security_group_service.set_shared_reservation_security_group_rules(
            security_group=default_sg,
            management_sg_id=self._aws_model.aws_mgmt_sg_id,
            isolated_sg=isolated_sg,
            need_management_sg=False,
        )

        inbound_ports = [
            PortData(from_port="-1", to_port="-1", protocol="-1", destination=cidr)
            for cidr in self._aws_model.additional_mgmt_networks
        ]
        for sg in (isolated_sg, default_sg):
            self._security_group_service.set_security_group_rules(
                sg, inbound_ports, logger=self._logger
            )


STRATEGIES = {
    VpcMode.DYNAMIC: PrepareCloudInfraDynamicStrategy,
    VpcMode.STATIC: PrepareCloudInfraStaticStrategy,
    VpcMode.SHARED: PrepareCloudInfraSharedStrategy,
    VpcMode.SINGLE: PrepareCloudInfraSingleStrategy,
}


def get_prepare_infra_strategy(
    vpc_service: "VPCService",
    security_group_service: "SecurityGroupService",
    aws_clients: "AwsApiClients",
    aws_model: "AWSEc2CloudProviderResourceModel",
    reservation: "ReservationModel",
    network_action: "PrepareCloudInfra",
    cancellation_context: "CancellationContext",
    logger: "Logger",
) -> PrepareCloudInfraAbsStrategy:
    # noinspection PyArgumentList
    return STRATEGIES[aws_model.vpc_mode](  # pycharm fails to get correct params
        vpc_service,
        security_group_service,
        aws_clients,
        aws_model,
        reservation,
        network_action,
        cancellation_context,
        logger,
    )
