## Backlog: Purchasing (PR) capabilities for ecc-gateway-mcp

Status: BLOCKED - waiting for a cleaner OData service from the user.

### Goal
Expose Purchase Requisition reads as MCP tools: get_pr_list, get_pr_texts.
Replace the sales scenario (no sales OData service is available).

### Done so far
- Server `ecc-gateway-mcp` pushed to https://github.com/and23jul/ECCGatewayMCP (main, commit 43f1f58).
- FastMCP (mcp==1.30.0), XSUAA JWT validation, destination `Gateway-x96-SSO`
  (OnPremise + principal propagation), sales tools built on API_SALES_ORDER_SRV defaults.
- manifest.yml binds: XSUAA-application-ECCGatewayMCP, DEST-lite-Restricted, CONN-lite-ECCGatewayMCP.
- xs-security.json: roles ZROL-APP-ECCGatewayMCP-ViewSalesOrders / -CreateSalesOrders;
  role collections ZROC-APP-APP-ECCGatewayMCP-SalesSupport / ZROC-APP-ECCGatewayMCP-SalesExecutive.

### Findings from first metadata (ZMYOPTIMA_SQUOTE_SRV, local metadata.xml, uncommitted)
- getPRList / getPRTexts are NOT function imports (0 FunctionImports). They are entity types.
- getPRList: set getPRList, key IvType; read getPRList('<IvType>')?$expand=DATA -> getPRListData rows.
- getPRTexts: set getPRTextsSet, key IvPrNum; or getPR('<PR>')/TEXTS.
- All properties filterable=false and sortable=false; sets pageable=false.
  So no $filter/$orderby/$top/$skip: filter and paginate inside the MCP server.
- CreatedOn is Edm.DateTime (/Date(ms)/): parse it. DocData is binary: exclude.
- Unknown: valid IvType values; whether $expand=DATA is required; real service path.

### Open questions
1. IvType meaning/values, and tool input (enum, fixed config, or free 4 chars).
2. getPRTexts call path (getPRTextsSet('<PR>') vs getPR('<PR>')/TEXTS).
3. Remove the sales tools or keep them (leaning remove).
4. Delete the old metadata.xml?

### Needed from user
- New service $metadata XML in the project folder.
- Service path on the Gateway.
- Working sample URLs from /IWFND/GW_CLIENT.

### Draft tasks (once unblocked)
1. Save the contract as contract/sap-purchasing.yaml (read-only tools, scope PurchaseRequisitionRead).
2. Add purchasing.py backend: paths, field mapping, DateTime parsing, in-server filter and pagination.
3. Register tools in server.py; rename server to sap-purchasing; remove SALES_* settings if sales is dropped.
4. Add PurchaseRequisitionRead scope and a role in xs-security.json (keep ZROL-APP-ECCGatewayMCP-* naming).
5. Test with mocked backend responses (same approach as before), then push to GitHub.
