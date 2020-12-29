from cloudshell.cp.aws.domain.common.exceptions import CancellationException


class CommandCancellationService:
    def check_if_cancelled(self, cancellation_context, data=None):
        """Check if command was cancelled from the CloudShell.

        :param cancellation_context cloudshell.shell.core.driver_context.CancellationContext instance  # noqa: E501
        :param dict data: Dictionary that will be added to the cancellation exception
            if raised. Use this container to add context data to the cancellation
            exception to be used by the exception handler
        :raises cloudshell.cp.azure.common.exceptions.cancellation_exception.CancellationException  # noqa: E501
        :return:
        """
        if cancellation_context and cancellation_context.is_cancelled:
            raise CancellationException("Command was cancelled", data)
