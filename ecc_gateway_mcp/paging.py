"""In-server pagination helpers.

Both ECC Gateway services declare their entity sets sap:pageable="false", so the backend
ignores $top/$skip/$orderby. We therefore read a bounded result set and paginate in memory,
exposing an opaque page token to the MCP client.
"""

from __future__ import annotations

import base64
import json

from .errors import GatewayError


def encode_page_token(skip: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"skip": skip}).encode()).decode()


def decode_page_token(token: str) -> int:
    try:
        skip = json.loads(base64.urlsafe_b64decode(token.encode()))["skip"]
        if isinstance(skip, int) and skip >= 0:
            return skip
    except (ValueError, KeyError, TypeError):
        pass
    raise GatewayError("INVALID_INPUT", "page_token is not valid.")


def paginate(rows: list, skip: int, limit: int) -> tuple[list, str | None]:
    """Slice `rows` and return (page, next_page_token). next token is None at the end."""
    window = rows[skip : skip + limit]
    has_more = len(rows) > skip + limit
    return window, (encode_page_token(skip + limit) if has_more else None)
