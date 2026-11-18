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

## Chat UI (v1.0.0, mock mode) - shipped 2026-11-03

Commit 52d4a13. Implements the first slice of idea 4 above: a UI5 chat front-end that forwards the
prompt to the workflow API. Not deployed yet; runs locally with a mock reply.

- `ui/`: UI5 app (OpenUI5 CDN, Horizon). `util/ChatClient.js` POSTs `{prompt}` to
  `workflow/chat` (relative URL, CSRF token fetch, 403 retry once, 30s timeout) and shows the
  `text` field of the `{text}` reply; `rows` is ignored for now. Mock mode on localhost or
  `?mock=true`; `?mock=false` forces the real endpoint. A prompt containing "error" simulates a failure.
- `approuter/xs-app.json` and `ui/webapp/xs-app.json`: `/workflow/*` -> destination
  `AWSService-CTC-NoSSO` (xsuaa login, CSRF on, scope SalesRead OR PurchasingRead), catch-all ->
  `html5-apps-repo-rt`.
- `mta.yaml` (repo root, UI + deployer + approuter only; the Python app still deploys with
  `cf push` and `manifest.yml`). Binds existing `XSUAA-application-ECCGatewayMCP`,
  `DEST-lite-Restricted`, `HTML5-app_runtime-Restricted`; creates `HTML5-app_host-ECCGatewayMCP`.
  Connectivity binding (`CONN-lite-ECCGatewayMCP`) is commented out.
- Tests: `cd ui && npm test` (15 QUnit tests in Node; same tests run in the browser at
  `/test/unit/unitTests.qunit.html` under `npm start`), `cd approuter && npm test` (8 route tests),
  `pytest` for the Python app (28 passing).
- Assumptions to confirm: landscape eu10-004 in the same space as DEST-lite-Restricted; route host
  `ecc-gateway-chat`; UI5 namespace `aps.pco.eccgatewaychat`.

### Next steps

Manual (cannot be done from the repo):
1. `cf update-service XSUAA-application-ECCGatewayMCP -c xs-security.json` (adds the approuter
   redirect URI; the MTA binds this instance as existing-service so it never applies the file).
2. Create the subaccount destination `AWSService-CTC-NoSSO` in the cockpit: OAuth2ClientCredentials,
   real workflow URL, token URL, client id/secret. If the workflow host is only reachable through
   the Cloud Connector: Proxy Type OnPremise, add the host in the Cloud Connector, and enable the
   connectivity binding (approuter `requires` + resource) in `mta.yaml`.
3. Build and deploy using the header of `mta.yaml`:
   `mbt module-build -m ecc-gateway-chat-ui -m ecc-gateway-chat-ui-deployer -m ecc-gateway-chat-approuter -a -g`
   then `cf deploy mta_archives/ecc-gateway-chat_1.0.0.mtar -f`.
4. Assign a `ZROC-APP-ECCGatewayMCP-*` role collection to every chat user (the `/workflow` route
   needs SalesRead or PurchasingRead).

Blocked on workflow connectivity details (still unknown):
5. Workflow endpoint URL and path, OAuth grant type and token URL, and how the CF app reaches the
   private network (Cloud Connector, VPN/Private Link, or a gateway). Then set the real route
   `target` in both `xs-app.json` files (currently a placeholder, one-line change).
6. Confirm the workflow works as a thin LLM call: request `{system, prompt, temperature,
   response_format}`, reply `{text}`, stateless, no payload logging. Run the six routing test
   questions (sales order details, purchase orders for a vendor, material search -> null, missing ID
   -> null, prompt injection -> null, user's own language) and check the JSON is stable.

Verify on first deploy (could not be checked locally):
7. The approuter issues a CSRF token for the GET with `X-CSRF-Token: Fetch` on `workflow/`.
8. The route `scope` array means "any one of" the listed scopes (user with only SalesRead must pass).
9. The relative `workflow/chat` URL resolves through the versioned HTML5 path
   (`/apspcoeccgatewaychat-1.0.0/workflow/chat`) and the second route pattern matches it.
10. Visual check of the layout in a real browser (only the rendered DOM was checked headlessly).

Then the agent service (rest of idea 4), in this repo under `agent/` with its own `manifest.yml`:
11. Router pattern, at most two workflow calls per question: call 1 turns the question into
    `{"tool","args","message"}` JSON using the six tools; the agent validates it against the tool
    schemas and refuses anything else; it calls `ecc-gateway-mcp` with the user's token; call 2 turns
    the result into a short answer. Prompts live in a config file (versioned in git).
12. Reuse the shared XSUAA instance so the approuter's user token can be forwarded to the MCP server
    without a token exchange. Bind the agent to the same XSUAA, destination and (if needed)
    connectivity instances.
13. Agent returns `{text, rows}`; point the approuter `/workflow/chat` route at the agent; UI renders
    `rows` as a table (UI currently ignores them).
14. Safeguards: never log or store the JWT, cap the rows sent to the workflow, treat ECC data as
    untrusted input to the LLM (prompt injection), keep every tool read-only.
15. Tests: mocked workflow and MCP server; end-to-end check with a hand-minted user token against
    the deployed MCP server before wiring the UI.

Open decisions: whether ECC business data may be sent to the workflow's LLM in full or must be
trimmed or masked (the workflow runs in a private network behind OAuth); structured rows vs text
only in the UI; whether `metadata.xml` (old ZMYOPTIMA_SQUOTE_SRV, untracked) should be deleted.

## History

- Earlier exploration targeted Purchase Requisition reads (getPRList/getPRTexts) from
  `ZMYOPTIMA_SQUOTE_SRV` and an initial sales scenario on `API_SALES_ORDER_SRV`. That
  direction was superseded: the shipped server uses the dedicated read-only ECC Gateway
  services `ZGW_ECCMCP_SALES_SRV` and `ZGW_ECCMCP_PURCHASING_SRV` with the tool set above.
- Repo: https://github.com/and23jul/ECCGatewayMCP
