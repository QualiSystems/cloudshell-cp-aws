import ipaddress
import re

from cloudshell.cp.aws.models.port_data import PortData


class PortGroupAttributeParser:
    PORT_DATA_MATCH = re.compile(
        r"^(?P<from_port>\d+)"
        r"(-(?P<to_port>\d+))?"
        r"(:(?P<protocol>(udp|tcp)))?"
        r"(:(?P<destination>\S+))?$",
        re.IGNORECASE,
    )
    ICMP_PORT_DATA_MATCH = re.compile(
        r"^(?P<protocol>icmp)" r"(:(?P<destination>\S+))?$",
        re.IGNORECASE,
    )
    DEFAULT_DESTINATION = "0.0.0.0/0"
    DEFAULT_PROTOCOL = "tcp"

    @staticmethod
    def parse_security_group_rules_to_port_data(rules):
        """# noqa
        :param [list] rules:
        :return:
        :rtype: list[PortData]
        """
        if not isinstance(rules, list):
            return None

        parsed_data = []

        for rule in rules:
            port_data = PortData(rule.fromPort, rule.toPort, rule.protocol, rule.source)
            parsed_data.append(port_data)

        return parsed_data if (len(parsed_data) > 0) else None

    @staticmethod
    def parse_port_group_attribute(ports_attribute):
        """# noqa
        :param ports_attribute:
        :return:
        :rtype: list[PortData]
        """
        if ports_attribute:
            ports = filter(bool, map(str.strip, ports_attribute.strip().split(";")))
            port_data_array = [
                PortGroupAttributeParser._single_port_parse(port) for port in ports
            ]
            return port_data_array
        return None

    @classmethod
    def _single_port_parse(cls, ports_attribute):
        match = cls.PORT_DATA_MATCH.search(ports_attribute)
        if match:
            from_port = match.group("from_port")
            to_port = match.group("to_port") or from_port
        else:
            match = cls.ICMP_PORT_DATA_MATCH.search(ports_attribute)
            if match:
                from_port = to_port = "-1"
            else:
                msg = f"The value '{ports_attribute}' is not a valid ports rule"
                raise ValueError(msg)

        destination = match.group("destination") or cls.DEFAULT_DESTINATION
        protocol = match.group("protocol") or cls.DEFAULT_PROTOCOL
        return PortData(
            from_port=from_port,
            to_port=to_port,
            protocol=protocol,
            destination=destination,
        )

    @staticmethod
    def _is_valid_source(source):
        try:
            # check if source is a valid CIDR
            ipaddress.ip_network(str(source))
        except Exception:
            return False

        return True
