"""FastMCP server `ecc-gateway`: read-only Sales and Purchasing tools, auth wiring, entry point."""

from __future__ import annotations

import logging
from typing import Annotated

from mcp import types
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .auth import Authorizer, XsuaaTokenVerifier
from .config import Settings, load_settings
from .destination import DestinationResolver
from .gateway import GatewayClient
from .models import (
    CustomerId,
    PurchaseOrderDetail,
    PurchaseOrderId,
    PurchaseOrderItem,
    PurchaseOrderPage,
    SalesOrderDetail,
    SalesOrderId,
    SalesOrderItem,
    SalesOrderPage,
    VendorId,
)
from .purchasing import PurchasingService
from .sales import SalesService

logger = logging.getLogger(__name__)

# Every tool here is a read; the backend services are creatable/updatable/deletable = false.
_READ_ONLY = types.ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)

_Limit = Annotated[int, Field(ge=1, le=50, description="Maximum items to return.")]
_PageToken = Annotated[str | None, Field(description="next_page_token from a previous call.")]


def create_server(settings: Settings, gateway: GatewayClient | None = None) -> FastMCP:
    gateway = gateway or GatewayClient(DestinationResolver(settings))
    sales = SalesService(settings, gateway)
    purchasing = PurchasingService(settings, gateway)
    authz = Authorizer(settings.xsuaa.xsappname)

    mcp = FastMCP(
        "ecc-gateway",
        host="0.0.0.0",
        port=settings.port,
        stateless_http=True,
        json_response=False,
        token_verifier=XsuaaTokenVerifier(settings.xsuaa),
        auth=AuthSettings(
            issuer_url=settings.xsuaa.url,
            resource_server_url=settings.public_url,
            # Audience is checked by XsuaaTokenVerifier, not via RFC 8707 resource indicators.
            validate_token_resource=False,
        ),
    )

    # --- Sales (ZGW_ECCMCP_SALES_SRV) -----------------------------------------------------------

    @mcp.tool(annotations=_READ_ONLY)
    async def get_sales_order(sales_order_id: SalesOrderId) -> SalesOrderDetail:
        """Read one sales document (customer and its items).

        Errors: NOT_FOUND (document does not exist or is not visible to caller),
        FORBIDDEN (caller lacks SalesRead permission).
        """
        jwt = authz.require("SalesRead")
        return await sales.get_order(jwt, sales_order_id)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_sales_orders(
        customer_id: CustomerId | None = None,
        limit: _Limit = 10,
        page_token: _PageToken = None,
    ) -> SalesOrderPage:
        """List sales documents, optionally filtered by customer."""
        jwt = authz.require("SalesRead")
        return await sales.list_orders(jwt, customer_id, limit, page_token)

    @mcp.tool(annotations=_READ_ONLY)
    async def get_sales_order_items(sales_order_id: SalesOrderId) -> list[SalesOrderItem]:
        """List the item lines of one sales document."""
        jwt = authz.require("SalesRead")
        return await sales.list_items(jwt, sales_order_id)

    # --- Purchasing (ZGW_ECCMCP_PURCHASING_SRV) -------------------------------------------------

    @mcp.tool(annotations=_READ_ONLY)
    async def get_purchase_order(purchase_order_id: PurchaseOrderId) -> PurchaseOrderDetail:
        """Read one purchasing document (vendor and its items).

        Errors: NOT_FOUND (document does not exist or is not visible to caller),
        FORBIDDEN (caller lacks PurchasingRead permission).
        """
        jwt = authz.require("PurchasingRead")
        return await purchasing.get_order(jwt, purchase_order_id)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_purchase_orders(
        vendor_id: VendorId | None = None,
        limit: _Limit = 10,
        page_token: _PageToken = None,
    ) -> PurchaseOrderPage:
        """List purchasing documents, optionally filtered by vendor."""
        jwt = authz.require("PurchasingRead")
        return await purchasing.list_orders(jwt, vendor_id, limit, page_token)

    @mcp.tool(annotations=_READ_ONLY)
    async def get_purchase_order_items(purchase_order_id: PurchaseOrderId) -> list[PurchaseOrderItem]:
        """List the item lines of one purchasing document."""
        jwt = authz.require("PurchasingRead")
        return await purchasing.list_items(jwt, purchase_order_id)

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO, which would put business data (filters, ids) in the logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    create_server(load_settings()).run(transport="streamable-http")


if __name__ == "__main__":
    main()
