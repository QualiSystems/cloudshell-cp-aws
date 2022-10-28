import uuid
from typing import TYPE_CHECKING, List, Optional

from botocore.exceptions import ClientError

from cloudshell.cp.aws.domain.handlers.ec2 import (
    IsolationTagValue,
    TagsHandler,
    TypeTagValue,
)

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2ServiceResource  # noqa: I900
    from mypy_boto3_ec2.service_resource import SecurityGroup, Vpc  # noqa: I900


class SecurityGroupService:
    CLOUDSHELL_SANDBOX_DEFAULT_SG = "Cloudshell Sandbox SG {0}"
    CLOUDSHELL_SANDBOX_ISOLATED_FROM_SANDBOX_SG = "Isolated SG {0}"
    CLOUDSHELL_SANDBOX_ISOLATED_SG_STARTS = (
        CLOUDSHELL_SANDBOX_ISOLATED_FROM_SANDBOX_SG.replace("{}", "").replace("{0}", "")
    )
    CLOUDSHELL_CUSTOM_SECURITY_GROUP = "Cloudshell Custom SG {0}"
    CLOUDSHELL_SUBNET_SECURITY_GROUP = "Cloudshell Subnet SG {}"
    CLOUDSHELL_SECURITY_GROUP_DESCRIPTION = "Cloudshell Security Group"

    def delete_security_group(self, sg):
        if sg.group_name != "default":
            sg.delete()
        return True

    @staticmethod
    def create_security_group(
        ec2_session: "EC2ServiceResource", vpc_id: str, security_group_name: str
    ) -> "SecurityGroup":
        return ec2_session.create_security_group(
            GroupName=security_group_name,
            Description=SecurityGroupService.CLOUDSHELL_SECURITY_GROUP_DESCRIPTION,
            VpcId=vpc_id,
        )

    @staticmethod
    def sandbox_default_sg_name(reservation_id):
        return SecurityGroupService.CLOUDSHELL_SANDBOX_DEFAULT_SG.format(reservation_id)

    @staticmethod
    def sandbox_isolated_sg_name(reservation_id):
        return SecurityGroupService.CLOUDSHELL_SANDBOX_ISOLATED_FROM_SANDBOX_SG.format(
            reservation_id
        )

    @classmethod
    def subnet_sg_name(cls, subnet_id: str) -> str:
        return cls.CLOUDSHELL_SUBNET_SECURITY_GROUP.format(subnet_id)

    @staticmethod
    def _set_rules(security_group: "SecurityGroup", ip_permissions: list):
        try:
            security_group.authorize_ingress(IpPermissions=ip_permissions)
        except ClientError as e:
            if "InvalidPermission.Duplicate" in str(e):
                pass
            else:
                raise

    @staticmethod
    def get_security_group_by_name(vpc: "Vpc", name: str) -> Optional["SecurityGroup"]:
        security_groups = [
            sg for sg in list(vpc.security_groups.all()) if sg.group_name == name
        ]

        if not security_groups:
            return None

        if len(security_groups) > 1:
            raise ValueError("Too many security groups by that name")

        return security_groups[0]

    @staticmethod
    def get_reservation_id(security_group: "SecurityGroup") -> Optional[str]:
        return TagsHandler.from_tags_list(security_group.tags).get_reservation_id()

    def get_security_groups_by_reservation_id(
        self, vpc: "Vpc", reservation_id: str
    ) -> List["SecurityGroup"]:
        return [
            sg
            for sg in vpc.security_groups.all()
            if self.get_reservation_id(sg) == reservation_id
        ]

    def set_shared_reservation_security_group_rules(
        self, security_group, management_sg_id, isolated_sg, need_management_sg
    ):
        """# noqa
        Set inbound rules for the reservation shared security group.
        The default rules are:
         1) Allow all inbound traffic from instances with the same reservation id (inner sandbox connectivity)
         2) Allow all inbound traffic from the management vpc for specific security group id
        :param bool need_management_sg:
        :param security_group: security group object
        :param str management_sg_id: Id of the management security group id
        :return:
        """

        # management_rule = {'IpProtocol': '-1', 'FromPort': -1, 'ToPort': -1,  # noqa
        #                    'UserIdGroupPairs': [{'GroupId': management_sg_id}]}  # noqa
        #
        # allow_internal_traffic_rule = {'IpProtocol': '-1', 'FromPort': -1, 'ToPort': -1,  # noqa
        #        'UserIdGroupPairs': [{'GroupId': security_group.id}, {'GroupId': isolated_sg.id}]}  # noqa
        #
        # ip_permissions = [allow_internal_traffic_rule]  # noqa
        #
        # if need_management_sg:  # noqa
        #     ip_permissions.append(management_rule)  # noqa
        management_rule = {
            "IpProtocol": "-1",
            "FromPort": -1,
            "ToPort": -1,
            "UserIdGroupPairs": [{"GroupId": management_sg_id}],
        }

        allow_internal_traffic_rule = {
            "IpProtocol": "-1",
            "FromPort": -1,
            "ToPort": -1,
            "UserIdGroupPairs": [
                {"GroupId": security_group.id},
                {"GroupId": isolated_sg.id},
            ],
        }

        ip_permissions = [allow_internal_traffic_rule]

        if need_management_sg:
            ip_permissions.append(management_rule)

        self._set_rules(security_group, ip_permissions)

    def set_isolated_security_group_rules(
        self, security_group, management_sg_id, need_management_access
    ):
        """# noqa
        Set inbound rules for the reservation isolated security group.
        The default rules are:
         1) Allow all inbound traffic from the management vpc for specific security group id
        :param bool need_management_access:
        :param security_group: security group object
        :param str management_sg_id: Id of the management security group id
        :return:
        """
        # security_group.authorize_ingress(IpPermissions=  # noqa
        # [  # noqa
        #     {  # noqa
        #         'IpProtocol': '-1',  # noqa
        #         'FromPort': -1,  # noqa
        #         'ToPort': -1,  # noqa
        #         'UserIdGroupPairs': [  # noqa
        #             {  # noqa
        #                 'GroupId': management_sg_id  # noqa
        #             }  # noqa
        #         ]  # noqa
        #     }  # noqa
        # ])  # noqa
        if need_management_access:
            ip_permissions = [
                {
                    "IpProtocol": "-1",
                    "FromPort": -1,
                    "ToPort": -1,
                    "UserIdGroupPairs": [{"GroupId": management_sg_id}],
                }
            ]
            self._set_rules(security_group, ip_permissions)

    def set_subnet_sg_rules(self, security_group):
        rule = {
            "IpProtocol": "-1",
            "FromPort": -1,
            "ToPort": -1,
            "UserIdGroupPairs": [
                {"GroupId": security_group.id},
            ],
        }
        self._set_rules(security_group, [rule])

    def set_security_group_rules(
        self, security_group, inbound_ports=None, outbound_ports=None, logger=None
    ):
        """# noqa
        :param security_group: AWS SG object
        :param list[PortData] inbound_ports:
        :param list[PortData] outbound_ports:
        :param logging.Logger logger:
        :return:
        """
        # adding inbound port rules
        if inbound_ports:
            self._set_inbound_ports(inbound_ports, security_group)
            if logger:
                logger.info(
                    "Inbound ports attribute: {} set to security group: {}".format(
                        inbound_ports, security_group.group_id
                    )
                )

        # adding outbound port rules
        if outbound_ports:
            self._set_outbound_ports(outbound_ports, security_group)
            if logger:
                logger.info(
                    "Outbound ports attribute: {} set to security group: {}".format(
                        outbound_ports, security_group.group_id
                    )
                )

    def _set_outbound_ports(self, outbound_ports, security_group):
        if outbound_ports:
            ip_permissions = [
                self.get_ip_permission_object(port)
                for port in outbound_ports
                if port is not None
            ]
            security_group.authorize_egress(IpPermissions=ip_permissions)

    def _set_inbound_ports(self, inbound_ports, security_group):
        if inbound_ports:
            ip_permissions = [
                self.get_ip_permission_object(port)
                for port in inbound_ports
                if port is not None
            ]
            self._set_rules(security_group, ip_permissions)

    def remove_all_inbound_rules(self, security_group):
        rules = security_group.ip_permissions
        if rules:
            security_group.revoke_ingress(
                IpPermissions=rules
            )  # , GroupName=security_group.group_name)

    def remove_allow_all_outbound_rule(self, security_group):
        security_group.revoke_egress(
            IpPermissions=[
                {
                    "IpProtocol": "-1",
                    "FromPort": 0,
                    "ToPort": 65535,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ]
        )

    @staticmethod
    def get_ip_permission_object(port_data):
        return {
            "IpProtocol": port_data.protocol,
            "FromPort": int(port_data.from_port),
            "ToPort": int(port_data.to_port),
            "IpRanges": [{"CidrIp": port_data.destination}],
        }

    def get_inbound_ports_security_group(self, ec2_session, network_interface):
        """# noqa
        Returns an inbound ports security group for the nic
        Inbound ports security group is defined by the following attributes and their values:
        "Isolation=Exclusive" and "Type=InboundPorts"
        :param ec2_session:
        :param network_interface: AWS::EC2::NetworkInterface
        :rtype AppSecurityGroupModel:
        """
        security_group_descriptions = network_interface.groups

        for security_group_description in security_group_descriptions:
            security_group = ec2_session.SecurityGroup(
                security_group_description["GroupId"]
            )
            if self._is_inbound_ports_security_group(security_group):
                return security_group

        return None

    def get_custom_security_group(self, ec2_session, network_interface):
        """# noqa
        Returns a custom security group for the nic
        Custom security group is defined by the following attributes and their values:
        "Isolation=Exclusive" and "Type=Interface"
        :param ec2_session:
        :param network_interface: AWS::EC2::NetworkInterface
        :rtype AppSecurityGroupModel:
        """
        security_group_descriptions = network_interface.groups

        for security_group_description in security_group_descriptions:
            security_group = ec2_session.SecurityGroup(
                security_group_description["GroupId"]
            )
            if self._is_custom_security_group(security_group):
                return security_group

        return None

    def get_or_create_custom_security_group(
        self, ec2_session, logger, network_interface, reservation, vpc_id
    ):
        """# noqa
        Returns or create (if doesn't exist) and then returns a custom security group for the nic
        Custom security group is defined by the following attributes and their values:
        "Isolation=Exclusive" and "Type=Interface"
        :param ec2_session:
        :param logging.Logger logger:
        :param network_interface: AWS::EC2::NetworkInterface
        :param ReservationModel reservation:
        :param str vpc_id:
        :rtype AppSecurityGroupModel:
        """

        security_group_descriptions = network_interface.groups

        custom_security_group = self.get_custom_security_group(
            ec2_session=ec2_session, network_interface=network_interface
        )

        if custom_security_group:
            logger.info(
                f"Custom security group exists for nic "
                f"'{network_interface.network_interface_id}'."
            )
            return custom_security_group

        # name for a new (non existed yet) custom security group
        security_group_name = (
            SecurityGroupService.CLOUDSHELL_CUSTOM_SECURITY_GROUP.format(
                str(uuid.uuid4())
            )
        )

        # create a new security group in vpc
        custom_security_group = self.create_security_group(
            ec2_session, vpc_id, security_group_name
        )

        logger.info(f"Custom security group '{security_group_name}' created.")

        # add tags to the created security group that will define it as a custom
        # security group
        tags = TagsHandler.create_security_group_tags(
            security_group_name,
            reservation,
            IsolationTagValue.EXCLUSIVE,
            TypeTagValue.INTERFACE,
        )
        tags.add_tags_to_obj(custom_security_group)

        # attach the custom security group to the nic
        custom_security_group_id = custom_security_group.group_id
        security_group_ids = [x["GroupId"] for x in security_group_descriptions]
        security_group_ids.append(custom_security_group_id)
        network_interface.modify_attribute(Groups=security_group_ids)

        return custom_security_group

    @staticmethod
    def _is_inbound_ports_security_group(security_group: "SecurityGroup") -> bool:
        tags = TagsHandler.from_tags_list(security_group.tags)
        return (
            tags.get_isolation() is IsolationTagValue.EXCLUSIVE
            and tags.get_type() is TypeTagValue.INBOUND_PORTS
        )

    @staticmethod
    def _is_custom_security_group(security_group: "SecurityGroup") -> bool:
        tags = TagsHandler.from_tags_list(security_group.tags)
        return (
            tags.get_isolation() is IsolationTagValue.EXCLUSIVE
            and tags.get_type() is TypeTagValue.INTERFACE
        )

    def sort_sg_list(self, sg_list: List["SecurityGroup"]) -> List["SecurityGroup"]:
        """Sort Security Groups and set Isolated SG to the end.

        Isolated SGs can be used in other SGs and should be deleted last
        """
        return sorted(
            sg_list,
            key=lambda sg: sg.group_name.startswith(
                self.CLOUDSHELL_SANDBOX_ISOLATED_SG_STARTS
            ),
        )
