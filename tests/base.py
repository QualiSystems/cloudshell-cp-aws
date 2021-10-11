from typing import List
from unittest.mock import Mock

import attr


@attr.s(auto_attribs=True)
class RouteTableTest:
    _main: bool = False
    associations_attribute: List[dict] = attr.ib(factory=list)
    tags: list = attr.ib(factory=list)

    def __attrs_post_init__(self):
        try:
            attr_dict = self.associations_attribute[0]
        except IndexError:
            self.associations_attribute.append({})
            attr_dict = self.associations_attribute[0]
        attr_dict["Main"] = self._main

    def create_tags(self, *, Tags):
        self.tags.extend(Tags)

    def load(self):
        ...


@attr.s(auto_attribs=True)
class VpcTest:
    _rts: List["RouteTableTest"] = attr.ib(
        factory=[RouteTableTest(), RouteTableTest(True)].copy
    )
    id: str = "vpc id"  # noqa: A003

    @property
    def route_tables(self):
        return Mock(all=lambda: self._rts)

    def create_route_table(self) -> "RouteTableTest":
        rt = RouteTableTest()
        self._rts.append(rt)
        return rt
