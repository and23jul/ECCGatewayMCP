"""Sales read operations: mapping between the tool contract and ZGW_ECCMCP_SALES_SRV.

Backend facts (metadata/Sales.edmx.xml, OData V2, read-only):
  SOHeadSet  key SONumber;            fields SONumber, SOCustomer  (SOCustomer filterable)
  SOItemSet  key SONumber+SOItemNo;   fields SONumber, SOItemNo, MaterialNo  (none filterable)
  No navigation between head and item; both sets are pageable=false.
All backend field names live in this module so adapting to a different service touches only here.
"""

from __future__ import annotations

from typing import Any

from .config import Settings
from .gateway import GatewayClient
from .models import (
    CustomerId,
    SalesOrder,
    SalesOrderDetail,
    SalesOrderItem,
    SalesOrderPage,
)
from .paging import decode_page_token, paginate


def pad_number(value: str) -> str:
    """SAP stores purely numeric keys with leading zeros (e.g. 0000012345)."""
    return value.zfill(10) if value.isdigit() else value


def _head(row: dict[str, Any]) -> SalesOrder:
    return SalesOrder(
        sales_order_id=row["SONumber"],
        customer_id=row.get("SOCustomer") or "",
    )


def _item(row: dict[str, Any]) -> SalesOrderItem:
    return SalesOrderItem(
        sales_order_id=row["SONumber"],
        item_number=row["SOItemNo"],
        material_id=row.get("MaterialNo") or "",
    )


class SalesService:
    def __init__(self, settings: Settings, gateway: GatewayClient) -> None:
        self._s = settings
        self._gw = gateway

    async def get_order(self, jwt: str, sales_order_id: str) -> SalesOrderDetail:
        key = pad_number(sales_order_id)
        head_path = f"{self._s.sales_service_path}/{self._s.sales_head_entity_set}('{key}')"
        head = await self._gw.get(jwt, head_path)
        items = await self._items_for(jwt, key)
        return SalesOrderDetail(
            sales_order_id=head["SONumber"],
            customer_id=head.get("SOCustomer") or "",
            items=items,
        )

    async def list_items(self, jwt: str, sales_order_id: str) -> list[SalesOrderItem]:
        return await self._items_for(jwt, pad_number(sales_order_id))

    async def list_orders(
        self, jwt: str, customer_id: str | None, limit: int, page_token: str | None
    ) -> SalesOrderPage:
        skip = decode_page_token(page_token) if page_token else 0
        params: dict[str, str] = {}
        if customer_id:
            # SOCustomer is the only server-side filterable field on SOHeadSet.
            params["$filter"] = f"SOCustomer eq '{pad_number(customer_id)}'"
        path = f"{self._s.sales_service_path}/{self._s.sales_head_entity_set}"
        rows = await self._gw.get_collection(jwt, path, params or None)
        rows = rows[: self._s.max_backend_rows]
        window, next_token = paginate(rows, skip, limit)
        return SalesOrderPage(items=[_head(r) for r in window], next_page_token=next_token)

    async def _items_for(self, jwt: str, padded_so: str) -> list[SalesOrderItem]:
        # SOItemSet has no filterable fields, so read the set and filter by key in-server.
        path = f"{self._s.sales_service_path}/{self._s.sales_item_entity_set}"
        rows = await self._gw.get_collection(jwt, path)
        rows = rows[: self._s.max_backend_rows]
        return [_item(r) for r in rows if r.get("SONumber") == padded_so]
