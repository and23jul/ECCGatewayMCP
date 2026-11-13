"""GatewayClient OData V2 parsing and HTTP status -> GatewayError mapping."""

from __future__ import annotations

import httpx
import pytest

from ecc_gateway_mcp.destination import ResolvedTarget
from ecc_gateway_mcp.errors import GatewayError
from ecc_gateway_mcp.gateway import GatewayClient


class _Resolver:
    """Resolver stub that points the client at a transport-mocked base URL."""

    def __init__(self, transport: httpx.MockTransport) -> None:
        self._transport = transport

    async def resolve(self, jwt: str) -> ResolvedTarget:
        return ResolvedTarget(base_url="http://backend")

    # GatewayClient builds its own AsyncClient; patch it to use the mock transport.
    def patch(self, client: GatewayClient) -> None:
        orig = client._client

        def _with_transport(target):
            c = orig(target)
            c._transport = self._transport
            # httpx dispatches through the per-URL transport map; override the default.
            c._mounts = {}
            return c

        client._client = _with_transport  # type: ignore[assignment]


def _make_client(handler) -> GatewayClient:
    transport = httpx.MockTransport(handler)
    resolver = _Resolver(transport)
    client = GatewayClient(resolver)
    resolver.patch(client)
    return client


async def test_get_collection_unwraps_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"d": {"results": [{"SONumber": "1"}, {"SONumber": "2"}]}})

    rows = await _make_client(handler).get_collection("jwt", "/SOHeadSet")
    assert [r["SONumber"] for r in rows] == ["1", "2"]


async def test_get_collection_wraps_single_entity():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"d": {"SONumber": "1"}})

    rows = await _make_client(handler).get_collection("jwt", "/SOHeadSet('1')")
    assert rows == [{"SONumber": "1"}]


@pytest.mark.parametrize(
    "status,code",
    [(401, "FORBIDDEN"), (403, "FORBIDDEN"), (404, "NOT_FOUND"), (500, "BACKEND_ERROR")],
)
async def test_status_maps_to_error_code(status, code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="backend detail that must not leak")

    with pytest.raises(GatewayError) as exc:
        await _make_client(handler).get("jwt", "/SOHeadSet('1')")
    assert exc.value.code == code
    # raw backend body is never surfaced in the client-facing message
    assert "backend detail" not in exc.value.message


async def test_non_odata_body_is_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(GatewayError) as exc:
        await _make_client(handler).get("jwt", "/SOHeadSet('1')")
    assert exc.value.code == "BACKEND_ERROR"
