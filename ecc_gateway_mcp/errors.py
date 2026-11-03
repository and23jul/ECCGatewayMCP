"""Error type shared by all layers. The code is the stable part of the tool contract."""

from __future__ import annotations


class GatewayError(Exception):
    """Raised for any expected failure. Surfaces to the MCP client as `CODE: message`.

    Codes used: NOT_FOUND, FORBIDDEN, INVALID_INPUT, CONFIRMATION_REQUIRED, CANCELLED,
    BACKEND_NOT_CONFIGURED, BACKEND_ERROR, DESTINATION_ERROR.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
