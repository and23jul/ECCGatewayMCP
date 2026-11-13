# Connecting an MCP client to ecc-gateway-mcp

This server is only the **server half** of the picture. Natural-language understanding
("which OData service / entity set do I call?") happens in the **LLM-backed MCP client**
you point at it. This guide wires that client to the deployed Cloud Foundry app.

## How the pieces fit

```
You (natural language)
      |
      v
MCP client with an LLM        <- decides WHICH tool to call (sales vs purchasing, head vs item)
  (Claude Desktop / Kiro /
   custom agent)
      |  streamable-HTTP + Bearer <XSUAA JWT>
      v
ecc-gateway-mcp (CF app)      <- maps each tool to a fixed OData service + entity set
      |  principal propagation (caller JWT) via destination Gateway-x96-SSO + Cloud Connector
      v
ECC Gateway OData V2 services
```

The client picks the tool; the server deterministically resolves the tool to the right
OData service path and entity set (see table below). You never name an entity set yourself.

## Tool -> OData mapping (what the server guarantees)

| Tool | Scope required | OData service | Entity set(s) |
|------|----------------|---------------|---------------|
| `get_sales_order` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOHeadSet` + `SOItemSet` |
| `list_sales_orders` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOHeadSet` |
| `get_sales_order_items` | `SalesRead` | `ZGW_ECCMCP_SALES_SRV` | `SOItemSet` |
| `get_purchase_order` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POHeadSet` + `POItemSet` |
| `list_purchase_orders` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POHeadSet` |
| `get_purchase_order_items` | `PurchasingRead` | `ZGW_ECCMCP_PURCHASING_SRV` | `POItemSet` |

## Prerequisites

1. The app is deployed and reachable. Find its URL:
   ```
   cf app ecc-gateway-mcp
   ```
   The MCP endpoint is: `https://<app-route>/mcp`

2. You can mint an XSUAA JWT for the bound `XSUAA-application-ECCGatewayMCP` instance.
   The token's `aud` must include `ecc-gateway-mcp`, and its `scope` must include
   `ecc-gateway-mcp.SalesRead` and/or `ecc-gateway-mcp.PurchasingRead` (granted via the
   role collections `ZROC-APP-ECCGatewayMCP-*`).

## Getting a token

### Option A - interactive user token (recommended for principal propagation)

The backend call uses **principal propagation**, so the token must represent a real user
who is mapped on the Cloud Connector / ECC side. Mint a user token through the XSUAA
`password` or `authorization_code` flow. Fastest for testing:

```bash
# 1. Read the bound XSUAA credentials
cf env ecc-gateway-mcp    # find VCAP_SERVICES.xsuaa[0].credentials: url, clientid, clientsecret

# 2. Exchange username/password for a user JWT (password grant)
curl -s -u "<clientid>:<clientsecret>" \
  "https://<xsuaa-url>/oauth/token" \
  -d "grant_type=password&username=<user>&password=<pass>&response_type=token" \
  | jq -r .access_token
```

A client-credentials token (`grant_type=client_credentials`) will pass XSUAA validation
and scope checks, but it has **no named user**, so principal propagation to ECC will not
identify a person. Use it only to confirm the MCP layer works, not for real reads.

### Option B - bind a service key for scripted access

```bash
cf create-service-key XSUAA-application-ECCGatewayMCP sk-ecc-gateway-mcp
cf service-key XSUAA-application-ECCGatewayMCP sk-ecc-gateway-mcp
# use the clientid/clientsecret/url from the key output in the curl call above
```

## Client configuration

The server speaks **streamable-HTTP** at `/mcp` and expects `Authorization: Bearer <JWT>`.

### Kiro / VS Code style (mcp.json)

```json
{
  "mcpServers": {
    "ecc-gateway": {
      "url": "https://<app-route>/mcp",
      "headers": {
        "Authorization": "Bearer ${ECC_GATEWAY_TOKEN}"
      }
    }
  }
}
```

Set `ECC_GATEWAY_TOKEN` in your environment to the JWT from the step above. (XSUAA
access tokens are short-lived, typically well under an hour, so you will refresh it.)

### Claude Desktop style

Claude Desktop launches MCP servers over stdio, so point it at a remote-HTTP bridge
such as `mcp-remote`:

```json
{
  "mcpServers": {
    "ecc-gateway": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://<app-route>/mcp",
        "--header", "Authorization: Bearer ${ECC_GATEWAY_TOKEN}"
      ],
      "env": { "ECC_GATEWAY_TOKEN": "<paste JWT>" }
    }
  }
}
```

## Trying it

Once connected, the client lists six tools. Ask in plain language and let the LLM route:

- "List sales orders for customer 1000."
  -> `list_sales_orders(customer_id="1000")` -> `ZGW_ECCMCP_SALES_SRV/SOHeadSet`
     with `$filter=SOCustomer eq '0000001000'`
- "What materials are on sales order 12345?"
  -> `get_sales_order_items(sales_order_id="12345")` -> `ZGW_ECCMCP_SALES_SRV/SOItemSet`
     (key padded to `0000012345`)
- "Show purchase order 4500000123 with its vendor."
  -> `get_purchase_order(purchase_order_id="4500000123")` -> `ZGW_ECCMCP_PURCHASING_SRV/POHeadSet`+`POItemSet`

## Limits to know (so you phrase requests the server can serve)

- Sales list filters only by **customer** (`SOCustomer`); purchasing list filters only by
  **vendor**. Item sets have no filterable fields - the server reads the set and filters by
  key in memory, capped at `MAX_BACKEND_ROWS` (default 5000).
- Everything is **read-only**. No create/update/delete tools exist.
- Numeric keys are auto zero-padded to 10 chars, so "order 12345" works as typed.
- A request that needs an entity set or filter the backend does not expose (e.g. "sales
  orders containing material X") has no tool to route to - the model cannot and should not
  invent one.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| 401 at the MCP endpoint | Missing/expired/wrong-audience JWT. Re-mint; confirm `aud` includes `ecc-gateway-mcp`. |
| Tool returns FORBIDDEN | Token lacks `ecc-gateway-mcp.SalesRead`/`.PurchasingRead`. Assign the `ZROC-APP-ECCGatewayMCP-*` role collection to the user. |
| Tool returns NOT_FOUND | Document does not exist or is not visible to the propagated user in ECC. |
| BACKEND_ERROR | Destination `Gateway-x96-SSO`, Cloud Connector, or the OData service path is misconfigured. Check `cf logs ecc-gateway-mcp`. |
