from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, List

from cloudshell.cp.core.models import CleanupNetwork

from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource
    from mypy_boto3_ec2.service_resource import Vpc

    from cloudshell.cp.aws.domain.services.ec2.keypair import KeyPairService
    from cloudshell.cp.aws.domain.services.ec2.mirroring import TrafficMirrorService
    from cloudshell.cp.aws.domain.services.ec2.route_table import RouteTablesService
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )


class CleanupSandboxInfraException(Exception):
    pass


class CleanupSandboxInfraBaseStrategy(ABC):
    def __init__(
        self,
        vpc_service: "VPCService",
        key_pair_service: "KeyPairService",
        route_table_service: "RouteTablesService",
        traffic_mirror_service: "TrafficMirrorService",
        ec2_client: "EC2Client",
        ec2_session: "EC2ServiceResource",
        s3_session,
        aws_ec2_datamodel: "AWSEc2CloudProviderResourceModel",
        reservation_id: str,
        actions: list,
        logger: "Logger",
    ):
        self.vpc_service = vpc_service
        self.key_pair_service = key_pair_service
        self.route_table_service = route_table_service
        self.traffic_mirror_service = traffic_mirror_service
        self.ec2_client = ec2_client
        self.ec2_session = ec2_session
        self.s3_session = s3_session
        self.aws_ec2_datamodel = aws_ec2_datamodel
        self.reservation_id = reservation_id
        self.actions = actions
        self.logger = logger
        self._cleanup_exceptions: List[Exception] = []

    def cleanup(self):
        self.remove_keypair()

        vpc = self.get_vpc()
        self.remove_instances(vpc)
        self.remove_igw(vpc)
        self.remove_security_groups(vpc)
        self.remove_subnets(vpc)
        self.remove_peerings(vpc)
        self.remove_blackhole_routes_mgt_vpc()
        self.remove_custom_route_tables(vpc)
        self.remove_traffic_mirror_elements()
        self.remove_vpc(vpc)

        if self._cleanup_exceptions:
            raise CleanupSandboxInfraException(self._cleanup_exceptions)

    @contextmanager
    def save_exception_context(self):
        try:
            yield
        except Exception as e:
            self.logger.exception(e)
            self._cleanup_exceptions.append(e)

    def remove_keypair(self):
        self.logger.info("Removing private key (pem file) from s3")
        self.key_pair_service.remove_key_pair_for_reservation_in_s3(
            self.s3_session,
            self.aws_ec2_datamodel.key_pairs_location,
            self.reservation_id,
        )
        self.logger.info("Removing key pair from ec2")
        self.key_pair_service.remove_key_pair_for_reservation_in_ec2(
            self.ec2_session, self.reservation_id
        )

    @abstractmethod
    def get_vpc(self) -> "Vpc":
        raise NotImplementedError

    def remove_instances(self, vpc: "Vpc"):
        self.logger.info("Removing instances")
        with self.save_exception_context():
            self._remove_instances(vpc)

    @abstractmethod
    def _remove_instances(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_igw(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_igw(vpc)

    @abstractmethod
    def _remove_igw(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_security_groups(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_security_groups(vpc)

    @abstractmethod
    def _remove_security_groups(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_subnets(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_subnets(vpc)

    @abstractmethod
    def _remove_subnets(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_peerings(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_peerings(vpc)

    @abstractmethod
    def _remove_peerings(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_blackhole_routes_mgt_vpc(self):
        with self.save_exception_context():
            self._remove_blackhole_routes_mgt_vpc()

    @abstractmethod
    def _remove_blackhole_routes_mgt_vpc(self):
        raise NotImplementedError

    def remove_custom_route_tables(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_custom_route_tables(vpc)

    @abstractmethod
    def _remove_custom_route_tables(self, vpc: "Vpc"):
        raise NotImplementedError

    def remove_traffic_mirror_elements(self):
        with self.save_exception_context():
            self._remove_traffic_mirror_elements()

    def _remove_traffic_mirror_elements(self):
        self.vpc_service.delete_traffic_mirror_elements(
            self.ec2_client,
            self.traffic_mirror_service,
            self.reservation_id,
            self.logger,
        )

    def remove_vpc(self, vpc: "Vpc"):
        with self.save_exception_context():
            self._remove_vpc(vpc)

    @abstractmethod
    def _remove_vpc(self, vpc: "Vpc"):
        raise NotImplementedError


class CleanupSandboxInfraDynamicStaticVpcStrategy(CleanupSandboxInfraBaseStrategy):
    def get_vpc(self) -> "Vpc":
        vpc = self.vpc_service.find_vpc_for_reservation(
            self.ec2_session, self.reservation_id
        )
        if not vpc:
            raise CleanupSandboxInfraException("No VPC was created for the reservation")
        return vpc

    def _remove_instances(self, vpc: "Vpc"):
        self.vpc_service.delete_all_instances(vpc)

    def _remove_igw(self, vpc: "Vpc"):
        self.vpc_service.remove_all_internet_gateways(vpc)

    def _remove_security_groups(self, vpc: "Vpc"):
        self.vpc_service.remove_all_security_groups(vpc)

    def _remove_subnets(self, vpc: "Vpc"):
        self.vpc_service.remove_all_subnets(vpc)

    def _remove_peerings(self, vpc: "Vpc"):
        self.vpc_service.remove_all_peering(vpc)

    def _remove_blackhole_routes_mgt_vpc(self):
        rts = self.route_table_service.get_all_route_tables(
            self.ec2_session, self.aws_ec2_datamodel.aws_management_vpc_id
        )
        for rt in rts:
            self.route_table_service.delete_blackhole_routes(rt, self.ec2_client)

    def _remove_custom_route_tables(self, vpc: "Vpc"):
        self.vpc_service.remove_custom_route_tables(self.ec2_session, vpc)

    def _remove_vpc(self, vpc: "Vpc"):
        self.vpc_service.delete_vpc(vpc)


class CleanupSandboxInfraSharedVpcStrategy(CleanupSandboxInfraBaseStrategy):
    def get_vpc(self) -> "Vpc":
        return self.vpc_service.get_vpc_by_id(
            self.ec2_session, self.aws_ec2_datamodel.vpc_id
        )

    def _remove_instances(self, vpc: "Vpc"):
        inst_s = self.vpc_service.instance_service
        inst_s.terminate_instances(
            inst_s.get_instances_for_reservation(vpc, self.reservation_id)
        )

    def _remove_igw(self, vpc: "Vpc"):
        """In a Shared VPC we do not create/remove IGW."""
        pass

    def _remove_security_groups(self, vpc: "Vpc"):
        sg_service = self.vpc_service.sg_service
        sg_list = sg_service.get_security_groups_by_reservation_id(
            vpc, self.reservation_id
        )
        for sg in sg_service.sort_sg_list(sg_list):
            try:
                sg_service.delete_security_group(sg)
            except Exception as e:
                self._cleanup_exceptions.append(e)

    def _remove_subnets(self, vpc: "Vpc"):
        for subnet in self.vpc_service.find_subnets_by_reservation_id(
            vpc, self.reservation_id
        ):
            net_interfaces = list(subnet.network_interfaces.all())
            for net_int in net_interfaces:
                net_int.detach()
                net_int.delete()
            self.vpc_service.subnet_service.delete_subnet(subnet)

    def _remove_peerings(self, vpc: "Vpc"):
        """In a Shared VPC we do not create peering connections."""
        pass

    def _remove_blackhole_routes_mgt_vpc(self):
        """In a Shared VPC we do not create routes to Management VPS."""
        pass

    def _remove_custom_route_tables(self, vpc: "Vpc"):
        try:
            try:
                private_rt = self.vpc_service.get_or_throw_private_route_table(
                    vpc, self.reservation_id
                )
            except ValueError:
                pass
            else:
                self.route_table_service.delete_table(private_rt)
        except Exception as e:
            self._cleanup_exceptions.append(e)

        try:
            try:
                public_rt = self.vpc_service.get_or_throw_public_route_table(
                    vpc, self.reservation_id
                )
            except ValueError:
                pass
            else:
                self.route_table_service.delete_table(public_rt)
        except Exception as e:
            self._cleanup_exceptions.append(e)

    def _remove_vpc(self, vpc: "Vpc"):
        """In a Shared VPC we do not create the VPC."""
        pass


class CleanupSandboxInfraOperation:
    STRATEGIES = {
        VpcMode.DYNAMIC: CleanupSandboxInfraDynamicStaticVpcStrategy,
        VpcMode.STATIC: CleanupSandboxInfraDynamicStaticVpcStrategy,
        VpcMode.SHARED: CleanupSandboxInfraSharedVpcStrategy,
    }

    def __init__(
        self, vpc_service, key_pair_service, route_table_service, traffic_mirror_service
    ):
        self.vpc_service = vpc_service
        self.key_pair_service = key_pair_service
        self.route_table_service = route_table_service
        self.traffic_mirror_service = traffic_mirror_service

    def cleanup(
        self,
        ec2_client: "EC2Client",
        ec2_session: "EC2ServiceResource",
        s3_session,
        aws_ec2_data_model: "AWSEc2CloudProviderResourceModel",
        reservation_id: str,
        actions: list,
        logger: "Logger",
    ):
        if not actions:
            raise ValueError("No cleanup action was found")

        result = CleanupNetwork()
        result.actionId = actions[0].actionId
        result.success = True
        strategy = self.STRATEGIES[aws_ec2_data_model.vpc_mode](
            self.vpc_service,
            self.key_pair_service,
            self.route_table_service,
            self.traffic_mirror_service,
            ec2_client,
            ec2_session,
            s3_session,
            aws_ec2_data_model,
            reservation_id,
            actions,
            logger,
        )

        try:
            strategy.cleanup()
        except Exception as exc:
            logger.exception("Error in cleanup connectivity")
            result.success = False
            result.errorMessage = f"CleanupSandboxInfra ended with the error: {exc}"
        return result
