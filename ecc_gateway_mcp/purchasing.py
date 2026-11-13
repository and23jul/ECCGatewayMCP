"""Purchasing read operations: mapping between the tool contract and ZGW_ECCMCP_PURCHASING_SRV.

Backend facts (metadata/Purchase.edmx.xml, OData V2, read-only):
  POHeadSet  key PONumber;            fields PONumber, POVendor  (POVendor filterable)
             nav POItemSet via association EKKO_EKPO (PONumber -> PONumber)
  POItemSet  key PONumber+POItemNo;   fields PONumber, POItemNo, MaterialNo  (MaterialNo not filterable)
  Both sets are pageable=false.
All backend field names live in this module so adapting to a different service touches only here.
"""

from __future__ import annotations

from typing import Any

from .config import Settings
from .gateway import GatewayClient
from .models import (
    PurchaseOrder,
    PurchaseOrderDetail,
    PurchaseOrderItem,
    PurchaseOrderPage,
    VendorId,
)
from .paging import decode_page_token, paginate


def pad_number(value: str) -> str:
    """SAP stores purely numeric keys with leading zeros (e.g. 0000012345)."""
    return value.zfill(10) if value.isdigit() else value


def _head(row: dict[str, Any]) -> PurchaseOrder:
    return PurchaseOrder(
        purchase_order_id=row["PONumber"],
        vendor_id=row.get("POVendor") or "",
    )


def _item(row: dict[str, Any]) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        purchase_order_id=row["PONumber"],
        item_number=row["POItemNo"],
        material_id=row.get("MaterialNo") or "",
    )


class PurchasingService:
    def __init__(self, settings: Settings, gateway: GatewayClient) -> None:
        self._s = settings
        self._gw = gateway

    async def get_order(self, jwt: str, purchase_order_id: str) -> PurchaseOrderDetail:
        key = pad_number(purchase_order_id)
        head_path = f"{self._s.purchasing_service_path}/{self._s.purchasing_head_entity_set}('{key}')"
        head = await self._gw.get(jwt, head_path)
        items = await self._items_for(jwt, key)
        return PurchaseOrderDetail(
            purchase_order_id=head["PONumber"],
            vendor_id=head.get("POVendor") or "",
            items=items,
        )

    async def list_items(self, jwt: str, purchase_order_id: str) -> list[PurchaseOrderItem]:
        return await self._items_for(jwt, pad_number(purchase_order_id))

    async def list_orders(
        self, jwt: str, vendor_id: str | None, limit: int, page_token: str | None
    ) -> PurchaseOrderPage:
        skip = decode_page_token(page_token) if page_token else 0
        params: dict[str, str] = {}
        if vendor_id:
            # POVendor is the only server-side filterable field on POHeadSet.
            params["$filter"] = f"POVendor eq '{pad_number(vendor_id)}'"
        path = f"{self._s.purchasing_service_path}/{self._s.purchasing_head_entity_set}"
        rows = await self._gw.get_collection(jwt, path, params or None)
        rows = rows[: self._s.max_backend_rows]
        window, next_token = paginate(rows, skip, limit)
        return PurchaseOrderPage(items=[_head(r) for r in window], next_page_token=next_token)

    async def _items_for(self, jwt: str, padded_po: str) -> list[PurchaseOrderItem]:
        # POHead has a navigation to POItemSet (EKKO_EKPO); read items through the nav path.
        nav = (
            f"{self._s.purchasing_service_path}/{self._s.purchasing_head_entity_set}"
            f"('{padded_po}')/{self._s.purchasing_item_entity_set}"
        )
        rows = await self._gw.get_collection(jwt, nav)
        rows = rows[: self._s.max_backend_rows]
        return [_item(r) for r in rows]
