from typing import TYPE_CHECKING

import attr

from cloudshell.cp.core.models import CleanupNetwork

from cloudshell.cp.aws.domain.services.strategy.cleanup import get_strategy

if TYPE_CHECKING:
    from logging import Logger

    from cloudshell.cp.aws.domain.services.ec2.keypair import KeyPairService
    from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService
    from cloudshell.cp.aws.models.aws_api import AwsApiClients
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )


@attr.s(auto_attribs=True)
class CleanupSandboxInfraOperation:
    vpc_service: "VPCService"
    key_pair_service: "KeyPairService"

    def cleanup(
        self,
        aws_clients: "AwsApiClients",
        aws_model: "AWSEc2CloudProviderResourceModel",
        reservation_id: str,
        actions: list,
        logger: "Logger",
    ):
        if not actions:
            raise ValueError("No cleanup action was found")

        result = CleanupNetwork()
        result.actionId = actions[0].actionId
        result.success = True
        strategy = get_strategy(
            self.vpc_service,
            self.key_pair_service,
            aws_clients,
            aws_model,
            reservation_id,
            logger,
        )

        try:
            strategy.cleanup()
        except Exception as exc:
            logger.exception("Error in cleanup connectivity")
            result.success = False
            result.errorMessage = f"CleanupSandboxInfra ended with the error: {exc}"
        return result
