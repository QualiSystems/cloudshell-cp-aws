import time
from enum import Enum
from typing import TYPE_CHECKING, Generator, Optional

import attr
from retrying import retry

from cloudshell.cp.aws.common.cached_property import cached_property, invalidated_cache
from cloudshell.cp.aws.domain.handlers.ec2 import TagsHandler

if TYPE_CHECKING:
    from logging import Logger

    from mypy_boto3_ec2 import EC2ServiceResource  # noqa: I900
    from mypy_boto3_ec2.service_resource import Vpc, VpcPeeringConnection  # noqa: I900

    from cloudshell.cp.aws.models.reservation_model import ReservationModel


CONNECTION_NAME_FORMAT = "Peering connection for {} with management vpc"


def get_connection_name(reservation_id: str) -> str:
    return CONNECTION_NAME_FORMAT.format(reservation_id)


class Status(Enum):
    PENDING_ACCEPTANCE = "pending-acceptance"
    ACTIVE = "active"
    DELETED = "deleted"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"
    PROVISIONING = "provisioning"
    DELETING = "deleting"
    OTHER = "_other"

    @classmethod
    def get(cls, status_code: str, msg: Optional[str] = None) -> "Status":
        try:
            status = cls(status_code)
        except ValueError:
            status = cls.OTHER
        status.msg = msg
        return status

    @property
    def msg(self) -> Optional[str]:
        return getattr(self, "_msg", None)

    @msg.setter
    def msg(self, value: str):
        self._msg = value


class VpcPeeringConnectionError(Exception):
    ...


class VpcPeeringConnectionNotFoundForReservation(VpcPeeringConnectionError):
    def __init__(self, reservation_id: str):
        self.reservation_id = reservation_id
        super().__init__(
            f"VPC peering connection for reservation {reservation_id} is not found"
        )


class VpcPeeringConnectionFailedStatus(VpcPeeringConnectionError):
    def __init__(
        self,
        status: Status,
        expected_status: Status,
    ):
        self.status = status
        self.expected_status = expected_status
        msg = f"VPC Peering connection status is {status.value}"
        if status.msg:
            msg += f", status message '{status.msg}'"
        msg += f". Expected status {expected_status.value}"
        super().__init__(msg)


class VpcPeeringConnectionWaitTimeout(VpcPeeringConnectionError):
    def __init__(
        self,
        status: Status,
        expected_status: Status,
    ):
        self.status = status
        self.expected_status = expected_status
        msg = (
            f"Timeout waiting for VPC Peering connection status to be "
            f"{expected_status.value}. Current status is {status.value}"
        )
        super().__init__(msg)


@attr.s(auto_attribs=True)
class VpcPeeringHandler:
    _vpc_peering: "VpcPeeringConnection"

    @classmethod
    def get_active_by_reservation_id(
        cls, ec2_session: "EC2ServiceResource", reservation_id: str
    ) -> "VpcPeeringHandler":
        vpc_peerings = ec2_session.vpc_peering_connections.filter(
            Filters=[{"Name": "tag:ReservationId", "Values": [reservation_id]}]
        )
        for connection in map(cls, vpc_peerings):
            if connection.is_active:
                return connection
        raise VpcPeeringConnectionNotFoundForReservation(reservation_id)

    @classmethod
    def yield_live_peerings(
        cls, vpc: "Vpc"
    ) -> Generator["VpcPeeringHandler", None, None]:
        for peering in map(cls, vpc.accepted_vpc_peering_connections.all()):
            if not peering.is_failed:
                yield peering

    @classmethod
    def create(
        cls,
        ec2_session: "EC2ServiceResource",
        vpc_id1: str,
        vpc_id2: str,
        reservation: "ReservationModel",
        logger: "Logger",
    ) -> "VpcPeeringHandler":
        inst = cls(
            ec2_session.create_vpc_peering_connection(VpcId=vpc_id1, PeerVpcId=vpc_id2)
        )
        logger.debug(f"VPC Peering created {inst.id}, Status: {inst.status.value}")

        logger.debug(
            f"Waiting until VPC peering connection {inst.id} status will be "
            f"{Status.PENDING_ACCEPTANCE.value}"
        )
        inst.wait_until_status(Status.PENDING_ACCEPTANCE)

        logger.debug(f"Accepting VPC peering connection {inst.id}")
        inst.accept_peering()

        logger.debug(f"Waiting until VPC peering status will be {Status.ACTIVE}")
        inst.wait_until_status(Status.ACTIVE)

        connection_name = get_connection_name(reservation.reservation_id)
        tags = TagsHandler.create_default_tags(connection_name, reservation)
        inst.add_tags(tags)

        return inst

    @property
    def status(self) -> Status:
        return Status.get(
            self._vpc_peering.status["Code"], self._vpc_peering.status.get("Message")
        )

    @property
    def is_active(self) -> bool:
        return self.status is Status.ACTIVE

    @property
    def is_failed(self) -> bool:
        return self.status is Status.FAILED

    @property  # noqa: A003
    def id(self) -> str:  # noqa: A003
        return self._vpc_peering.id

    @cached_property
    def tags(self) -> "TagsHandler":
        self.update()
        return TagsHandler.from_tags_list(self._vpc_peering.tags)

    @property
    def name(self) -> str:
        return self.tags.get_name()

    def _update_tags(self):
        invalidated_cache(self, "tags")

    def delete(self):
        self._vpc_peering.delete()

    @retry(stop_max_attempt_number=30, wait_fixed=1000)
    def update(self):
        self._vpc_peering.load()

    def wait_until_status(
        self,
        status: Status,
        delay: int = 10,
        timeout: int = 10 * 60,
        raise_on_error: bool = True,
    ):
        start_time = time.time()
        while self.status != status:
            if raise_on_error and self.status in (
                Status.REJECTED,
                Status.FAILED,
            ):
                raise VpcPeeringConnectionFailedStatus(self.status, status)

            if time.time() - start_time > timeout:
                raise VpcPeeringConnectionWaitTimeout(self.status, status)
            time.sleep(delay)
            self.update()

    @retry(stop_max_attempt_number=30, wait_fixed=1000)
    def accept_peering(self):
        self._vpc_peering.accept()

    def add_tags(self, tags: TagsHandler):
        tags.add_tags_to_obj(self._vpc_peering)
        self._update_tags()
