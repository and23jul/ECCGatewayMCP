"""Shared fixtures: synthetic Settings and fake gateways. No credentials or real backends."""

from __future__ import annotations

from typing import Any

import pytest

from ecc_gateway_mcp.config import OAuthService, Settings, XsuaaBinding

SALES_PATH = "/sap/opu/odata/sap/ZGW_ECCMCP_SALES_SRV"
PURCHASING_PATH = "/sap/opu/odata/sap/ZGW_ECCMCP_PURCHASING_SRV"


@pytest.fixture
def settings() -> Settings:
    dummy = OAuthService(token_url="https://uaa", client_id="c", client_secret="s", extra={})
    return Settings(
        port=8080,
        public_url="http://localhost:8080",
        xsuaa=XsuaaBinding(url="https://uaa", client_id="c", xsappname="ecc-gateway-mcp", tenant_id=None),
        destination_service=dummy,
        connectivity_service=None,
        destination_name="Gateway-x96-SSO",
        sales_service_path=SALES_PATH,
        sales_head_entity_set="SOHeadSet",
        sales_item_entity_set="SOItemSet",
        purchasing_service_path=PURCHASING_PATH,
        purchasing_head_entity_set="POHeadSet",
        purchasing_item_entity_set="POItemSet",
        max_backend_rows=5000,
    )


class FakeGateway:
    """Fake GatewayClient. `single` maps a full path to one entity; `collection` maps a path to rows.

    Records every requested path in `.calls`, and the params in `.params_for`, so tests can assert
    that server-side $filter is only sent on filterable fields.
    """

    def __init__(
        self,
        single: dict[str, dict[str, Any]] | None = None,
        collection: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._single = single or {}
        self._collection = collection or {}
        self.calls: list[str] = []
        self.params_for: list[tuple[str, dict | None]] = []

    async def get(self, jwt: str, path: str, params: dict | None = None) -> dict[str, Any]:
        self.calls.append(path)
        self.params_for.append((path, params))
        return self._single[path]

    async def get_collection(self, jwt: str, path: str, params: dict | None = None) -> list[dict[str, Any]]:
        self.calls.append(path)
        self.params_for.append((path, params))
        return self._collection.get(path, [])
