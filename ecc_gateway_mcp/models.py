"""Input/output shapes of the read-only `ecc-gateway` tool contract.

Field names mirror the two ECC Gateway OData V2 services (see metadata/*.edmx.xml):
  ZGW_ECCMCP_SALES_SRV      -> SOHead(SONumber, SOCustomer), SOItem(SONumber, SOItemNo, MaterialNo)
  ZGW_ECCMCP_PURCHASING_SRV -> POHead(PONumber, POVendor),   POItem(PONumber, POItemNo, MaterialNo)
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

# SAP document / master-data keys are numeric strings up to the metadata MaxLength.
SalesOrderId = Annotated[
    str, Field(pattern=r"^[0-9]{1,10}$", description="SAP sales document number (digits, up to 10).")
]
CustomerId = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9]{1,10}$", description="SAP customer number.")
]
PurchaseOrderId = Annotated[
    str, Field(pattern=r"^[0-9]{1,10}$", description="SAP purchasing document number (digits, up to 10).")
]
VendorId = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9]{1,10}$", description="SAP vendor number.")
]


# --- Sales (ZGW_ECCMCP_SALES_SRV) ---------------------------------------------------------------

class SalesOrderItem(BaseModel):
    sales_order_id: str  # SONumber
    item_number: str     # SOItemNo
    material_id: str      # MaterialNo


class SalesOrder(BaseModel):
    sales_order_id: str  # SONumber
    customer_id: str     # SOCustomer


class SalesOrderDetail(BaseModel):
    sales_order_id: str
    customer_id: str
    items: list[SalesOrderItem]


class SalesOrderPage(BaseModel):
    items: list[SalesOrder]
    next_page_token: str | None


# --- Purchasing (ZGW_ECCMCP_PURCHASING_SRV) -----------------------------------------------------

class PurchaseOrderItem(BaseModel):
    purchase_order_id: str  # PONumber
    item_number: str        # POItemNo
    material_id: str        # MaterialNo


class PurchaseOrder(BaseModel):
    purchase_order_id: str  # PONumber
    vendor_id: str          # POVendor


class PurchaseOrderDetail(BaseModel):
    purchase_order_id: str
    vendor_id: str
    items: list[PurchaseOrderItem]


class PurchaseOrderPage(BaseModel):
    items: list[PurchaseOrder]
    next_page_token: str | None
