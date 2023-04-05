from unittest import TestCase
from unittest.mock import Mock

from cloudshell.cp.core.models import PrepareCloudInfra

from cloudshell.cp.aws.domain.conncetivity.operations.cleanup import (
    CleanupSandboxInfraOperation,
)
from cloudshell.cp.aws.models.aws_ec2_cloud_provider_resource_model import VpcMode


class TestCleanupSandboxInfra(TestCase):
    def setUp(self):
        self.vpc_serv = Mock()
        self.key_pair_serv = Mock()
        self.ec2_session = Mock()
        self.s3_session = Mock()
        self.ec2_client = Mock()
        self.aws_api_clients = Mock(
            ec2_session=self.ec2_session,
            s3_session=self.s3_session,
            ec2_client=self.ec2_client,
        )
        self.aws_model = Mock(vpc_mode=VpcMode.DYNAMIC)
        self.reservation_id = Mock()
        self.cleanup_operation = CleanupSandboxInfraOperation(
            self.vpc_serv,
            self.key_pair_serv,
        )
        self.logger = Mock()

    def test_cleanup(self):
        vpc = self.vpc_serv.find_vpc_for_reservation()

        self.cleanup_operation.cleanup(
            self.aws_api_clients,
            aws_model=self.aws_model,
            reservation_id=self.reservation_id,
            logger=self.logger,
            actions=[PrepareCloudInfra()],
        )

        self.assertTrue(
            self.vpc_serv.find_vpc_for_reservation.called_with(
                self.ec2_session, self.reservation_id
            )
        )
        self.assertTrue(
            self.key_pair_serv.remove_key_pair_for_reservation_in_s3.called_with(
                self.s3_session, self.aws_model, self.reservation_id
            )
        )
        self.assertTrue(self.vpc_serv.delete_all_instances.called_with(vpc))
        self.assertTrue(self.vpc_serv.remove_all_security_groups.called_with(vpc))
        self.assertTrue(self.vpc_serv.remove_all_subnets.called_with(vpc))
        self.assertTrue(self.vpc_serv.remove_all_peering.called_with(vpc))
        self.assertTrue(self.vpc_serv.delete_vpc.called_with(vpc))
        self.vpc_serv.delete_traffic_mirror_elements.assert_called_once_with(
            self.ec2_client, self.reservation_id, self.logger
        )
        self.vpc_serv.delete_all_blackhole_routes.called_once_with(vpc)

    def test_cleanup_no_vpc(self):
        vpc_serv = Mock()
        vpc_serv.find_vpc_for_reservation = Mock(return_value=None)
        result = CleanupSandboxInfraOperation(vpc_serv, self.key_pair_serv).cleanup(
            aws_clients=self.aws_api_clients,
            aws_model=self.aws_model,
            reservation_id=self.reservation_id,
            actions=[PrepareCloudInfra()],
            logger=self.logger,
        )

        self.assertFalse(result.success)
