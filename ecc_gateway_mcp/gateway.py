"""Minimal OData V2 client that calls the backend through the resolved destination."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .destination import DestinationResolver, ResolvedTarget
from .errors import GatewayError

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0)


class GatewayClient:
    def __init__(self, resolver: DestinationResolver) -> None:
        self._resolver = resolver

    def _client(self, target: ResolvedTarget) -> httpx.AsyncClient:
        # A fresh client per call: the cookie jar (SAP session / CSRF) must never be shared between users.
        return httpx.AsyncClient(
            base_url=target.base_url,
            headers={"Accept": "application/json", **target.headers},
            params=target.params,
            proxy=target.proxy_url,
            timeout=_TIMEOUT,
            follow_redirects=False,
        )

    async def get(self, user_jwt: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        target = await self._resolver.resolve(user_jwt)
        async with self._client(target) as client:
            resp = await client.get(path, params={"$format": "json", **(params or {})})
        return self._parse(resp)

    async def post(self, user_jwt: str, service_root: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        target = await self._resolver.resolve(user_jwt)
        async with self._client(target) as client:
            fetch = await client.get(service_root, headers={"X-CSRF-Token": "Fetch"})
            csrf = fetch.headers.get("x-csrf-token")
            if fetch.status_code >= 400 or not csrf:
                self._parse(fetch)  # raises a mapped error for 401/403
                raise GatewayError("BACKEND_ERROR", "Backend did not issue a CSRF token.")
            resp = await client.post(path, json=body, headers={"X-CSRF-Token": csrf})
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code in (401, 403):
            raise GatewayError("FORBIDDEN", "Backend denied access for the calling user.")
        if resp.status_code == 404:
            raise GatewayError("NOT_FOUND", "Resource does not exist or is not visible to caller.")
        if resp.status_code >= 400:
            # Backend bodies can contain internal details; keep them in the log only.
            logger.error("Backend returned HTTP %s: %.500s", resp.status_code, resp.text)
            raise GatewayError("BACKEND_ERROR", f"Backend request failed (HTTP {resp.status_code}).")
        try:
            return resp.json()["d"]
        except (ValueError, KeyError):
            logger.error("Unexpected backend payload: %.500s", resp.text)
            raise GatewayError("BACKEND_ERROR", "Backend returned an unexpected response.") from None
