import configparser
import os
from typing import TYPE_CHECKING

import boto3

from cloudshell.api.cloudshell_api import CloudShellAPISession

from cloudshell.cp.aws.models.aws_api import AwsApiClients
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode

if TYPE_CHECKING:
    from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import (
        AWSEc2CloudProviderResourceModel,
    )


class AWSSessionProvider:
    EC2 = "ec2"
    S3 = "s3"

    def __init__(self):
        self.test_cred_path = os.path.join(os.path.dirname(__file__), "test_cred.ini")
        if not os.path.isfile(self.test_cred_path):
            self.test_cred_path = ""

    def get_clients(
        self,
        cloudshell_session: "CloudShellAPISession",
        aws_ec2_data_model: "AWSEc2CloudProviderResourceModel",
    ) -> AwsApiClients:
        default_session = self._get_aws_session(aws_ec2_data_model, cloudshell_session)
        if not default_session:
            raise ValueError("Could not create AWS Session")

        if aws_ec2_data_model.vpc_mode is VpcMode.SHARED:
            aws_ec2_session = self._assume_shared_vpc_role(
                default_session, aws_ec2_data_model
            )
        else:
            aws_ec2_session = default_session

        return AwsApiClients(
            ec2_session=aws_ec2_session.resource(self.EC2),
            s3_session=default_session.resource(self.S3),
            ec2_client=aws_ec2_session.client(self.EC2),
            default_ec2_session=default_session.resource(self.EC2),
        )

    def get_s3_session(self, cloudshell_session, aws_ec2_data_model):
        aws_session = self._get_aws_session(aws_ec2_data_model, cloudshell_session)

        if not aws_session:
            raise ValueError("Could not create AWS Session")
        return aws_session.resource(self.S3)

    def get_ec2_session(self, cloudshell_session, aws_ec2_data_model):
        aws_session = self._get_aws_session(aws_ec2_data_model, cloudshell_session)

        if not aws_session:
            raise ValueError("Could not create AWS Session")
        return aws_session.resource(self.EC2)

    def get_ec2_client(self, cloudshell_session, aws_ec2_data_model):
        aws_session = self._get_aws_session(aws_ec2_data_model, cloudshell_session)

        if not aws_session:
            raise ValueError("Could not create AWS Client")
        return aws_session.client(self.EC2)

    def _get_aws_session(
        self,
        aws_ec2_data_model: "AWSEc2CloudProviderResourceModel",
        cloudshell_session: "CloudShellAPISession",
    ):
        credentials = self._get_aws_credentials(cloudshell_session, aws_ec2_data_model)
        aws_session = self._create_aws_session(aws_ec2_data_model, credentials)
        return aws_session

    @staticmethod
    def _create_aws_session(aws_ec2_data_model, credentials):
        if not credentials:
            aws_session = boto3.session.Session(region_name=aws_ec2_data_model.region)
        else:
            aws_session = boto3.session.Session(
                aws_access_key_id=credentials.access_key_id,
                aws_secret_access_key=credentials.secret_access_key,
                region_name=aws_ec2_data_model.region,
            )
        return aws_session

    @staticmethod
    def _assume_shared_vpc_role(
        aws_session, aws_ec2_data_model: "AWSEc2CloudProviderResourceModel"
    ):
        endpoint_url = f"https://sts.{aws_ec2_data_model.region}.amazonaws.com"
        sts = aws_session.client("sts", endpoint_url=endpoint_url)
        data = sts.assume_role(
            RoleArn=aws_ec2_data_model.shared_vpc_role_arn,
            RoleSessionName="CS-SharedVPC-Session",
        )
        credentials = data["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=aws_ec2_data_model.region,
        )
        return session

    def _get_aws_credentials(self, cloudshell_session=None, aws_ec2_data_model=None):
        if self.test_cred_path:
            return self._get_test_credentials()
        if (
            cloudshell_session
            and aws_ec2_data_model.aws_access_key_id
            and aws_ec2_data_model.aws_secret_access_key
        ):
            return AWSCredentials(
                self._decrypt_key(
                    cloudshell_session, aws_ec2_data_model.aws_access_key_id
                ),
                self._decrypt_key(
                    cloudshell_session, aws_ec2_data_model.aws_secret_access_key
                ),
            )
        return None

    def _get_test_credentials(self):
        config = configparser.ConfigParser()
        config_path = self.test_cred_path
        config.read_file(open(config_path))
        return AWSCredentials(
            config.get("Credentials", "Access Key ID"),
            config.get("Credentials", "Secret Access Key"),
        )

    @staticmethod
    def _decrypt_key(cloudshell_session, field):
        return cloudshell_session.DecryptPassword(field).Value


class AWSCredentials:
    def __init__(self, key_id, access_key):
        self.access_key_id = key_id
        self.secret_access_key = access_key
