"""Page-token round-trip, validation, and in-server slicing."""

from __future__ import annotations

import pytest

from ecc_gateway_mcp.errors import GatewayError
from ecc_gateway_mcp.paging import decode_page_token, encode_page_token, paginate


def test_token_round_trip():
    assert decode_page_token(encode_page_token(30)) == 30
    assert decode_page_token(encode_page_token(0)) == 0


@pytest.mark.parametrize("bad", ["", "not-base64!!", "YWJj", "e30="])  # garbage, non-json, {} without skip
def test_invalid_token_raises_invalid_input(bad):
    with pytest.raises(GatewayError) as exc:
        decode_page_token(bad)
    assert exc.value.code == "INVALID_INPUT"


def test_negative_skip_rejected():
    with pytest.raises(GatewayError):
        decode_page_token(encode_page_token(-5))


def test_paginate_middle_and_end():
    rows = list(range(25))
    window, token = paginate(rows, skip=0, limit=10)
    assert window == list(range(10)) and token is not None

    window, token = paginate(rows, skip=20, limit=10)
    assert window == list(range(20, 25)) and token is None


def test_paginate_skip_past_end_is_empty():
    window, token = paginate([1, 2, 3], skip=10, limit=10)
    assert window == [] and token is None
