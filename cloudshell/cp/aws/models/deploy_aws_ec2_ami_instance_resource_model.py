import json
from typing import Dict

from cloudshell.cp.aws.common.converters import attribute_getter
from cloudshell.cp.aws.domain.services.parsers.aws_model_parser import AWSModelsParser


class DeployAWSEc2AMIInstanceResourceModel:
    __deploymentModel__ = "Amazon AWS Cloud Provider 2G.Amazon AWS EC2 Instance 2G"

    def __init__(
        self, attributes
    ):  # todo handle the c=initialization of the object from the attributes
        self.user_data_url = ""
        self.user_data_run_parameters = ""

        self.custom_tags = ""
        self.cloud_provider = ""
        self.aws_ami_id = ""
        self.storage_size = ""
        self.storage_iops = ""
        # the storage type can be one of these: 'standard'|'io1'|'gp2'|'sc1'|'st1'
        self.storage_type = ""  # type: str
        self.min_count = 0  # type: int
        self.max_count = 0  # type: int
        self.instance_type = ""  # type: str
        self.iam_role = ""  # type: str
        self.security_group_ids = None  # type: str
        self.private_ip_address = ""  # type: str
        self.private_ip_addresses_dict = None  # type: Dict
        self.root_volume_name = ""  # type: str
        self.delete_on_termination = True  # type: bool
        self.auto_power_off = False  # type: bool
        self.wait_for_ip = False  # type: bool
        self.wait_for_status_check = False  # type: bool
        self.auto_delete = False  # type: bool
        self.autoload = False  # type: bool
        self.outbound_ports = ""  # type: str
        self.inbound_ports = ""  # type: str
        self.wait_for_credentials = ""  # type: str
        self.add_public_ip = False  # type: bool
        self.allocate_elastic_ip = False  # type: bool
        self.network_configurations = None  # type: list["NetworkAction"]  # noqa
        self.allow_all_sandbox_traffic = True  # type: bool

        get_attr = attribute_getter(attributes, self.__deploymentModel__)
        self.aws_ami_id = get_attr("AWS AMI Id")
        self.allow_all_sandbox_traffic = get_attr("Allow all Sandbox Traffic", bool)
        self.storage_size = get_attr("Storage Size")
        self.storage_iops = get_attr("Storage IOPS")
        self.storage_type = get_attr("Storage Type")
        self.instance_type = get_attr("Instance Type")
        self.iam_role = get_attr("IAM Role Name")
        self.root_volume_name = get_attr("Root Volume Name")
        self.wait_for_ip = get_attr("Wait for IP", bool)
        self.wait_for_status_check = get_attr("Wait for Status Check", bool)
        self.status_check_timeout = get_attr("Status Check Timeout", int, 0)
        self.autoload = get_attr("Autoload", bool)
        self.inbound_ports = get_attr("Inbound Ports")
        self.wait_for_credentials = get_attr("Wait for Credentials", bool)
        (
            self.add_public_ip,
            self.allocate_elastic_ip,
        ) = AWSModelsParser.parse_public_ip_options_attribute(
            get_attr("Public IP Options")
        )
        self.custom_tags = get_attr("Custom Tags")
        self.user_data_url = get_attr("User Data URL")
        self.user_data_run_parameters = get_attr("User Data Parameters")
        self.enable_source_dest_check = get_attr("Enable Source Dest Check", bool, True)

        private_ip_att_value = get_attr("Private IP")
        self.private_ip_address = self._get_primary_private_ip_address(
            private_ip_att_value
        )
        self.private_ip_addresses_dict = self._get_private_ip_addresses_dict(
            private_ip_att_value
        )

    def _get_private_ip_addresses_dict(self, private_ip_address):
        try:
            # if dict of private ip address then we take the first as the primary
            return json.loads(private_ip_address)
        except Exception:
            return None

    def _get_primary_private_ip_address(self, private_ip_address):
        try:
            # if dict of private ip address then we take the first as the primary
            return json.loads(private_ip_address).values()[0]
        except Exception:
            return private_ip_address or None
