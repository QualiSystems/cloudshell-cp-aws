import re
from unittest import TestCase
from unittest.mock import Mock

from cloudshell.cp.aws.domain.services.ec2.subnet import SubnetService


class TestSubnetService(TestCase):
    def setUp(self):
        self.vpc = Mock()
        self.cidr = "10.0.0.0/24"
        self.availability_zone = "a1"
        self.vpc_name = "name"
        self.reservation_id = "res"
        self.subnet_waiter = Mock()
        self.subnet_srv = SubnetService(self.subnet_waiter)

    def test_delete_subnet(self):
        subnet = Mock()
        res = self.subnet_srv.delete_subnet(subnet)
        self.assertTrue(res)
        self.assertTrue(subnet.delete.called)

    def test_get_vpc_subnets(self):
        # arrange
        subnet1 = Mock()
        subnet2 = Mock()
        vpc = Mock()
        vpc.subnets.all = Mock(return_value=[subnet1, subnet2])

        # act
        subnets = self.subnet_srv.get_vpc_subnets(vpc)

        # assert
        vpc.subnets.all.assert_called_once()
        self.assertTrue(subnet1 in subnets)
        self.assertTrue(subnet2 in subnets)
        self.assertEqual(len(subnets), 2)

    def test_get_vpc_subnets_throw_if_empty(self):
        # arrange
        vpc = Mock()
        vpc.id = "123"
        vpc.subnets.all = Mock(return_value=[])
        # act
        with self.assertRaisesRegex(
            ValueError, re.escape(f"The given VPC({vpc.id}) has no subnets")
        ):
            self.subnet_srv.get_vpc_subnets(vpc)
        # assert
        vpc.subnets.all.assert_called_once()

    def test_get_first_or_none_subnet_from_vpc_returns_first(self):
        # arrange
        subnet1 = Mock()
        subnet2 = Mock()
        vpc = Mock()
        vpc.subnets.all = Mock(return_value=[subnet1, subnet2])

        # act
        subnet_result = self.subnet_srv.get_first_or_none_subnet_from_vpc(vpc=vpc)

        # assert
        vpc.subnets.all.assert_called_once()
        self.assertEqual(subnet1, subnet_result)

    def test_create_subnet_nowait(self):
        # Act
        self.subnet_srv.create_subnet_nowait(self.vpc, "1.2.3.4/24", "zoneA")
        # Assert
        self.vpc.create_subnet.assert_called_once_with(
            CidrBlock="1.2.3.4/24", AvailabilityZone="zoneA"
        )

    def test_get_first_or_none_subnet_from_vpc__returns_none(self):
        # Arrange
        self.vpc.subnets.all = Mock(return_value=[])
        # Act
        subnet = self.subnet_srv.get_first_or_none_subnet_from_vpc(self.vpc)
        # Assert
        self.assertEqual(subnet, None)

    def test_get_first_or_none_subnet_from_vpc__returns_by_cidr(self):
        # Arrange
        s = Mock()
        s.cidr_block = "1.2.3.4/24"
        self.vpc.subnets.all = Mock(return_value=[s, Mock()])
        # Act
        subnet = self.subnet_srv.get_first_or_none_subnet_from_vpc(
            self.vpc, "1.2.3.4/24"
        )
        # Assert
        self.assertEqual(subnet, s)
