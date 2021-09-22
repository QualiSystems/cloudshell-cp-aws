import netaddr
from botocore.exceptions import ClientError

from cloudshell.shell.core.driver_context import AutoLoadDetails

from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode


class AutoloadOperation:
    def get_inventory(
        self, cloud_provider_model, logger, ec2_client, ec2_session, s3_session
    ):
        """Check that all needed resources are valid and present on the Azure.

        :param cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model.AWSEc2CloudProviderResourceModel cloud_provider_model:  instance  # noqa
        :param logger: logging.Logger instance
        :return: cloudshell.shell.core.driver_context.AutoLoadDetails instance
        """
        logger.info("Starting Autoload Operation...")

        if cloud_provider_model.vpc_mode is not VpcMode.SHARED:
            self._validate_management_security_group(
                cloud_provider_model, ec2_client, logger
            )

        # removed for now
        # self._validate_keypair_location_in_s3(cloud_provider_model, logger, s3_session) # noqa

        self._validate_vpc_cidr(cloud_provider_model.static_vpc_cidr, logger)

        return AutoLoadDetails([], [])

    def _validate_management_security_group(
        self, cloud_provider_model, ec2_client, logger
    ):
        logger.info("Validate management security group")
        management_sg_id = cloud_provider_model.aws_mgmt_sg_id
        if management_sg_id == "":
            return
        try:
            response = ec2_client.describe_security_groups(
                GroupIds=[str(management_sg_id)]
            )
            management_sg_id_found = any(
                sg.get("GroupId")
                for sg in response.get("SecurityGroups", [])
                if sg.get("GroupId") == management_sg_id
            )
            if not management_sg_id_found:
                raise AutoloadException(
                    f"Was not able to find the AWS management security group with "
                    f"id {management_sg_id}"
                )
            logger.info(response)

        except ClientError as e:
            logger.exception(e)
            raise AutoloadException(
                f"Was not able to find the AWS management security group with "
                f"id {management_sg_id}"
            )

    def _validate_keypair_location_in_s3(
        self, cloud_provider_model, logger, s3_session
    ):
        logger.info("Checking if keypair storage in S3 exists")
        bucket = s3_session.Bucket(cloud_provider_model.key_pairs_location)
        if not bucket.creation_date:
            raise AutoloadException("Key pairs location not found in S3")

    def _validate_cidr_format(self, cidr, logger):
        """Validate that CIDR have a correct format. Example "10.10.10.10/24".

        :param str cidr:
        :param logging.Logger logger:
        :return: True/False whether CIDR is valid or not
        :rtype: bool
        """
        try:
            netaddr.IPNetwork(cidr)
        except netaddr.AddrFormatError:
            logger.info(f"CIDR {cidr} is in invalid format", exc_info=True)
            return False
        if "/" not in cidr:
            return False

        return True

    def _validate_vpc_cidr(self, vpc_cidr, logger):
        """Verify "Additional Mgmt Networks" attribute.

        :param str vpc_cidr: for example "10.10.10.10/24"
        :param logging.Logger logger:
        :return:
        """
        valid = vpc_cidr == "" or self._validate_cidr_format(vpc_cidr, logger)
        if not valid:
            raise Exception(
                'CIDR {} entered in "VPC CIDR" attribute is not '
                "in the valid format".format(vpc_cidr)
            )


class AutoloadException(Exception):
    pass
