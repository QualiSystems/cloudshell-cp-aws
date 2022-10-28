from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional

import attr
import botocore
from retrying import retry

from cloudshell.cp.aws.common.exceptions import BaseAwsException

if TYPE_CHECKING:
    from mypy_boto3_ec2.type_defs import TagTypeDef  # noqa: I900

    from cloudshell.cp.aws.models.reservation_model import ReservationModel


CREATED_BY_QUALI = "Cloudshell"


class TagName:
    Name = "Name"
    CreatedBy = "CreatedBy"
    Owner = "Owner"
    Blueprint = "Blueprint"
    ReservationId = "ReservationId"
    Domain = "Domain"
    IsPublic = "IsPublic"
    Isolation = "Isolation"
    Type = "Type"


class IsolationTagValue(Enum):
    EXCLUSIVE = "Exclusive"
    SHARED = "Shared"


class TypeTagValue(Enum):
    DEFAULT = "Default"
    ISOLATED = "Isolated"
    INBOUND_PORTS = "InboundPorts"
    INTERFACE = "Interface"


class TagServiceCannotFindTheObject(BaseAwsException):
    def __init__(self, aws_obj):
        self.obj = aws_obj
        super().__init__(f"Tag service cannot find the {aws_obj}")


def tag_service_cannot_find_obj(exc) -> bool:
    return (
        isinstance(exc, botocore.exceptions.ClientError)
        and "notfound" in str(exc).lower()
    )


@attr.s(auto_attribs=True, slots=True, frozen=True, str=False)
class TagsHandler:
    _tags_dict: Dict[str, str] = {}

    @classmethod
    def from_tags_list(cls, tags_list: Optional[List[Dict[str, str]]]) -> "TagsHandler":
        tags_dict = {}
        for tag in tags_list or []:
            tags_dict[tag["Key"]] = tag["Value"]
        return cls(tags_dict)

    @classmethod
    def create_default_tags(
        cls, name: str, reservation: "ReservationModel"
    ) -> "TagsHandler":
        tags = {
            TagName.Name: name,
            TagName.CreatedBy: CREATED_BY_QUALI,
            TagName.Blueprint: reservation.blueprint,
            TagName.Owner: reservation.owner,
            TagName.Domain: reservation.domain,
            TagName.ReservationId: reservation.reservation_id,
        }
        return cls(tags)

    @classmethod
    def create_security_group_tags(
        cls,
        name: str,
        reservation: "ReservationModel",
        isolation: IsolationTagValue,
        tag_type: TypeTagValue,
    ) -> "TagsHandler":
        tags = cls.create_default_tags(name, reservation)
        tags_dict = {
            TagName.Isolation: isolation.value,
            TagName.Type: tag_type.value,
        }
        tags.update_tags(tags_dict)
        return tags

    def __str__(self):
        return f"Tags: {self._tags_dict}"

    @property
    def aws_tags(self) -> List["TagTypeDef"]:
        return [{"Key": key, "Value": value} for key, value in self._tags_dict.items()]

    def get(self, name: str) -> Optional[str]:
        return self._tags_dict.get(name)

    def get_name(self) -> Optional[str]:
        return self._tags_dict.get(TagName.Name)

    def get_reservation_id(self) -> Optional[str]:
        return self._tags_dict.get(TagName.ReservationId)

    def set_is_public_tag(self, is_public: bool):
        self._tags_dict[TagName.IsPublic] = str(is_public)

    def update_tags(self, tags_dict: Dict[str, str]):
        self._tags_dict.update(tags_dict)

    def get_isolation(self) -> Optional[IsolationTagValue]:
        try:
            value = IsolationTagValue(self.get(TagName.Isolation))
        except ValueError:
            value = None
        return value

    def get_type(self) -> Optional[TypeTagValue]:
        try:
            value = TypeTagValue(self.get(TagName.Type))
        except ValueError:
            value = None
        return value

    def add_tags_to_obj(self, aws_obj) -> None:
        try:
            self._add_tag_to_obj(aws_obj)
        except botocore.exceptions.ClientError as e:
            if "notfound" in str(e).lower():
                raise TagServiceCannotFindTheObject(aws_obj)
            else:
                raise

    @retry(
        wait_fixed=5 * 1000,
        stop_max_delay=5 * 60 * 1000,
        retry_on_exception=tag_service_cannot_find_obj,
    )
    def _add_tag_to_obj(self, aws_obj) -> None:
        try:
            aws_obj.create_tags(Tags=self.aws_tags)
        except AttributeError:
            ec2 = aws_obj.meta.client
            ec2.create_tags(Resources=(aws_obj.id,), Tags=self.aws_tags)
