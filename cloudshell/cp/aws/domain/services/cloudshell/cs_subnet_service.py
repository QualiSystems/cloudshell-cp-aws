import itertools
from ipaddress import IPv4Network
from logging import Logger
from typing import TYPE_CHECKING

from cloudshell.api.cloudshell_api import CloudShellAPIError

if TYPE_CHECKING:
    from cloudshell.api.cloudshell_api import CloudShellAPISession

    from cloudshell.cp.aws.domain.services.strategy.prepare_subnets import ActionItem


class CsSubnetService:
    def __init__(self, cs_session: "CloudShellAPISession", reservation_id: str):
        self.cs_session = cs_session
        self.reservation_id = reservation_id

    def patch_subnet_cidr(
        self,
        item: "ActionItem",
        vpc_cidr: str,
        logger: "Logger",
    ):
        requested_cidr = item.action.actionParams.cidr
        cidr = self._gen_new_cidr(requested_cidr, vpc_cidr, logger)
        if cidr != requested_cidr:
            # alias = item.action.actionParams.alias  noqa: E800
            # new_alias = self._get_alias(cidr)  noqa: E800
            # self._set_new_service_name(alias, new_alias, logger)  noqa: E800

            # item.action.actionParams.alias = new_alias  noqa: E800
            logger.info(
                f"Patch subnet CIDR to be inside the Shared VPC CIDR. Old CIDR "
                f"'{requested_cidr}' new CIDR '{cidr}'"
            )
            item.action.actionParams.cidr = cidr

    def _set_new_service_name(self, current_name, new_name, logger):
        try:
            self.cs_session.SetServiceName(self.reservation_id, current_name, new_name)
        except CloudShellAPIError:
            logger.debug(
                f"Failed to rename Subnet Service {current_name}", exc_info=True
            )

    @staticmethod
    def _gen_new_cidr(cidr: str, vpc_cidr: str, logger: "Logger"):
        if not IPv4Network(vpc_cidr).supernet_of(IPv4Network(cidr)):
            prefix = vpc_cidr.split(".", 2)[:2]  # first two digits
            suffix = cidr.rsplit(".", 2)[-2:]  # last two digits and mask
            cidr = ".".join(itertools.chain(prefix, suffix))
            logger.info(
                f"Patch subnet CIDR so it should be a subnet of VPC CIDR, now - {cidr}"
            )
            if not IPv4Network(vpc_cidr).supernet_of(IPv4Network(cidr)):
                raise ValueError("Subnet CIDR is not a subnetwork of VPC CIDR")
        return cidr

    @staticmethod
    def _get_alias(cidr: str) -> str:
        """Creates alias for CS Subnet Service."""
        net = IPv4Network(cidr)
        return f"Subnet - {net.network_address}-{net.broadcast_address}"
