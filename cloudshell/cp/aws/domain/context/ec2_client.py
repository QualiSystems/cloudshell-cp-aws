class EC2ClientContext:
    def __init__(self, aws_session_manager, cloudshell_session, aws_ec2_resource_model):
        """# noqa
        Initializes an instance of EC2ClientContext
        :param aws_session_manager:
        :type aws_session_manager: AWSSessionProvider
        :param cloudshell_session:
        :type: cloudshell_session: CloudShellAPISession
        :param aws_ec2_resource_model:
        :type aws_ec2_resource_model: AWSEc2CloudProviderResourceModel
        """
        self.aws_session_manager = aws_session_manager
        self.cloudshell_session = cloudshell_session
        self.aws_ec2_resource_model = aws_ec2_resource_model

    def __enter__(self):
        """# noqa
        Initializes aws ec2 client instance
        :return: Subclass of :py:class:`~boto3.resources.base.ServiceResource`
        :rtype EC2.Client:
        """
        return self.aws_session_manager.get_ec2_client(
            cloudshell_session=self.cloudshell_session,
            aws_ec2_data_model=self.aws_ec2_resource_model,
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        """# noqa
        Called upon end of the context. Does nothing
        :param exc_type: Exception type
        :param exc_val: Exception value
        :param exc_tb: Exception traceback
        :return:
        """
        pass
