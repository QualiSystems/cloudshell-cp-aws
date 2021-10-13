from unittest import TestCase
from unittest.mock import Mock, call

from cloudshell.cp.aws.domain.services.ec2.vpc import VPCService


class TestVPCService(TestCase):
    def setUp(self):
        self.tags = Mock()
        self.subnet_service = Mock()
        self.logger = Mock()
        self.aws_ec2_datamodel = Mock()
        self.ec2_client = Mock()
        self.ec2_session = Mock()
        self.vpc = Mock()
        self.vpc_id = Mock()
        self.ec2_session.create_vpc = Mock(return_value=self.vpc)
        self.ec2_session.Vpc = Mock(return_value=self.vpc)
        self.s3_session = Mock()
        self.reservation = Mock()
        self.cidr = Mock()
        self.vpc_waiter = Mock()
        self.instance_service = Mock()
        self.sg_service = Mock()
        self.route_table_service = Mock()
        self.traffic_mirror_service = Mock()
        self.vpc_service = VPCService(
            subnet_service=self.subnet_service,
            instance_service=self.instance_service,
            vpc_waiter=self.vpc_waiter,
            sg_service=self.sg_service,
            traffic_mirror_service=self.traffic_mirror_service,
        )

    def test_get_all_internet_gateways(self):
        internet_gate = Mock()
        self.vpc.internet_gateways = Mock()
        self.vpc.internet_gateways.all = Mock(return_value=[internet_gate])
        res = self.vpc_service.get_all_igws(self.vpc)

        self.assertEqual(res, [internet_gate])

    def test_remove_all_internet_gateways(self):
        internet_gate = Mock()

        self.vpc.internet_gateways = Mock()
        self.vpc.internet_gateways.all = Mock(return_value=[internet_gate])
        self.vpc_service.remove_all_internet_gateways(self.vpc)

        internet_gate.detach_from_vpc.assert_called_with(VpcId=self.vpc.id)
        self.assertTrue(internet_gate.delete.called)

    def test_create_and_attach_internet_gateway(self):
        internet_gate = Mock()
        internet_gate.id = "super_id"
        self.ec2_session.create_internet_gateway = Mock(return_value=internet_gate)

        igw = self.vpc_service.create_and_attach_internet_gateway(
            self.ec2_session, self.vpc, self.reservation
        )

        self.assertTrue(self.ec2_session.create_internet_gateway.called)
        self.assertEqual(igw.id, internet_gate.id)

    def test_create_vpc_for_reservation(self):
        vpc = self.vpc_service.create_vpc_for_reservation(
            self.ec2_session, self.reservation, self.cidr
        )
        self.vpc_service.VPC_RESERVATION.format(self.reservation.reservation_id)

        self.vpc_waiter.wait.assert_called_once_with(
            vpc=vpc, state=self.vpc_waiter.AVAILABLE
        )
        self.assertEqual(self.vpc, vpc)
        self.ec2_session.create_vpc.assert_called_once_with(CidrBlock=self.cidr)

    def test_find_vpc_for_reservation(self):
        self.ec2_session.vpcs = Mock()
        self.ec2_session.vpcs.filter = Mock(return_value=[self.vpc])
        vpc = self.vpc_service.find_vpc_for_reservation(
            self.ec2_session, self.reservation
        )
        self.assertEqual(vpc, self.vpc)

    def test_find_vpc_for_reservation_no_vpc(self):
        self.ec2_session.vpcs = Mock()
        self.ec2_session.vpcs.filter = Mock(return_value=[])
        vpc = self.vpc_service.find_vpc_for_reservation(
            self.ec2_session, self.reservation
        )
        self.assertIsNone(vpc)

    def test_find_vpc_for_reservation_too_many(self):
        self.ec2_session.vpcs = Mock()
        self.ec2_session.vpcs.filter = Mock(return_value=[1, 2])
        self.assertRaises(
            ValueError,
            self.vpc_service.find_vpc_for_reservation,
            self.ec2_session,
            self.reservation,
        )

    def test_remove_all_sgs(self):
        sg = Mock()
        self.vpc.security_groups.all.return_value = [sg]
        self.sg_service.sort_sg_list.return_value = [sg]

        self.vpc_service.remove_all_security_groups(self.vpc)

        self.sg_service.delete_security_group.assert_called_once_with(sg)

    # When a trying to delete security group(isolated) and it is referenced in
    # another's group rule.
    # we get resource sg-XXXXXX has a dependent object, so to fix that ,
    # isolated group shall be deleted last.
    def test_remove_all_sgs_isolated_group_removed_last(self):
        sg = Mock()
        sg.group_name = "dummy"
        isolated_sg = Mock()
        isolated_sg.group_name = self.sg_service.sandbox_isolated_sg_name(
            self.reservation.reservation_id
        )
        isolated_at_start_sgs = [isolated_sg, sg]
        isolated_at_end_sgs_calls = [call(sg), call(isolated_sg)]
        self.sg_service.sort_sg_list.return_value = [sg, isolated_sg]

        self.vpc.security_groups = Mock()
        self.vpc.security_groups.all = Mock(return_value=isolated_at_start_sgs)

        self.vpc_service.remove_all_security_groups(self.vpc)

        self.sg_service.delete_security_group.assert_has_calls(
            isolated_at_end_sgs_calls, any_order=False
        )

    def test_remove_subnets(self):
        subnet = Mock()
        self.vpc.subnets = Mock()
        self.vpc.subnets.all = Mock(return_value=[subnet])

        res = self.vpc_service.remove_all_subnets(self.vpc)

        self.assertIsNotNone(res)
        self.subnet_service.delete_subnet.assert_called_once_with(subnet)

    def test_delete_all_instances(self):
        instance = Mock()
        self.vpc.instances = Mock()
        self.vpc.instances.all = Mock(return_value=[instance])

        self.vpc_service.delete_all_instances(self.vpc)

        self.instance_service.terminate_instances.assert_called_once_with([instance])

    def test_delete_vpc(self):
        res = self.vpc_service.delete_vpc(self.vpc)

        self.assertTrue(self.vpc.delete.called)
        self.assertIsNotNone(res)

    def test_get_or_pick_availability_zone_1(self):  # Scenario(1): from existing subnet
        # Arrange
        subnet = Mock()
        subnet.availability_zone = "z"
        self.subnet_service.get_first_or_none_subnet_from_vpc = Mock(
            return_value=subnet
        )
        # Act
        result = self.vpc_service.get_or_pick_availability_zone(
            ec2_client=self.ec2_client,
            vpc=self.vpc,
            aws_ec2_datamodel=self.aws_ec2_datamodel,
        )
        # Assert
        self.assertEqual(result, "z")

    def test_get_or_pick_availability_zone_2(
        self,
    ):  # Scenario(2): from available zones list
        # Arrange
        self.subnet_service.get_first_or_none_subnet_from_vpc = Mock(return_value=None)
        self.ec2_client.describe_availability_zones = Mock(
            return_value={"AvailabilityZones": [{"ZoneName": "z"}]}
        )
        # Act
        result = self.vpc_service.get_or_pick_availability_zone(
            ec2_client=self.ec2_client,
            vpc=self.vpc,
            aws_ec2_datamodel=self.aws_ec2_datamodel,
        )
        # Assert
        self.assertEqual(result, "z")

    def test_get_or_pick_availability_zone_3(self):  # Scenario(3): no available zone
        # Arrange
        self.subnet_service.get_first_or_none_subnet_from_vpc = Mock(return_value=None)
        self.ec2_client.describe_availability_zones = Mock(return_value=None)
        # Act
        with self.assertRaisesRegex(
            Exception, "No AvailabilityZone is available for this vpc"
        ):
            self.vpc_service.get_or_pick_availability_zone(
                ec2_client=self.ec2_client,
                vpc=self.vpc,
                aws_ec2_datamodel=self.aws_ec2_datamodel,
            )
