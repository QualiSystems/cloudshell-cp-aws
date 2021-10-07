import pytest

from cloudshell.shell.core.driver_context import ReservationContextDetails

from cloudshell.cp.aws.models.reservation_model import ReservationModel

from tests.base import VpcTest


@pytest.fixture()
def vpc():
    return VpcTest()


@pytest.fixture()
def reservation():
    context = ReservationContextDetails(
        environment_name="env name",
        environment_path="env path",
        domain="domain",
        description="descr",
        owner_user="user",
        owner_email="email",
        reservation_id="rid",
        saved_sandbox_name="sandbox name",
        saved_sandbox_id="sandbox id",
        running_user="running user",
    )
    return ReservationModel(context)
