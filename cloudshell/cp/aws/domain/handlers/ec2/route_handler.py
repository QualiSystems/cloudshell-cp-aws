from typing import TYPE_CHECKING

import attr

from cloudshell.cp.aws.common.cached_property import cached_property

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Route


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
