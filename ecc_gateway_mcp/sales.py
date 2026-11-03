"""Sales order operations and the mapping between the tool contract and the backend OData model.

All backend field names live in this module so adapting to a different ECC Gateway service
only touches this file (plus the SALES_* settings).
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any

from .config import Settings
from .errors import GatewayError
from .gateway import GatewayClient
from .models import DraftItem, DraftResult, OrderStatus, SalesOrderPage, SalesOrderSummary

_SELECT = (
    "SalesOrder,SoldToParty,OverallSDProcessStatus,OverallSDDocumentRejectionSts,"
    "TotalNetAmount,TransactionCurrency"
)

# contract status -> OData $filter. 'C' = completely processed / completely rejected.
_STATUS_FILTER: dict[str, str] = {
    "open": "OverallSDProcessStatus ne 'C' and OverallSDDocumentRejectionSts ne 'C'",
    "completed": "OverallSDProcessStatus eq 'C' and OverallSDDocumentRejectionSts ne 'C'",
    "rejected": "OverallSDDocumentRejectionSts eq 'C'",
}


def pad_number(value: str) -> str:
    """SAP stores purely numeric keys with leading zeros (e.g. 0000012345)."""
    return value.zfill(10) if value.isdigit() else value


def _status(row: dict[str, Any]) -> str:
    if row.get("OverallSDDocumentRejectionSts") == "C":
        return "rejected"
    return "completed" if row.get("OverallSDProcessStatus") == "C" else "open"


def _summary(row: dict[str, Any]) -> SalesOrderSummary:
    return SalesOrderSummary(
        sales_order_id=row["SalesOrder"],
        customer_id=row.get("SoldToParty") or "",
        status=_status(row),
        net_amount=float(Decimal(row.get("TotalNetAmount") or "0")),  # OData V2 sends decimals as strings
        currency=row.get("TransactionCurrency") or "",
    )


def encode_page_token(skip: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"skip": skip}).encode()).decode()


def decode_page_token(token: str) -> int:
    try:
        skip = json.loads(base64.urlsafe_b64decode(token.encode()))["skip"]
        if isinstance(skip, int) and skip >= 0:
            return skip
    except (ValueError, KeyError, TypeError):
        pass
    raise GatewayError("INVALID_INPUT", "page_token is not valid.")


class SalesService:
    def __init__(self, settings: Settings, gateway: GatewayClient) -> None:
        self._s = settings
        self._gw = gateway

    async def get_order(self, jwt: str, sales_order_id: str) -> SalesOrderSummary:
        key = pad_number(sales_order_id)
        path = f"{self._s.sales_service_path}/{self._s.sales_entity_set}('{key}')"
        return _summary(await self._gw.get(jwt, path, {"$select": _SELECT}))

    async def list_orders(
        self, jwt: str, customer_id: str | None, status: OrderStatus | None, limit: int, page_token: str | None
    ) -> SalesOrderPage:
        skip = decode_page_token(page_token) if page_token else 0
        filters = []
        if customer_id:
            filters.append(f"SoldToParty eq '{pad_number(customer_id)}'")
        if status:
            filters.append(f"({_STATUS_FILTER[status]})")
        params = {
            "$select": _SELECT,
            "$orderby": "SalesOrder desc",
            "$top": str(limit + 1),  # one extra row tells us whether another page exists
            "$skip": str(skip),
        }
        if filters:
            params["$filter"] = " and ".join(filters)

        data = await self._gw.get(jwt, f"{self._s.sales_service_path}/{self._s.sales_entity_set}", params)
        rows = data.get("results", [])
        has_more = len(rows) > limit
        return SalesOrderPage(
            items=[_summary(r) for r in rows[:limit]],
            next_page_token=encode_page_token(skip + limit) if has_more else None,
        )

    async def create_draft(self, jwt: str, customer_id: str, items: list[DraftItem]) -> DraftResult:
        if not self._s.draft_entity_set:
            raise GatewayError(
                "BACKEND_NOT_CONFIGURED",
                "Draft creation is not configured (set SALES_DRAFT_ENTITY_SET).",
            )
        body = {
            **self._s.draft_defaults,
            "SoldToParty": pad_number(customer_id),
            "to_Item": [
                {
                    "Material": i.material_id,
                    "RequestedQuantity": str(i.quantity),
                    "RequestedQuantityUnit": i.unit,
                }
                for i in items
            ],
        }
        root = self._s.sales_service_path
        data = await self._gw.post(jwt, root, f"{root}/{self._s.draft_entity_set}", body)
        draft_id = data.get(self._s.draft_id_field)
        if not draft_id:
            raise GatewayError("BACKEND_ERROR", "Backend did not return a draft identifier.")
        return DraftResult(draft_id=str(draft_id), status="draft")
