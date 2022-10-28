import itertools
from functools import total_ordering
from ipaddress import IPv4Network
from logging import Logger
from typing import TYPE_CHECKING, Iterator, List

import attr

from cloudshell.cp.aws.common.cached_property import cached_property
from cloudshell.cp.aws.common.exceptions import BaseAwsException

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Vpc  # noqa: I900


class CidrError(BaseAwsException):
    ...


class CidrIsNotSubnetOf(CidrError):
    def __init__(self, cidr: "CidrHandler", supernet: "CidrHandler"):
        self.cidr = cidr
        self.supernet = supernet
        super().__init__(f"CIDR {cidr} is not subnet of the {supernet}")


class CidrIsNotInsideCidrList(CidrError):
    def __init__(self, cidr: "CidrHandler", cidr_list: "CidrListHandler"):
        self.cidr = cidr
        self.cidr_list = cidr_list
        super().__init__(f"CIDR {cidr} is not inside CIDR list {cidr_list}")


class CidrBlockIsEmpty(CidrError):
    ...


@total_ordering
@attr.s(auto_attribs=True, cmp=False)
class CidrHandler:
    _cidr: str

    @cached_property
    def network(self) -> IPv4Network:
        return IPv4Network(self._cidr)

    def __str__(self):
        return self._cidr

    def __lt__(self, other: "CidrHandler") -> bool:
        if not isinstance(other, CidrHandler):
            raise NotImplementedError
        return self.network < other.network

    def __eq__(self, other: "CidrHandler") -> bool:
        if not isinstance(other, CidrHandler):
            raise NotImplementedError
        return self.network == other.network

    def subnet_of(self, other: "CidrHandler") -> bool:
        if not isinstance(other, CidrHandler):
            raise NotImplementedError
        return self.network.subnet_of(other.network)

    def supernet_of(self, other: "CidrHandler") -> bool:
        if not isinstance(other, CidrHandler):
            raise NotImplementedError
        return self.network.supernet_of(other.network)

    def patch_cidr_to_be_inside(
        self, other: "CidrHandler", logger: "Logger"
    ) -> "CidrHandler":
        logger.debug(f"Patching CIDR {other} to be inside cidr list {self}")
        prefix = str(self).split(".", 2)[:2]  # first two digits
        suffix = str(other).rsplit(".", 2)[-2:]  # last two digits and mask
        cidr = ".".join(itertools.chain(prefix, suffix))
        other = CidrHandler(cidr)
        self.validate_is_supernet_of(other)

        return other

    def validate_is_supernet_of(self, other: "CidrHandler"):
        if not self.supernet_of(other):
            raise CidrIsNotSubnetOf(self, other)


@attr.s(auto_attribs=True)
class CidrListHandler:
    _cidr_list: List[CidrHandler]

    @classmethod
    def from_vpc(cls, vpc: "Vpc") -> "CidrListHandler":
        cidrs = [
            CidrHandler(cidr_dict["CidrBlock"])
            for cidr_dict in vpc.cidr_block_association_set
            if cidr_dict.get("CidrBlockState", {}).get("State", "fail") == "associated"
        ]
        return cls(cidrs)

    def __iter__(self) -> Iterator[CidrHandler]:
        return iter(self._cidr_list)

    def __str__(self):
        return str(list(map(str, self)))

    @property
    def main_cidr(self) -> CidrHandler:
        try:
            cidr_handler = next(self)
        except StopIteration:
            raise CidrBlockIsEmpty
        return cidr_handler

    def patch_cidr_to_be_inside(
        self, cidr: CidrHandler, logger: "Logger"
    ) -> CidrHandler:
        if not any(map(cidr.subnet_of, self)):
            cidr = cidr.patch_cidr_to_be_inside(self.main_cidr, logger)
        return cidr

    def validate_is_supernet_of(self, cidr: "CidrHandler"):
        if not any(map(cidr.subnet_of, self)):
            raise CidrIsNotInsideCidrList(cidr, self)
