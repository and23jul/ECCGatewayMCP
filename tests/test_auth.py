"""Authorizer scope enforcement. Token verification (JWT/JWKS) needs XSUAA and is not unit-tested here."""

from __future__ import annotations

import pytest

from mcp.server.auth.middleware import auth_context
from mcp.server.auth.provider import AccessToken

from ecc_gateway_mcp.auth import Authorizer
from ecc_gateway_mcp.errors import GatewayError


def _token(scopes: list[str]) -> AccessToken:
    return AccessToken(token="jwt-value", client_id="cid", scopes=scopes, expires_at=None)


def _set_context(token: AccessToken | None):
    # AuthContext middleware stores the token in a ContextVar; set it directly for the unit test.
    return auth_context.auth_context_var.set(
        auth_context.AuthenticatedUser(token) if token else None
    )


def test_require_returns_jwt_when_scope_present():
    reset = _set_context(_token(["ecc-gateway-mcp.SalesRead"]))
    try:
        assert Authorizer("ecc-gateway-mcp").require("SalesRead") == "jwt-value"
    finally:
        auth_context.auth_context_var.reset(reset)


def test_require_forbidden_when_scope_missing():
    reset = _set_context(_token(["ecc-gateway-mcp.PurchasingRead"]))
    try:
        with pytest.raises(GatewayError) as exc:
            Authorizer("ecc-gateway-mcp").require("SalesRead")
        assert exc.value.code == "FORBIDDEN"
    finally:
        auth_context.auth_context_var.reset(reset)


def test_require_forbidden_when_no_token():
    reset = _set_context(None)
    try:
        with pytest.raises(GatewayError) as exc:
            Authorizer("ecc-gateway-mcp").require("SalesRead")
        assert exc.value.code == "FORBIDDEN"
    finally:
        auth_context.auth_context_var.reset(reset)
