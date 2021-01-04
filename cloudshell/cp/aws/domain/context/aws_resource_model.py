from cloudshell.shell.core.driver_context import ResourceCommandContext

from cloudshell.cp.aws.domain.services.parsers.aws_model_parser import AWSModelsParser
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
    AWSEc2CloudProviderResourceModel,
)


class AwsResourceModelContext:
    def __init__(self, context: ResourceCommandContext, model_parser: AWSModelsParser):
        self.context = context
        self.model_parser = model_parser

    def __enter__(self) -> AWSEc2CloudProviderResourceModel:
        return self.model_parser.convert_to_aws_resource_model(self.context.resource)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
