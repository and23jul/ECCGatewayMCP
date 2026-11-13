# Backlog: ecc-gateway-mcp

Status: SHIPPED - Sales and Purchasing read tools are implemented and deployable.

## What the server does today

FastMCP server `ecc-gateway` (streamable-HTTP), XSUAA JWT validation with per-tool scope
checks, backend reads through destination `Gateway-x96-SSO` (OnPremise + principal
propagation via Cloud Connector). Two read-only ECC Gateway OData V2 services.

### Tools (all read-only)

| Tool | Scope | OData service | Entity set(s) |
|------|-------|---------------|---------------|
| `get_sales_order` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOHeadSet` + `SOItemSet` |
| `list_sales_orders` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOHeadSet` |
| `get_sales_order_items` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOItemSet` |
| `get_purchase_order` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POHeadSet` + `POItemSet` |
| `list_purchase_orders` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POHeadSet` |
| `get_purchase_order_items` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POItemSet` |

### Backend facts (metadata/Sales.edmx.xml, metadata/Purchase.edmx.xml)

- Sales `SOHeadSet`: key `SONumber`; fields `SONumber`, `SOCustomer` (only `SOCustomer`
  filterable). `SOItemSet`: key `SONumber`+`SOItemNo`; fields incl. `MaterialNo` (none
  filterable); no navigation from head to item - server filters items by key in memory.
- Purchasing `POHeadSet`: key `PONumber`; fields `PONumber`, `POVendor` (only `POVendor`
  filterable). `POItemSet`: key `PONumber`+`POItemNo`; fields incl. `MaterialNo`. Head has a
  navigation to items (`EKKO_EKPO`), so items are read through the nav path.
- Both services are pageable=false: the server reads up to `MAX_BACKEND_ROWS` (default 5000)
  then filters and paginates in memory. Numeric keys auto zero-padded to 10 chars.

### Deployment (manifest.yml + xs-security.json)

- App `ecc-gateway-mcp`, python buildpack, binds: `XSUAA-application-ECCGatewayMCP`,
  `DEST-lite-Restricted` (reused), `CONN-lite-ECCGatewayMCP`.
- Scopes `SalesRead`, `PurchasingRead`. Role templates `ZROL-APP-ECCGatewayMCP-ViewSales`
  / `-ViewPurchasing` / `-ViewAll`. Role collections `ZROC-APP-ECCGatewayMCP-SalesViewer`
  / `-PurchasingViewer` / `-Viewer`.
- Client connection guide: see `CONNECTING.md`.

## Open ideas / future work

1. Material-based lookup: no tool today routes "orders containing material X" because
   `MaterialNo` is not filterable on either item set. Would need in-server scan of the item
   set (bounded by `MAX_BACKEND_ROWS`) and a new tool + clear docstring so the LLM can route
   to it.
2. Consider exposing additional filterable head fields if the backend services add them.
3. Token refresh helper for clients (XSUAA access tokens are short-lived).
4. UI5 front-end over MCP (Option A: natural-language app). A UI5 app that holds NO ECC
   destination binding; all backend retrieval stays in this MCP server. Flow:
   UI5 -> approuter -> agent service (LLM + MCP client) -> ecc-gateway-mcp -> destination/CC -> ECC.
   Key prep:
   - New agent service (CF app): MCP client over streamable-HTTP + an LLM. Exposes a simple
     endpoint (e.g. POST /chat) to the UI; calls the LLM with the 6 tool defs, runs the chosen
     tool, returns results.
   - Token exchange: approuter user JWT -> jwt-bearer exchange to a token with aud=ecc-gateway-mcp,
     preserving user identity (same identity zone/subaccount). MCP server needs a USER token for
     principal propagation (see destination.py: X-user-token / SAP-Connectivity-Authentication).
   - Role collections ZROC-APP-ECCGatewayMCP-* assigned to UI users so the exchanged token carries
     SalesRead/PurchasingRead.
   - UI5 app + approuter (reuse APSAppRouter pattern: html5-apps-repo app-runtime + destination to
     the agent service, NOT to ECC).
   - New BTP resources: agent CF app + its own XSUAA (configured for token exchange), optional
     SAP Generative AI Hub / AI Core if the LLM runs on BTP; html5-apps-repo app-host for the UI.
   Decisions to settle first: (a) LLM hosting (SAP Generative AI Hub vs external - data residency);
   (b) structured data vs chat-text output (shapes UI + agent response contract);
   (c) whether ECC business data may transit an external LLM.
   Build order: stand up agent locally against deployed MCP with a hand-minted user token; solve
   approuter->agent->MCP token exchange; build UI5+approuter; wire role collections and verify
   principal propagation for a UI user end-to-end.

## History

- Earlier exploration targeted Purchase Requisition reads (getPRList/getPRTexts) from
  `ZMYOPTIMA_SQUOTE_SRV` and an initial sales scenario on `API_SALES_ORDER_SRV`. That
  direction was superseded: the shipped server uses the dedicated read-only ECC Gateway
  services `ZGW_ECCMCP_SALES_SRV` and `ZGW_ECCMCP_PURCHASING_SRV` with the tool set above.
- Repo: https://github.com/and23jul/ECCGatewayMCP
