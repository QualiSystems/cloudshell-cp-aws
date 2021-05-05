from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client


def get_transit_gateway_cidr_blocks(ec2_client: "EC2Client", tgw_id: str) -> List[str]:
    info_list = ec2_client.describe_transit_gateways(TransitGatewayIds=[tgw_id])
    return info_list["TransitGateways"][0]["Options"]["TransitGatewayCidrBlocks"]
