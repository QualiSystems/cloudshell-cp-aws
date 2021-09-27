from typing import Dict, List, Optional

import attr


class TagNames:
    Name = "Name"


@attr.s(auto_attribs=True, slots=True, frozen=True)
class TagsHandler:
    _tags_dict: Dict[str, str] = {}

    @classmethod
    def from_tags_list(cls, tags_list: List[Dict[str, str]]) -> "TagsHandler":
        tags_dict = {}
        for tag in tags_list:
            tags_dict[tag["Key"]] = tag["Value"]
        return cls(tags_dict)

    def get(self, name: str) -> Optional[str]:
        return self._tags_dict.get(name)

    def get_name(self) -> Optional[str]:
        return self._tags_dict.get(TagNames.Name)
