"""Resolves the Gateway destination (identity propagation) via the BTP Destination/Connectivity services."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from .config import OAuthService, Settings
from .errors import GatewayError

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0)


@dataclass
class ResolvedTarget:
    """Everything needed to call the backend on behalf of one user. Never cache across users."""

    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    proxy_url: str | None = None


class _ClientCredentialsToken:
    def __init__(self, service: OAuthService) -> None:
        self._service = service
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._expires_at - 60:
                return self._token
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service.token_url}/oauth/token",
                    data={"grant_type": "client_credentials"},
                    auth=(self._service.client_id, self._service.client_secret),
                    headers={"Accept": "application/json"},
                )
            if resp.status_code != 200:
                logger.error("Service token request failed with HTTP %s", resp.status_code)
                raise GatewayError("DESTINATION_ERROR", "Could not obtain a service token.")
            body = resp.json()
            self._token = body["access_token"]
            self._expires_at = time.monotonic() + float(body.get("expires_in", 300))
            return self._token


class DestinationResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dest_token = _ClientCredentialsToken(settings.destination_service)
        self._conn_token = (
            _ClientCredentialsToken(settings.connectivity_service) if settings.connectivity_service else None
        )

    async def resolve(self, user_jwt: str) -> ResolvedTarget:
        config, auth_tokens = await self._find_destination(user_jwt)

        url = config.get("URL")
        if not url:
            raise GatewayError("DESTINATION_ERROR", "Destination has no URL.")
        target = ResolvedTarget(base_url=url.rstrip("/"))

        # Headers/query parameters configured on the destination (additional properties).
        for key, value in config.items():
            if key.startswith("URL.headers."):
                target.headers[key.removeprefix("URL.headers.")] = value
            elif key.startswith("URL.queries."):
                target.params[key.removeprefix("URL.queries.")] = value
        if config.get("sap-client"):
            target.params.setdefault("sap-client", config["sap-client"])

        # Authorization produced by the destination service (SAML bearer, token exchange, basic...).
        for token in auth_tokens:
            if token.get("error"):
                logger.error("Destination auth token error: %s", token["error"])
                raise GatewayError("DESTINATION_ERROR", "Destination could not produce an auth token.")
            header = token.get("http_header")
            if header:
                target.headers[header["key"]] = header["value"]

        if config.get("ProxyType") == "OnPremise":
            await self._apply_cloud_connector(target, config, user_jwt)
        return target

    async def _find_destination(self, user_jwt: str) -> tuple[dict[str, str], list[dict]]:
        service = self._settings.destination_service
        token = await self._dest_token.get()
        url = (
            f"{service.extra['uri'].rstrip('/')}/destination-configuration/v1/destinations/"
            f"{quote(self._settings.destination_name, safe='')}"
        )
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}", "X-user-token": user_jwt}
            )
        if resp.status_code == 404:
            raise GatewayError(
                "DESTINATION_ERROR", f"Destination '{self._settings.destination_name}' was not found."
            )
        if resp.status_code != 200:
            logger.error("Destination lookup failed with HTTP %s", resp.status_code)
            raise GatewayError("DESTINATION_ERROR", "Destination lookup failed.")
        body = resp.json()
        return body.get("destinationConfiguration", {}), body.get("authTokens", [])

    async def _apply_cloud_connector(self, target: ResolvedTarget, config: dict[str, str], user_jwt: str) -> None:
        conn = self._settings.connectivity_service
        if conn is None or self._conn_token is None:
            raise GatewayError(
                "DESTINATION_ERROR", "Destination is OnPremise but no connectivity service is bound."
            )
        host = conn.extra["onpremise_proxy_host"]
        port = conn.extra["onpremise_proxy_http_port"]
        target.proxy_url = f"http://{host}:{port}"
        target.headers["Proxy-Authorization"] = f"Bearer {await self._conn_token.get()}"
        if config.get("Authentication") == "PrincipalPropagation":
            # The Cloud Connector turns the user JWT into the short-lived certificate for the ECC login.
            target.headers["SAP-Connectivity-Authentication"] = f"Bearer {user_jwt}"
        if config.get("CloudConnectorLocationId"):
            target.headers["SAP-Connectivity-SCC-Location_ID"] = config["CloudConnectorLocationId"]
