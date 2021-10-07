from unittest import TestCase
from unittest.mock import Mock

import jsonpickle

from cloudshell.cp.aws.common.deploy_data_holder import DeployDataHolder
from cloudshell.cp.aws.domain.deployed_app.operations.app_ports_operation import (
    DeployedAppPortsOperation,
)
from cloudshell.cp.aws.domain.services.parsers.custom_param_extractor import (
    VmCustomParamsExtractor,
)


class TestDeployedAppPortsOperation(TestCase):
    def setUp(self):
        self.security_group_service = Mock()
        self.instance_service = Mock()
        self.operation = DeployedAppPortsOperation(
            VmCustomParamsExtractor(),
            self.security_group_service,
            self.instance_service,
        )

    def test_format_single_inbound(self):
        json_str = '{"vmCustomParams":[{"name": "inbound_ports", "value": "80"}]}'
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(result, "Inbound ports:\nPort 80 tcp")

    def test_format_complex_inbound(self):
        json_str = (
            '{"vmCustomParams":[{"name": "inbound_ports", '
            '"value": "80; 1200-2300:udp; 26:tcp"}]}'
        )
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(
            result, "Inbound ports:\nPort 80 tcp\nPorts 1200-2300 udp\nPort 26 tcp"
        )

    def test_format_single_outbound(self):
        json_str = '{"vmCustomParams":[{"name": "outbound_ports", "value": "80"}]}'
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(result, "Outbound ports:\nPort 80 tcp")

    def test_format_complex_outbound(self):
        json_str = (
            '{"vmCustomParams":[{"name": "Outbound_ports", '
            '"value": "80; 1200-2300:udp; 26:tcp"}]}'
        )
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(
            result, "Outbound ports:\nPort 80 tcp\nPorts 1200-2300 udp\nPort 26 tcp"
        )

    def test_format_complex_inbound_and_outbound(self):
        json_str = (
            '{"vmCustomParams":['
            '{"name": "inbound_ports", "value": "80; 1200-2300:udp; 26:tcp"},'
            '{"name": "Outbound_ports", "value": "1433; 3000-3010:udp; 30:tcp; 26:udp"'
            "}]}"
        )
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(
            result,
            "Inbound ports:\nPort 80 tcp\nPorts 1200-2300 udp\nPort 26 tcp\n\n"
            "Outbound ports:\nPort 1433 tcp\nPorts 3000-3010 udp\nPort 30 tcp\n"
            "Port 26 udp",
        )

    def test_no_inbound_or_outbound_ports(self):
        json_str = '{"vmCustomParams":[]}'
        dict_ = jsonpickle.decode(json_str)
        vmdetails = DeployDataHolder(dict_)

        result = self.operation.get_formated_deployed_app_ports(
            vmdetails.vmCustomParams
        )

        self.assertEqual(
            result,
            "No ports are open for inbound and outbound traffic outside of the Sandbox",
        )

    def test_get_app_ports_from_cloud_provider(self):
        instance = Mock()
        instance.network_interfaces = []
        instance.subnet = Mock()

        name_dict = {"Key": "Name", "Value": "Just a name"}
        reservation_id_dict = {"Key": "ReservationId", "Value": "Reservation Id"}
        instance.subnet.tags = [name_dict, reservation_id_dict]

        self.instance_service.get_active_instance_by_id = Mock(return_value=instance)

        remote_resource = Mock()
        remote_resource.fullname = "my ami name"

        es2_session = Mock()

        result = self.operation.get_app_ports_from_cloud_provider(
            ec2_session=es2_session,
            instance_id="",
            resource=remote_resource,
            allow_all_storage_traffic=True,
        )

        self.assertEqual(result, "App Name: my ami name\nAllow Sandbox Traffic: True")
