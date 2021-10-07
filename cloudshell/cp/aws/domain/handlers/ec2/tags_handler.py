from typing import TYPE_CHECKING, Dict, List, Optional

import attr

if TYPE_CHECKING:
    from mypy_boto3_ec2.type_defs import TagTypeDef

    from cloudshell.cp.aws.models.reservation_model import ReservationModel


CREATED_BY_QUALI = "Cloudshell"


class TagNames:
    Name = "Name"
    CreatedBy = "CreatedBy"
    Owner = "Owner"
    Blueprint = "Blueprint"
    ReservationId = "ReservationId"
    Domain = "Domain"
    IsPublic = "IsPublic"


@attr.s(auto_attribs=True, slots=True, frozen=True, str=False)
class TagsHandler:
    _tags_dict: Dict[str, str] = {}

    @classmethod
    def from_tags_list(cls, tags_list: List[Dict[str, str]]) -> "TagsHandler":
        tags_dict = {}
        for tag in tags_list:
            tags_dict[tag["Key"]] = tag["Value"]
        return cls(tags_dict)

    @classmethod
    def create_default(
        cls, name: str, reservation: "ReservationModel"
    ) -> "TagsHandler":
        tags = {
            TagNames.Name: name,
            TagNames.CreatedBy: CREATED_BY_QUALI,
            TagNames.Blueprint: reservation.blueprint,
            TagNames.Owner: reservation.owner,
            TagNames.Domain: reservation.domain,
            TagNames.ReservationId: reservation.reservation_id,
        }
        return cls(tags)

    def __str__(self):
        return f"Tags: {self._tags_dict}"

    @property
    def aws_tags(self) -> List["TagTypeDef"]:
        return [{"Key": key, "Value": value} for key, value in self._tags_dict.items()]

    def get(self, name: str) -> Optional[str]:
        return self._tags_dict.get(name)

    def get_name(self) -> Optional[str]:
        return self._tags_dict.get(TagNames.Name)

    def get_reservation_id(self) -> Optional[str]:
        return self._tags_dict.get(TagNames.ReservationId)

    def set_is_public_tag(self, is_public: bool):
        self._tags_dict[TagNames.IsPublic] = str(is_public)
