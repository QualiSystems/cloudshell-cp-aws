from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client  # noqa: I900


def get_transit_gateway_cidr_blocks(ec2_client: "EC2Client", tgw_id: str) -> List[str]:
    info_list = ec2_client.describe_transit_gateways(TransitGatewayIds=[tgw_id])
    try:
        cidr = info_list["TransitGateways"][0]["Options"]["TransitGatewayCidrBlocks"]
    except KeyError:
        cidr = []
    return cidr
