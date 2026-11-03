"""Inbound authentication: validates XSUAA JWTs and enforces per-tool scopes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from .config import XsuaaBinding
from .errors import GatewayError

logger = logging.getLogger(__name__)


class XsuaaTokenVerifier:
    """Implements the MCP `TokenVerifier` protocol for tokens issued by the bound XSUAA."""

    def __init__(self, binding: XsuaaBinding) -> None:
        self._binding = binding
        # Keys are always fetched from the bound XSUAA, never from the token's own `jku` header.
        self._jwks = PyJWKClient(f"{binding.url}/token_keys", cache_keys=True, lifespan=3600)

    def _decode(self, token: str) -> dict[str, Any]:
        key = self._jwks.get_signing_key_from_jwt(token).key
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"require": ["exp", "iss"], "verify_aud": False},
        )
        aud = claims.get("aud") or []
        audiences = {aud} if isinstance(aud, str) else set(aud)
        if not audiences & {self._binding.xsappname, self._binding.client_id}:
            raise jwt.InvalidAudienceError("token was not issued for this application")
        zone = claims.get("zid")
        if self._binding.tenant_id and zone and zone != self._binding.tenant_id:
            raise jwt.InvalidTokenError("token belongs to a different identity zone")
        return claims

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(self._decode, token)
        except jwt.PyJWTError as exc:
            logger.info("Rejected bearer token: %s", type(exc).__name__)
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("cid") or claims.get("client_id") or ""),
            scopes=list(claims.get("scope") or []),
            expires_at=claims.get("exp"),
            subject=claims.get("user_name") or claims.get("sub"),
        )


class Authorizer:
    """Maps the contract's authorization names (e.g. SalesOrderRead) to XSUAA scopes."""

    def __init__(self, xsappname: str) -> None:
        self._xsappname = xsappname

    def require(self, permission: str) -> str:
        """Return the caller's JWT if it holds `permission`, otherwise raise FORBIDDEN."""
        token = get_access_token()
        if token is None or f"{self._xsappname}.{permission}" not in token.scopes:
            raise GatewayError("FORBIDDEN", f"Caller lacks {permission} permission.")
        return token.token
