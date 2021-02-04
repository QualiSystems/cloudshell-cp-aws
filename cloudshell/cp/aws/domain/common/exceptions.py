class CancellationException(Exception):
    """Raised when command was cancelled from the CloudShell."""

    def __init__(self, message: str, data: dict):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)

        self.data = data if data else {}
