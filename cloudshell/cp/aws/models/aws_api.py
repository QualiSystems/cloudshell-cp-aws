from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource
    from mypy_boto3_s3 import S3ServiceResource


class AwsApiClients:
    def __init__(
        self,
        ec2_session: "EC2ServiceResource",
        s3_session: "S3ServiceResource",
        ec2_client: "EC2Client",
    ):
        self.ec2_session = ec2_session
        self.s3_session = s3_session
        self.ec2_client = ec2_client
