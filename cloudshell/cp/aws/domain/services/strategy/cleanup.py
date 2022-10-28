from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, List

import attr

from cloudshell.cp.aws.common.cached_property import cached_property
from cloudshell.cp.aws.domain.handlers.ec2 import VpcPeeringHandler
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2.service_resource import Vpc  # noqa: I900

    from cloudshell.cp.aws.domain.services.ec2.keypair import KeyPairService
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.models.aws_api import AwsApiClients
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )


class CleanupSandboxInfraException(Exception):
    ...


class VpcNotFound(CleanupSandboxInfraException):
    def __init__(self, r_id: str):
        super().__init__(f"No VPC was created for the reservation {r_id}")


@attr.s(auto_attribs=True)
class CleanupSandboxInfraAbsStrategy(metaclass=ABCMeta):
    _vpc_service: "VPCService"
    _key_pair_service: "KeyPairService"
    _aws_clients: "AwsApiClients"
    _aws_model: "AWSEc2CloudProviderResourceModel"
    _reservation_id: "str"
    _logger: "Logger"

    def __attrs_post_init__(self):
        self._cleanup_exceptions: List[Exception] = []

    def cleanup(self):
        self.remove_keypair()
        self.remove_instances()
        self.remove_igw()
        self.remove_security_groups()
        self.remove_subnets()
        self.remove_peerings()
        self.remove_blackhole_routes_mgt_vpc()
        self.remove_custom_route_tables()
        self.remove_traffic_mirror_elements()
        self.remove_vpc()

        if self._cleanup_exceptions:
            raise CleanupSandboxInfraException(self._cleanup_exceptions)

    @contextmanager
    def save_exception_context(self):
        try:
            yield
        except Exception as e:
            self._logger.exception(e)
            self._cleanup_exceptions.append(e)

    def remove_keypair(self):
        self._logger.info("Removing private key (pem file) from s3")
        self._key_pair_service.remove_key_pair_for_reservation_in_s3(
            self._aws_clients.s3_session,
            self._aws_model.key_pairs_location,
            self._reservation_id,
        )
        self._logger.info("Removing key pair from ec2")
        self._key_pair_service.remove_key_pair_for_reservation_in_ec2(
            self._aws_clients.ec2_session, self._reservation_id
        )

    @cached_property
    def vpc(self) -> "Vpc":
        return self.get_vpc()

    @abstractmethod
    def get_vpc(self) -> "Vpc":
        raise NotImplementedError

    @cached_property
    def vpc_name(self) -> str:
        return self._vpc_service.get_name(self.vpc)

    def remove_instances(self):
        with self.save_exception_context():
            self._remove_instances()

    @abstractmethod
    def _remove_instances(self):
        raise NotImplementedError

    def remove_igw(self):
        with self.save_exception_context():
            self._remove_igw()

    @abstractmethod
    def _remove_igw(self):
        raise NotImplementedError

    def remove_security_groups(self):
        with self.save_exception_context():
            self._remove_security_groups()

    @abstractmethod
    def _remove_security_groups(self):
        raise NotImplementedError

    def remove_subnets(self):
        with self.save_exception_context():
            self._remove_subnets()

    @abstractmethod
    def _remove_subnets(self):
        raise NotImplementedError

    def remove_peerings(self):
        with self.save_exception_context():
            self._remove_peerings()

    @abstractmethod
    def _remove_peerings(self):
        raise NotImplementedError

    def remove_blackhole_routes_mgt_vpc(self):
        with self.save_exception_context():
            self._remove_blackhole_routes_mgt_vpc()

    @abstractmethod
    def _remove_blackhole_routes_mgt_vpc(self):
        raise NotImplementedError

    def remove_custom_route_tables(self):
        with self.save_exception_context():
            self._remove_custom_route_tables()

    @abstractmethod
    def _remove_custom_route_tables(self):
        raise NotImplementedError

    def remove_traffic_mirror_elements(self):
        with self.save_exception_context():
            self._remove_traffic_mirror_elements()

    def _remove_traffic_mirror_elements(self):
        self._logger.info("Removing traffic mirror elements")
        self._vpc_service.delete_traffic_mirror_elements(
            self._aws_clients.ec2_client,
            self._reservation_id,
            self._logger,
        )

    def remove_vpc(self):
        with self.save_exception_context():
            self._remove_vpc()

    @abstractmethod
    def _remove_vpc(self):
        raise NotImplementedError


class CleanupSandboxInfraDynamicVpcStrategy(CleanupSandboxInfraAbsStrategy):
    def get_vpc(self) -> "Vpc":
        vpc = self._vpc_service.find_vpc_for_reservation(
            self._aws_clients.ec2_session, self._reservation_id
        )
        if not vpc:
            raise VpcNotFound(self._reservation_id)
        return vpc

    def _remove_instances(self):
        self._logger.info(f"Removing all instances in VPC '{self.vpc_name}'")
        self._vpc_service.delete_all_instances(self.vpc)

    def _remove_igw(self):
        self._logger.info(f"Remove all Internet Gateways in VPC '{self.vpc_name}'")
        self._vpc_service.remove_all_internet_gateways(self.vpc)

    def _remove_security_groups(self):
        self._logger.info(f"Remove all Security Groups in VPC '{self.vpc_name}'")
        self._vpc_service.remove_all_security_groups(self.vpc)

    def _remove_subnets(self):
        self._logger.info(f"Remove all subnets in VPC '{self.vpc_name}'")
        self._vpc_service.remove_all_subnets(self.vpc)

    def _remove_peerings(self):
        self._logger.info(f"Remove all peerings in VPC '{self.vpc_name}'")
        for peering in VpcPeeringHandler.yield_live_peerings(self.vpc):
            peering.delete()

    def _remove_blackhole_routes_mgt_vpc(self):
        mgmt_vpc = self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.aws_mgmt_vpc_id
        )
        mgmt_vpc_name = self._vpc_service.get_name(mgmt_vpc)
        self._logger.info(
            f"Remove blackhole routes in Management VPC '{mgmt_vpc_name}'"
        )
        self._vpc_service.delete_all_blackhole_routes(mgmt_vpc)

    def _remove_custom_route_tables(self):
        self._logger.info(f"Remove custom route tables in VPC '{self.vpc_name}'")
        self._vpc_service.remove_custom_route_tables(self.vpc)

    def _remove_vpc(self):
        self._logger.info(f"Remove VPC '{self.vpc_name}'")
        self._vpc_service.delete_vpc(self.vpc)


CleanupSandboxInfraStaticVpcStrategy = CleanupSandboxInfraDynamicVpcStrategy


class CleanupSandboxInfraSharedVpcStrategy(CleanupSandboxInfraAbsStrategy):
    def get_vpc(self) -> "Vpc":
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.shared_vpc_id
        )

    def _remove_instances(self):
        self._logger.info(
            f"Remove instances for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.delete_instances_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_igw(self):
        """In the Shared VPC mode we do not create/remove IGW."""
        pass

    def _remove_security_groups(self):
        self._logger.info(
            f"Remove security groups for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_security_groups_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_subnets(self):
        self._logger.info(
            f"Remove subnets for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_subnets_for_reservation(self.vpc, self._reservation_id)

    def _remove_peerings(self):
        """In the Shared VPC mode we do not create peering connections."""
        pass

    def _remove_blackhole_routes_mgt_vpc(self):
        """In the Shared VPC mode we do not create routes to Management VPC."""
        pass

    def _remove_custom_route_tables(self):
        self._logger.info(
            f"Remove route tables for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_route_tables_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_vpc(self):
        """In the Shared VPC mode we do not create the VPC."""
        pass


class CleanupSandboxInfraSingleVpcStrategy(CleanupSandboxInfraAbsStrategy):
    def get_vpc(self) -> "Vpc":
        return self._vpc_service.get_vpc_by_id(
            self._aws_clients.ec2_session, self._aws_model.aws_mgmt_vpc_id
        )

    def _remove_instances(self):
        self._logger.info(
            f"Remove instances for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.delete_instances_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_igw(self):
        """In the Single VPC mode we do not create/remove IGW."""
        pass

    def _remove_security_groups(self):
        self._logger.info(
            f"Remove security groups for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_security_groups_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_subnets(self):
        self._logger.info(
            f"Remove subnets for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_subnets_for_reservation(self.vpc, self._reservation_id)

    def _remove_peerings(self):
        """In the Single VPC mode we do not create peering connections."""

    def _remove_blackhole_routes_mgt_vpc(self):
        """In the Shared VPC mode we do not create routes to Management VPC."""

    def _remove_custom_route_tables(self):
        self._logger.info(
            f"Remove route tables for reservation {self._reservation_id} "
            f"in VPC '{self.vpc_name}'"
        )
        self._vpc_service.remove_route_tables_for_reservation(
            self.vpc, self._reservation_id
        )

    def _remove_vpc(self):
        """In the Single VPC mode we do not create the VPC."""


STRATEGIES = {
    VpcMode.DYNAMIC: CleanupSandboxInfraDynamicVpcStrategy,
    VpcMode.STATIC: CleanupSandboxInfraStaticVpcStrategy,
    VpcMode.SHARED: CleanupSandboxInfraSharedVpcStrategy,
    VpcMode.SINGLE: CleanupSandboxInfraSingleVpcStrategy,
}


def get_strategy(
    vpc_service: "VPCService",
    key_pair_service: "KeyPairService",
    aws_clients: "AwsApiClients",
    aws_model: "AWSEc2CloudProviderResourceModel",
    reservation_id: "str",
    logger: "Logger",
) -> CleanupSandboxInfraAbsStrategy:
    # noinspection PyArgumentList
    return STRATEGIES[aws_model.vpc_mode](  # pycharm fails to get correct params
        vpc_service,
        key_pair_service,
        aws_clients,
        aws_model,
        reservation_id,
        logger,
    )
