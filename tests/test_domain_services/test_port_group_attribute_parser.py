import pytest

from cloudshell.cp.aws.domain.services.parsers.port_group_attribute_parser import (
    PortGroupAttributeParser,
)
from cloudshell.cp.aws.models.port_data import PortData


@pytest.mark.parametrize(
    ("ports_str", "expected_port_data"),
    (
        ("80", PortData("80", "80", "tcp", "0.0.0.0/0")),
        ("443:tcp:10.0.0.0/24", PortData("443", "443", "tcp", "10.0.0.0/24")),
        ("200-220:udp", PortData("200", "220", "udp", "0.0.0.0/0")),
        ("icmp", PortData("-1", "-1", "icmp", "0.0.0.0/0")),
        ("icmp:10.0.0.0/24", PortData("-1", "-1", "icmp", "10.0.0.0/24")),
    ),
)
def test_parsing_inbound_ports(ports_str, expected_port_data):
    port_data = PortGroupAttributeParser._single_port_parse(ports_str)
    assert port_data.from_port == expected_port_data.from_port
    assert port_data.to_port == expected_port_data.to_port
    assert port_data.protocol == expected_port_data.protocol
    assert port_data.destination == expected_port_data.destination
