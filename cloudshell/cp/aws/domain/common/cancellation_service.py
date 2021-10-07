from typing import Optional

from cloudshell.shell.core.driver_context import CancellationContext

from cloudshell.cp.aws.domain.common.exceptions import CancellationException


class CommandCancellationService:
    @staticmethod
    def check_if_cancelled(
        cancellation_context: CancellationContext, data: Optional[dict] = None
    ):
        check_if_cancelled(cancellation_context, data)


def check_if_cancelled(
    cancellation_context: CancellationContext, data: Optional[dict] = None
):
    """Check if command was cancelled from the CloudShell.

    :param cancellation_context: cancellation context
    :param dict data: Dictionary that will be added to the cancellation exception
        if raised. Use this container to add context data to the cancellation
        exception to be used by the exception handler
    :raises CancellationException
    """
    if cancellation_context and cancellation_context.is_cancelled:
        raise CancellationException("Command was cancelled", data)
