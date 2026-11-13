"""Purchasing mapping, filtering and nav-path item reads (ZGW_ECCMCP_PURCHASING_SRV)."""

from __future__ import annotations

from ecc_gateway_mcp.purchasing import PurchasingService
from tests.conftest import PURCHASING_PATH, FakeGateway


async def test_get_order_maps_head_and_reads_items_via_nav(settings):
    key = "0000004500"
    head_path = f"{PURCHASING_PATH}/POHeadSet('{key}')"
    nav_path = f"{PURCHASING_PATH}/POHeadSet('{key}')/POItemSet"
    gw = FakeGateway(
        single={head_path: {"PONumber": key, "POVendor": "0000002000"}},
        collection={
            nav_path: [
                {"PONumber": key, "POItemNo": "00010", "MaterialNo": "PMAT-1"},
                {"PONumber": key, "POItemNo": "00020", "MaterialNo": "PMAT-2"},
            ]
        },
    )
    detail = await PurchasingService(settings, gw).get_order("jwt", "4500")

    assert detail.purchase_order_id == key
    assert detail.vendor_id == "0000002000"
    assert [(i.item_number, i.material_id) for i in detail.items] == [
        ("00010", "PMAT-1"),
        ("00020", "PMAT-2"),
    ]
    # items were read through the navigation path, not by scanning the whole POItemSet
    assert nav_path in gw.calls


async def test_list_orders_filters_on_vendor_only(settings):
    path = f"{PURCHASING_PATH}/POHeadSet"
    gw = FakeGateway(collection={path: [{"PONumber": "0000004500", "POVendor": "0000002000"}]})
    await PurchasingService(settings, gw).list_orders("jwt", "2000", 10, None)

    _, params = gw.params_for[-1]
    assert params == {"$filter": "POVendor eq '0000002000'"}


async def test_list_orders_no_filter_sends_no_params(settings):
    path = f"{PURCHASING_PATH}/POHeadSet"
    gw = FakeGateway(collection={path: [{"PONumber": "0000004500", "POVendor": "0000002000"}]})
    await PurchasingService(settings, gw).list_orders("jwt", None, 10, None)

    _, params = gw.params_for[-1]
    assert params is None


async def test_list_items_reads_nav_path(settings):
    key = "0000004500"
    nav_path = f"{PURCHASING_PATH}/POHeadSet('{key}')/POItemSet"
    gw = FakeGateway(
        collection={nav_path: [{"PONumber": key, "POItemNo": "00010", "MaterialNo": "PMAT-1"}]}
    )
    items = await PurchasingService(settings, gw).list_items("jwt", "4500")
    assert len(items) == 1
    assert items[0].purchase_order_id == key
    assert gw.calls == [nav_path]
