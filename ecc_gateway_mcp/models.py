"""Input/output shapes of the `sap-sales` tool contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

SalesOrderId = Annotated[
    str, Field(pattern=r"^[0-9]{1,10}$", description="SAP sales order number (digits, up to 10).")
]
CustomerId = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9]{1,10}$", description="SAP customer number.")
]
OrderStatus = Literal["open", "completed", "rejected"]


class SalesOrderSummary(BaseModel):
    sales_order_id: str
    customer_id: str
    status: str
    net_amount: float
    currency: str


class SalesOrderPage(BaseModel):
    items: list[SalesOrderSummary]
    next_page_token: str | None


class DraftItem(BaseModel):
    material_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$", description="Material number.")
    quantity: float = Field(gt=0)
    unit: str = Field(pattern=r"^[A-Za-z0-9]{1,3}$", description="Unit of measure, e.g. PC.")


class DraftResult(BaseModel):
    draft_id: str
    status: str


class _Confirmation(BaseModel):
    """Elicitation form shown to the user before a draft is created."""

    confirm: bool = Field(default=False, description="Create this draft sales order?")
