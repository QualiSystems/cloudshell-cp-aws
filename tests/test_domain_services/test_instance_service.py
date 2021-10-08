from unittest import TestCase
from unittest.mock import MagicMock, Mock

from cloudshell.cp.aws.domain.services.ec2.instance import InstanceService


class TestInstanceService(TestCase):
    def setUp(self):
        self.tag_service = Mock()
        self.instance_waiter = Mock()
        self.network_interface_service = Mock()
        self.ec2_session = Mock()
        self.ec2_client = Mock()
        self.name = "name"
        self.reservation_id = "res_id"
        self.instance = MagicMock()
        self.instance.instance_id = "id"
        self.default_tags = ["tag1", "tag2"]
        self.ec2_session.create_instances = Mock(return_value=[self.instance])
        self.ec2_session.Instance = Mock(return_value=self.instance)
        self.instance_service = InstanceService(
            self.instance_waiter, self.network_interface_service
        )

    def test_create_instance(self):
        ami_dep = Mock()
        ami_dep.custom_tags = ""
        new_instance = Mock()
        new_instance.instance_id = "id"
        volume_1 = Mock()
        volume_2 = Mock()

        new_instance.volumes.all = Mock(return_value=[volume_2, volume_1])

        self.ec2_session.create_instances = Mock(return_value=[new_instance])

        res = self.instance_service.create_instance(
            self.ec2_session,
            ami_dep,
        )

        self.ec2_session.create_instances.assert_called_once_with(
            ImageId=ami_dep.aws_ami_id,
            MinCount=ami_dep.min_count,
            MaxCount=ami_dep.max_count,
            InstanceType=ami_dep.instance_type,
            IamInstanceProfile=ami_dep.iam_role,
            KeyName=ami_dep.aws_key,
            BlockDeviceMappings=ami_dep.block_device_mappings,
            NetworkInterfaces=ami_dep.network_interfaces,
            UserData=ami_dep.user_data,
        )
        self.assertEqual(new_instance, res)

    def test_get_instance_by_id(self):
        res = self.instance_service.get_instance_by_id(self.ec2_session, "id")
        self.ec2_session.Instance.assert_called_once_with(id="id")
        self.assertIsNotNone(res)

    def test_get_active_instance_by_id_raise_exception_if_vm_terminated(self):
        """Check that method will raise exception if VM was terminated on the AWS."""
        self.instance.state = {"Name": "terminated"}

        with self.assertRaises(Exception):
            self.instance_service.get_active_instance_by_id(self.ec2_session, "id")

    def test_get_active_instance_by_id_raise_exception_if_no_vm(self):
        """Check that method will raise exception if VM was removed from the AWS."""
        self.ec2_session.Instance = Mock(return_value=None)
        with self.assertRaises(Exception):
            self.instance_service.get_active_instance_by_id(self.ec2_session, "id")

    def test_terminate_instance(self):
        self.instance_waiter.multi_wait = Mock(return_value=[self.instance])
        self.instance_waiter.TERMINATED = "terminated"
        res = self.instance_service.terminate_instance(self.instance)

        self.assertTrue(self.instance.terminate.called)
        self.instance_waiter.multi_wait.assert_called_once_with(
            [self.instance], self.instance_waiter.TERMINATED
        )
        self.assertIsNotNone(res)

    def test_terminate_instances(self):
        instances = [Mock(), Mock()]
        res = self.instance_service.terminate_instances(instances)

        self.assertTrue(instances[0].terminate.called)
        self.assertTrue(instances[1].terminate.called)
        self.instance_waiter.multi_wait.assert_called_once_with(
            instances, self.instance_waiter.TERMINATED
        )
        self.assertIsNotNone(res)

    def test_wait_for_instance_to_run_in_aws_with_status_check(self):
        # arrange
        ec2_client = Mock()
        instance = Mock()
        cancellation_context = Mock()
        logger = Mock()

        # act
        self.instance_service.wait_for_instance_to_run_in_aws(
            ec2_client,
            instance,
            True,
            0,
            cancellation_context,
            logger,
        )

        # assert
        self.instance_service.instance_waiter.wait.assert_called_once_with(
            instance=instance,
            state=self.instance_service.instance_waiter.RUNNING,
            cancellation_context=cancellation_context,
        )
        self.instance_service.instance_waiter.wait_status_ok.assert_called_once_with(
            ec2_client,
            instance,
            logger,
            0,
            cancellation_context,
        )
