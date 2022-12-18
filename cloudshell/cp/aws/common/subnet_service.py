from __future__ import annotations

from enum import Enum

from cloudshell.cp.core.models import PrepareSubnet


class SubnetServiceAttr(Enum):
    SUBNET_ID = "Subnet Id"


def get_subnet_id(subnet_action: PrepareSubnet) -> str | None:
    subnet_attrs = subnet_action.actionParams.subnetServiceAttributes or {}
    return subnet_attrs.get(SubnetServiceAttr.SUBNET_ID.value)
