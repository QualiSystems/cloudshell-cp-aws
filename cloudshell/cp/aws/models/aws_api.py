from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource  # noqa: I900
    from mypy_boto3_s3 import S3ServiceResource  # noqa: I900


class AwsApiClients:
    def __init__(
        self,
        ec2_session: "EC2ServiceResource",
        s3_session: "S3ServiceResource",
        ec2_client: "EC2Client",
        default_ec2_session: "EC2ServiceResource",
    ):
        """Api clients.

        If we work in Shared VPC mode ec2_session and ec2_client would be created
        based on the Shared role and would work with Shared account but S3 would be
        work with management account

        :param ec2_session: could be session created based on the ES role or on
            the Shared role
        :param default_ec2_session: always session created based on the ES role
        :param s3_session: s3 session created based on the ES role
        :param ec2_client: ec2 client could be created based on the ES role or on
            the Shared role
        """
        self.ec2_session = ec2_session
        self.s3_session = s3_session
        self.ec2_client = ec2_client
        self.default_ec2_session = default_ec2_session
