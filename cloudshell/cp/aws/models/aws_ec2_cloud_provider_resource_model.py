import ipaddress
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from cloudshell.shell.core.driver_context import ResourceContextDetails


NETWORK_MASK_PATTERN = re.compile(r"/\d+$")


def get_items(string: str, separator: str = ",") -> List[str]:
    return list(filter(bool, map(str.strip, string.split(separator))))


class VpcMode(Enum):
    DYNAMIC = "Dynamic"
    STATIC = "Static"
    SHARED = "Shared"
    SINGLE = "Single"


@dataclass
class AWSEc2CloudProviderResourceModel:
    region: str
    aws_mgmt_sg_id: str
    aws_mgmt_vpc_id: str
    key_pairs_location: str
    max_storage_size: int
    max_storage_iops: int
    instance_type: str
    vpc_mode: VpcMode
    static_vpc_cidr: str
    shared_vpc_id: str
    shared_vpc_role_arn: str
    aws_secret_access_key: str
    aws_access_key_id: str
    additional_mgmt_networks: List[str]
    tgw_id: str
    vgw_id: str
    vgw_cidrs: List[str]

    def _validate_vpc_id(self):
        if self.vpc_mode is VpcMode.SHARED and not self.shared_vpc_id:
            msg = "You should specify 'VPC ID' for the Shared VPC Mode"
            raise ValueError(msg)

    def _validate_aws_mgt_vpc_id(self):
        if not self.aws_mgmt_vpc_id:
            raise ValueError("AWS Mgmt VPC ID attribute must be set")

    def _validate_additional_mgt_networks(self):
        for network in self.additional_mgmt_networks:
            msg = f"Additional Management Network is not correct {network} - {{}}"
            try:
                ipaddress.IPv4Network(network)
            except ipaddress.AddressValueError as e:
                raise ValueError(msg.format(e))
            if not NETWORK_MASK_PATTERN.search(network):
                raise ValueError(msg.format("it should have network mask"))

    def _validate_vgw_cidrs(self):
        for cidr in self.vgw_cidrs:
            msg = f"VGW CIDR is not correct {cidr} - {{}}"
            try:
                ipaddress.IPv4Network(cidr)
            except ipaddress.AddressValueError as e:
                raise ValueError(msg.format(e))
            if not NETWORK_MASK_PATTERN.search(cidr):
                raise ValueError(msg.format("it should have network mask"))

    def _validate_role_arn(self):
        if self.vpc_mode is VpcMode.SHARED and not self.shared_vpc_role_arn:
            raise ValueError("You should specify Role Arn for the Shared VPC mode.")

    def _validate_static_cidr(self):
        if self.vpc_mode is VpcMode.STATIC and not self.static_vpc_cidr:
            raise ValueError("You should set Static VPC CIDR for Static VPC mode")

    def validate(self):
        self._validate_aws_mgt_vpc_id()
        self._validate_vpc_id()
        self._validate_additional_mgt_networks()
        self._validate_role_arn()
        self._validate_static_cidr()
        self._validate_vgw_cidrs()

    @classmethod
    def from_resource(
        cls, resource: "ResourceContextDetails"
    ) -> "AWSEc2CloudProviderResourceModel":
        def _get(attr_name: str):
            return resource.attributes[f"{resource.model}.{attr_name}"]

        model = cls(
            region=_get("Region"),
            aws_mgmt_sg_id=_get("AWS Mgmt SG ID"),
            aws_mgmt_vpc_id=_get("AWS Mgmt VPC ID"),
            key_pairs_location=_get("Keypairs Location"),
            max_storage_size=int(_get("Max Storage Size")),
            max_storage_iops=int(_get("Max Storage IOPS")),
            instance_type=_get("Instance Type"),
            vpc_mode=VpcMode(_get("VPC Mode")),
            static_vpc_cidr=_get("Static VPC CIDR"),
            shared_vpc_id=_get("Shared VPC ID"),
            aws_secret_access_key=_get("AWS Secret Access Key"),
            aws_access_key_id=_get("AWS Access Key ID"),
            additional_mgmt_networks=get_items(_get("Additional Management Networks")),
            tgw_id=_get("Transit Gateway ID"),
            vgw_id=_get("VPN Gateway ID"),
            vgw_cidrs=get_items(_get("VPN CIDRs")),
            shared_vpc_role_arn=_get("Shared VPC Role Arn"),
        )
        model.validate()
        return model
