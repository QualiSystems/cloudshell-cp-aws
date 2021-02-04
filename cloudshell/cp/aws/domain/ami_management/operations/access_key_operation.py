class GetAccessKeyOperation:
    def __init__(self, key_pair_service):
        """# noqa
        :param KeyPairService key_pair_service:
        :return:
        """
        self.key_pair_service = key_pair_service

    def get_access_key(self, s3_session, aws_ec2_resource_model, reservation_id):
        """# noqa
        Returns the content of the pem file stores in s3 for the given reservation
        :param s3_session:
        :param AWSEc2CloudProviderResourceModel aws_ec2_resource_model: The resource model of the AMI deployment option
        :param str reservation_id:
        :return:
        """
        return self.key_pair_service.load_key_pair_by_name(
            s3_session=s3_session,
            bucket_name=aws_ec2_resource_model.key_pairs_location,
            reservation_id=reservation_id,
        )
