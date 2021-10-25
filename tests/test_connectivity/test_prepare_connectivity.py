from unittest import TestCase
from unittest.mock import Mock

from cloudshell.cp.core.models import (
    CreateKeys,
    PrepareCloudInfra,
    PrepareCloudInfraParams,
    PrepareSubnet,
    PrepareSubnetParams,
)

from cloudshell.cp.aws.domain.conncetivity.operations.prepare import (
    PrepareSandboxInfraOperation,
)
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode


class TestPrepareSandboxInfra(TestCase):
    def setUp(self):
        self.vpc_serv = Mock()
        self.vpc_serv.get_all_internet_gateways = Mock(return_value=[])

        self.sg_serv = Mock()
        self.key_pair_serv = Mock()
        self.aws_clients = Mock()
        self.ec2_session = Mock()
        self.default_ec2_session = Mock()
        self.ec2_client = Mock()
        self.s3_session = Mock()
        self.aws_dm = Mock()
        self.aws_dm.vpc_mode = VpcMode.DYNAMIC
        self.reservation = Mock()
        self.route_table_service = Mock()
        self.cancellation_service = Mock()
        self.cancellation_context = Mock(is_cancelled=False)
        self.subnet_service = Mock()
        self.subnet_waiter = Mock()
        self.cs_subnet_service = Mock()
        self.logger = Mock()
        self.prepare_conn = PrepareSandboxInfraOperation(
            self.vpc_serv,
            self.sg_serv,
            self.key_pair_serv,
            self.subnet_service,
            self.subnet_waiter,
        )

    def test_prepare_conn_must_receive_network_action(self):
        with self.assertRaisesRegex(
            Exception, "Actions list must contain a PrepareCloudInfraAction."
        ):
            self.prepare_conn.prepare_connectivity(
                aws_clients=self.aws_clients,
                reservation=self.reservation,
                aws_model=self.aws_dm,
                actions=[PrepareSubnet()],
                cancellation_context=self.cancellation_context,
                cs_subnet_service=self.cs_subnet_service,
                logger=self.logger,
            )

    def test_prepare_conn_execute_the_network_action_first(self):
        # Arrage
        actions = []
        prepare_subnet_sub_a = PrepareSubnet()
        prepare_subnet_sub_a.actionId = "SubA"
        prepare_subnet_sub_a.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_a)
        prepare_cloud_infra = PrepareCloudInfra()
        prepare_cloud_infra.actionId = "Net"
        prepare_cloud_infra.actionParams = PrepareCloudInfraParams()
        actions.append(prepare_cloud_infra)
        prepare_subnet_sub_b = PrepareSubnet()
        prepare_subnet_sub_b.actionId = "SubB"
        prepare_subnet_sub_b.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_b)
        prepare_create_key = CreateKeys()
        prepare_create_key.actionId = "CreateKeys"
        actions.append(prepare_create_key)
        # Act
        results = self.prepare_conn.prepare_connectivity(
            aws_clients=self.aws_clients,
            reservation=self.reservation,
            aws_model=self.aws_dm,
            actions=actions,
            cancellation_context=self.cancellation_context,
            cs_subnet_service=self.cs_subnet_service,
            logger=self.logger,
        )
        # Assert
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0].actionId, "Net")
        self.assertEqual(results[1].actionId, "CreateKeys")
        self.assertEqual(results[2].actionId, "SubA")
        self.assertEqual(results[3].actionId, "SubB")

    def test_prepare_conn_execute_the_subnet_actions(self):
        # Arrage
        actions = []
        prepare_subnet_sub_a = PrepareSubnet()
        prepare_subnet_sub_a.actionId = "SubA"
        prepare_subnet_sub_a.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_a)
        prepare_cloud_infra = PrepareCloudInfra()
        prepare_cloud_infra.actionId = "Net"
        prepare_cloud_infra.actionParams = PrepareCloudInfraParams()
        actions.append(prepare_cloud_infra)
        prepare_subnet_sub_b = PrepareSubnet()
        prepare_subnet_sub_b.actionId = "SubB"
        prepare_subnet_sub_b.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_b)
        prepare_create_key = CreateKeys()
        prepare_create_key.actionId = "CreateKeys"
        actions.append(prepare_create_key)
        self.prepare_conn._prepare_subnets = lambda *args, **kwargs: ["ResA", "ResB"]
        # Act
        results = self.prepare_conn.prepare_connectivity(
            aws_clients=self.aws_clients,
            reservation=self.reservation,
            aws_model=self.aws_dm,
            actions=actions,
            cancellation_context=self.cancellation_context,
            cs_subnet_service=self.cs_subnet_service,
            logger=self.logger,
        )
        # Assert
        self.assertEqual(len(results), 4)
        self.assertEqual(results[2], "ResA")
        self.assertEqual(results[3], "ResB")

    def test_prepare_conn_command_no_management_vpc(self):
        aws_dm = Mock()
        cancellation_context = Mock()
        aws_dm.aws_mgmt_vpc_id = None
        with self.assertRaises(ValueError):
            self.prepare_conn.prepare_connectivity(
                self.aws_clients,
                self.reservation,
                aws_dm,
                [],
                cancellation_context,
                self.cs_subnet_service,
                self.logger,
            )

    def test_prepare_conn_error_no_vpc(self):
        self.vpc_serv.find_vpc_for_reservation = Mock(return_value=None)
        self.vpc_serv.get_active_vpcs_count = Mock(return_value=None)

        # Arrage
        actions = []
        prepare_subnet_sub_a = PrepareSubnet()
        prepare_subnet_sub_a.actionId = "SubA"
        prepare_subnet_sub_a.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_a)
        prepare_cloud_infra = PrepareCloudInfra()
        prepare_cloud_infra.actionId = "Net"
        prepare_cloud_infra.actionParams = PrepareCloudInfraParams()
        actions.append(prepare_cloud_infra)
        prepare_subnet_sub_b = PrepareSubnet()
        prepare_subnet_sub_b.actionId = "SubB"
        prepare_subnet_sub_b.actionParams = PrepareSubnetParams()
        actions.append(prepare_subnet_sub_b)

        # Assert
        with self.assertRaisesRegex(ValueError, "^((?!limit).)*$"):
            self.prepare_conn.prepare_connectivity(
                aws_clients=self.aws_clients,
                reservation=self.reservation,
                aws_model=self.aws_dm,
                actions=actions,
                cancellation_context=self.cancellation_context,
                cs_subnet_service=self.cs_subnet_service,
                logger=self.logger,
            )

    def test_prepare_conn_command_fault_res(self):
        self.aws_dm.is_static_vpc_mode = False

        action = PrepareCloudInfra()
        action.actionId = "1234"
        action.actionParams = PrepareCloudInfraParams()
        action.actionParams.cidr = "1.2.3.4/24"
        action2 = CreateKeys()
        action2.actionId = "123"
        cancellation_context = Mock()

        results = self.prepare_conn.prepare_connectivity(
            aws_clients=self.aws_clients,
            reservation=self.reservation,
            aws_model=self.aws_dm,
            actions=[action, action2],
            cancellation_context=cancellation_context,
            cs_subnet_service=self.cs_subnet_service,
            logger=self.logger,
        )

        self.assertFalse(results[0].success)
        self.assertEqual(results[0].infoMessage, "")
        self.assertIsNotNone(results[0].errorMessage)

    def test_create_key_pair(self):
        key_pair_service = Mock()
        key_pair_service.load_key_pair_by_name = Mock(return_value=None)
        prepare_conn = PrepareSandboxInfraOperation(
            self.vpc_serv,
            self.sg_serv,
            key_pair_service,
            self.subnet_service,
            self.subnet_waiter,
        )
        key_pair = Mock()
        key_pair_service.create_key_pair = Mock(return_value=key_pair)

        access_key = prepare_conn._get_or_create_key_pair(
            self.ec2_session, self.s3_session, "bucket", "res_id"
        )

        key_pair_service.load_key_pair_by_name.assert_called_once_with(
            s3_session=self.s3_session, bucket_name="bucket", reservation_id="res_id"
        )
        key_pair_service.create_key_pair.assert_called_once_with(
            ec2_session=self.ec2_session,
            s3_session=self.s3_session,
            bucket="bucket",
            reservation_id="res_id",
        )
        self.assertEqual(access_key, key_pair.key_material)
