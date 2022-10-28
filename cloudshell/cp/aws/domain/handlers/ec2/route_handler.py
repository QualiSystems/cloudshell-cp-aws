from typing import TYPE_CHECKING, Optional

import attr

from cloudshell.cp.aws.common.cached_property import cached_property

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Route  # noqa: I900


@attr.s(auto_attribs=True)
class RouteHandler:
    _route: "Route"

    @cached_property
    def is_blackhole(self) -> bool:
        return self._route.state == "blackhole"

    def delete(self):
        try:
            self._route.delete()
        except Exception as e:
            if "InvalidRoute.NotFound" in str(e):
                pass
            else:
                raise

    def delete_if_blackhole(self) -> bool:
        if self.is_blackhole:
            self.delete()
        return self.is_blackhole

    @property
    def gateway_id(self) -> Optional[str]:
        return self._route.gateway_id

    @property
    def tgw_id(self) -> Optional[str]:
        return self._route.transit_gateway_id

    @property
    def dst_cidr(self) -> Optional[str]:
        return self._route.destination_cidr_block

    def replace_peering_connection(self, peering_id: str):
        if peering_id != self._route.vpc_peering_connection_id:
            self._route.replace(VpcPeeringConnectionId=peering_id)
