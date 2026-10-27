class AgendaError(Exception):
    """A user-facing error (Spanish message) with the HTTP status the server should answer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
