from typing import TYPE_CHECKING, List

import attr
import jsonpickle

from cloudshell.cp.core.models import (
    ActionResultBase,
    CreateKeys,
    CreateKeysActionResult,
    PrepareCloudInfra,
    PrepareCloudInfraResult,
    PrepareSubnet,
    RequestActionBase,
)

from cloudshell.cp.aws.domain.services.strategy.prepare_cloud_infra import (
    get_prepare_infra_strategy,
)
from cloudshell.cp.aws.domain.services.strategy.prepare_subnets import (
    get_prepare_subnet_strategy,
)

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2ServiceResource  # noqa: I900
    from mypy_boto3_s3 import S3ServiceResource  # noqa: I900

    from cloudshell.shell.core.driver_context import CancellationContext

    from cloudshell.cp.aws.domain.services.cloudshell.cs_subnet_service import (
        CsSubnetService,
    )
    from cloudshell.cp.aws.domain.services.ec2.keypair import KeyPairService
    from cloudshell.cp.aws.domain.services.ec2.security_group import (
        SecurityGroupService,
    )
    from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.domain.services.waiters.subnet import SubnetWaiter
    from cloudshell.cp.aws.models.aws_api import AwsApiClients
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )
    from cloudshell.cp.aws.models.reservation_model import ReservationModel


@attr.s(auto_attribs=True)
class PrepareSandboxInfraOperation:
    vpc_service: "VPCService"
    security_group_service: "SecurityGroupService"
    key_pair_service: "KeyPairService"
    subnet_service: "SubnetService"
    subnet_waiter: "SubnetWaiter"

    def prepare_connectivity(
        self,
        aws_clients: "AwsApiClients",
        reservation: "ReservationModel",
        aws_model: "AWSEc2CloudProviderResourceModel",
        actions: List["RequestActionBase"],
        cancellation_context: "CancellationContext",
        cs_subnet_service: "CsSubnetService",
        logger: "Logger",
    ):
        actions_str = ",".join([jsonpickle.encode(a) for a in actions])
        logger.info(f"PrepareSandboxInfra actions: {actions_str}")
        results = []

        # Execute PrepareCloudInfra action first
        network_action = next(
            (a for a in actions if isinstance(a, PrepareCloudInfra)), None
        )
        create_keys_action = next(
            (a for a in actions if isinstance(a, CreateKeys)), None
        )
        if not network_action:
            raise ValueError("Actions list must contain a PrepareCloudInfraAction.")
        if not create_keys_action:
            raise ValueError("Actions list must contain a CreateKeys.")

        try:
            result = self._prepare_network(
                aws_clients,
                reservation,
                aws_model,
                network_action,
                cancellation_context,
                logger,
            )
            results.append(result)
        except Exception as e:
            logger.exception("Error in prepare connectivity.")
            results.append(self._create_fault_action_result(network_action, e))

        try:
            result = self._prepare_key(
                aws_clients,
                aws_model,
                reservation,
                create_keys_action,
                logger,
            )
            results.append(result)
        except Exception as e:
            logger.exception("Error in prepare key.")
            results.append(self._create_fault_action_result(create_keys_action, e))

        # Execute prepareSubnet actions
        subnet_actions = [a for a in actions if isinstance(a, PrepareSubnet)]
        try:
            subnet_results = self._prepare_subnets(
                cs_subnet_service,
                subnet_actions,
                aws_clients,
                aws_model,
                reservation,
                cancellation_context,
                logger,
            )
            results.extend(subnet_results)
        except Exception as e:
            logger.exception("Error in prepare subnets.")
            for action in subnet_actions:
                results.append(self._create_fault_action_result(action, e))

        logger.info("Prepare Connectivity completed")
        return results

    def _prepare_key(
        self,
        aws_clients: "AwsApiClients",
        aws_model: "AWSEc2CloudProviderResourceModel",
        reservation: "ReservationModel",
        action: "CreateKeys",
        logger: "Logger",
    ):
        logger.info("Get or create existing key pair")
        access_key = self._get_or_create_key_pair(
            ec2_session=aws_clients.ec2_session,
            s3_session=aws_clients.s3_session,
            bucket=aws_model.key_pairs_location,
            reservation_id=reservation.reservation_id,
        )
        return self._create_prepare_create_keys_result(action, access_key)

    def _prepare_network(
        self,
        aws_clients: "AwsApiClients",
        reservation: "ReservationModel",
        aws_model: "AWSEc2CloudProviderResourceModel",
        action: "PrepareCloudInfra",
        cancellation_context: "CancellationContext",
        logger: "Logger",
    ) -> "PrepareCloudInfraResult":
        strategy = get_prepare_infra_strategy(
            self.vpc_service,
            self.security_group_service,
            aws_clients,
            aws_model,
            reservation,
            action,
            cancellation_context,
            logger,
        )
        return strategy.prepare()

    def _get_or_create_key_pair(
        self,
        ec2_session: "EC2ServiceResource",
        s3_session: "S3ServiceResource",
        bucket: str,
        reservation_id: str,
    ) -> str:
        """Creates a keypair or retrieves an existing and returns the private key."""
        private_key = self.key_pair_service.load_key_pair_by_name(
            s3_session=s3_session, bucket_name=bucket, reservation_id=reservation_id
        )
        if not private_key:
            key_pair = self.key_pair_service.create_key_pair(
                ec2_session=ec2_session,
                s3_session=s3_session,
                bucket=bucket,
                reservation_id=reservation_id,
            )
            private_key = key_pair.key_material

        return private_key

    def _prepare_subnets(
        self,
        cs_subnet_service: "CsSubnetService",
        subnet_actions: List["PrepareSubnet"],
        aws_clients: "AwsApiClients",
        aws_models: "AWSEc2CloudProviderResourceModel",
        reservation: "ReservationModel",
        cancellation_context: "CancellationContext",
        logger: "Logger",
    ) -> List["PrepareCloudInfraResult"]:
        strategy = get_prepare_subnet_strategy(
            self.vpc_service,
            self.subnet_service,
            self.subnet_waiter,
            cs_subnet_service,
            self.security_group_service,
            subnet_actions,
            aws_clients,
            aws_models,
            reservation,
            cancellation_context,
            logger,
        )
        return strategy.prepare()

    @staticmethod
    def _create_prepare_create_keys_result(action, access_key):
        action_result = CreateKeysActionResult()
        action_result.actionId = action.actionId
        action_result.success = True
        action_result.infoMessage = "PrepareCreateKeys finished successfully"
        action_result.accessKey = access_key

        return action_result

    @staticmethod
    def _create_fault_action_result(action, e):
        action_result = ActionResultBase()
        action_result.actionId = action.actionId
        action_result.success = False
        action_result.errorMessage = f"PrepareSandboxInfra ended with the error: {e}"
        return action_result
