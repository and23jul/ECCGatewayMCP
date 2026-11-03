"""FastMCP server `sap-sales`: tools, auth wiring and entry point."""

from __future__ import annotations

import logging
from typing import Annotated

from mcp import types
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from .auth import Authorizer, XsuaaTokenVerifier
from .config import Settings, load_settings
from .destination import DestinationResolver
from .errors import GatewayError
from .gateway import GatewayClient
from .models import (
    CustomerId,
    DraftItem,
    DraftResult,
    OrderStatus,
    SalesOrderId,
    SalesOrderPage,
    SalesOrderSummary,
    _Confirmation,
)
from .sales import SalesService

logger = logging.getLogger(__name__)

_READ_ONLY = types.ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
_CREATE = types.ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)


def create_server(settings: Settings, gateway: GatewayClient | None = None) -> FastMCP:
    gateway = gateway or GatewayClient(DestinationResolver(settings))
    sales = SalesService(settings, gateway)
    authz = Authorizer(settings.xsuaa.xsappname)

    mcp = FastMCP(
        "sap-sales",
        host="0.0.0.0",
        port=settings.port,
        # Stateful sessions are required for confirmation (elicitation) in create_sales_order_draft.
        stateless_http=False,
        json_response=False,
        token_verifier=XsuaaTokenVerifier(settings.xsuaa),
        auth=AuthSettings(
            issuer_url=settings.xsuaa.url,
            resource_server_url=settings.public_url,
            # Audience is checked by XsuaaTokenVerifier, not via RFC 8707 resource indicators.
            validate_token_resource=False,
        ),
    )

    @mcp.tool(annotations=_READ_ONLY)
    async def get_sales_order(sales_order_id: SalesOrderId) -> SalesOrderSummary:
        """Read one sales order summary.

        Errors: NOT_FOUND (order does not exist or is not visible to caller),
        FORBIDDEN (caller lacks SalesOrderRead permission).
        """
        jwt = authz.require("SalesOrderRead")
        return await sales.get_order(jwt, sales_order_id)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_sales_orders(
        customer_id: CustomerId | None = None,
        status: OrderStatus | None = None,
        limit: Annotated[int, Field(ge=1, le=50, description="Maximum items to return.")] = 10,
        page_token: Annotated[str | None, Field(description="next_page_token of a previous call.")] = None,
    ) -> SalesOrderPage:
        """Find sales orders using supported filters."""
        jwt = authz.require("SalesOrderRead")
        return await sales.list_orders(jwt, customer_id, status, limit, page_token)

    @mcp.tool(annotations=_CREATE)
    async def create_sales_order_draft(
        customer_id: CustomerId,
        items: Annotated[list[DraftItem], Field(min_length=1, max_length=100)],
        ctx: Context,
    ) -> DraftResult:
        """Create a draft sales order for review; does not submit it. Asks the user to confirm first."""
        jwt = authz.require("SalesOrderCreate")

        # confirmation_required: never create anything unless the user explicitly said yes.
        if not ctx.session.check_client_capability(
            types.ClientCapabilities(elicitation=types.ElicitationCapability())
        ):
            raise GatewayError(
                "CONFIRMATION_REQUIRED",
                "This client cannot ask the user for confirmation, so no draft was created.",
            )
        lines = "\n".join(f"- {i.quantity:g} {i.unit} of {i.material_id}" for i in items)
        answer = await ctx.elicit(
            f"Create a draft sales order for customer {customer_id}?\n{lines}", _Confirmation
        )
        if answer.action != "accept" or not answer.data.confirm:
            raise GatewayError("CANCELLED", "The user did not confirm; no draft was created.")

        return await sales.create_draft(jwt, customer_id, items)

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO, which would put business data (filters, ids) in the logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    create_server(load_settings()).run(transport="streamable-http")


if __name__ == "__main__":
    main()
