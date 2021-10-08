from botocore.exceptions import ClientError

from cloudshell.cp.aws.domain.handlers.ec2 import IsolationTagValue, TagsHandler


class DeleteAMIOperation:
    def __init__(
        self,
        instance_service,
        ec2_storage_service,
        security_group_service,
        elastic_ip_service,
    ):
        """# noqa
        :param instance_service:
        :type instance_service: cloudshell.cp.aws.domain.services.ec2.instance.InstanceService
        :param ec2_storage_service:
        :type ec2_storage_service: cloudshell.cp.aws.domain.services.ec2.ebs.EC2StorageService
        :param security_group_service:
        :type security_group_service: cloudshell.cp.aws.domain.services.ec2.security_group.SecurityGroupService
        :param ElasticIpService elastic_ip_service:
        """
        self.instance_service = instance_service
        self.ec2_storage_service = ec2_storage_service
        self.security_group_service = security_group_service
        self.elastic_ip_service = elastic_ip_service

    def delete_instance(self, logger, ec2_session, instance_id):
        """# noqa
        Will terminate the instance safely
        :param logging.Logger logger:
        :param ec2_session: ec2 sessoion
        :param instance_id: the id if the instance
        :type instance_id: str
        :return:
        """
        try:
            self._delete(ec2_session, instance_id)
        except ClientError as clientErr:
            error = "Error"
            code = "Code"
            is_malformed = (
                error in clientErr.response
                and code in clientErr.response[error]
                and (
                    clientErr.response[error][code] == "InvalidInstanceID.Malformed"
                    or clientErr.response[error][code] == "InvalidInstanceID.NotFound"
                )
            )

            if not is_malformed:
                raise
            else:
                logger.info(f"Aws instance {instance_id} was already terminated")
                return

    def _delete(self, ec2_session, instance_id):
        """# noqa
        Will terminate the instance
        :param ec2_session: ec2 sessoion
        :param instance_id: the id if the instance
        :type instance_id: str
        :return:
        """
        instance = self.instance_service.get_instance_by_id(ec2_session, instance_id)

        # get the security groups before we delete the instance
        try:
            security_groups_description = instance.security_groups
            # in case we have exception the resource is already deleted
        except Exception:
            return True

        vpc_addresses = list(instance.vpc_addresses.all())

        self.instance_service.terminate_instance(instance)

        for address in vpc_addresses:
            self.elastic_ip_service.release_elastic_address(address)

        # find the exclusive security groups of the instance and delete them
        if security_groups_description:
            for sg_description in security_groups_description:
                security_group = ec2_session.SecurityGroup(sg_description["GroupId"])
                tags = TagsHandler.from_tags_list(security_group.tags)
                if tags.get_isolation() is IsolationTagValue.EXCLUSIVE:
                    self.security_group_service.delete_security_group(security_group)

        return True
