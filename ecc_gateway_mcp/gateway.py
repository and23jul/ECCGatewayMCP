"""Minimal read-only OData V2 client that calls the backend through the resolved destination."""

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
        # A fresh client per call: the cookie jar (SAP session) must never be shared between users.
        return httpx.AsyncClient(
            base_url=target.base_url,
            headers={"Accept": "application/json", **target.headers},
            params=target.params,
            proxy=target.proxy_url,
            timeout=_TIMEOUT,
            follow_redirects=False,
        )

    async def get(self, user_jwt: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Return the OData V2 payload under `d` (a single entity, or {"results": [...]})."""
        target = await self._resolver.resolve(user_jwt)
        async with self._client(target) as client:
            resp = await client.get(path, params={"$format": "json", **(params or {})})
        return self._parse(resp)

    async def get_collection(
        self, user_jwt: str, path: str, params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Return the rows of an entity-set read as a list."""
        data = await self.get(user_jwt, path, params)
        results = data.get("results")
        if results is None:
            # A single entity read through a collection path still arrives under `d`.
            return [data] if data else []
        return results

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
