import time
from typing import TYPE_CHECKING

from cloudshell.cp.aws.common import retry_helper

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import VpcPeeringConnection


class VpcPeeringConnectionWaiter:
    INITIATING_REQUEST = ("initiating-request",)
    PENDING_ACCEPTANCE = "pending-acceptance"
    ACTIVE = "active"
    DELETED = "deleted"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"
    PROVISIONING = "provisioning"
    DELETING = "deleting"

    STATES = [
        INITIATING_REQUEST,
        PENDING_ACCEPTANCE,
        ACTIVE,
        DELETED,
        REJECTED,
        FAILED,
        EXPIRED,
        PROVISIONING,
        DELETING,
    ]

    def __init__(self, delay=10, timeout=10):
        """# noqa
        :param delay: the time in seconds between each pull
        :type delay: int
        :param timeout: timeout in minutes until time out exception will raised
        :type timeout: int
        """
        self.delay = delay
        self.timeout = timeout * 60

    def wait(
        self,
        vpc_peering_connection: "VpcPeeringConnection",
        state: str,
        throw_on_error: bool = True,
        load: bool = False,
    ):
        """Will sync wait for the change of state of the instance."""
        if not vpc_peering_connection:
            raise ValueError("Vpc Peering Connection cannot be null")
        if state not in self.STATES:
            raise ValueError("Unsupported vpc peering connection state")

        start_time = time.time()
        while vpc_peering_connection.status["Code"] != state:
            retry_helper.do_with_retry(lambda: vpc_peering_connection.reload())
            status_code = vpc_peering_connection.status["Code"]
            status_msg = vpc_peering_connection.status.get("Message")
            if status_code == state:
                break
            if throw_on_error and status_code in [
                VpcPeeringConnectionWaiter.REJECTED,
                VpcPeeringConnectionWaiter.FAILED,
            ]:
                msg = f"Error: vpc peering connection state is {status_code}"
                if status_msg:
                    msg += f', status message "{status_msg}"'
                msg += f". Expected state: {state}."
                raise Exception(msg)

            if time.time() - start_time >= self.timeout:
                raise Exception(
                    f"Timeout waiting for vpc peering connection to be {state}. "
                    f"Current state is {status_code}"
                )
            time.sleep(self.delay)

        if load:
            retry_helper.do_with_retry(lambda: vpc_peering_connection.reload())
        return vpc_peering_connection
