"""Sales mapping, filtering and pagination (ZGW_ECCMCP_SALES_SRV)."""

from __future__ import annotations

import pytest

from ecc_gateway_mcp.sales import SalesService, pad_number
from tests.conftest import SALES_PATH, FakeGateway


def test_pad_number_only_pads_numeric():
    assert pad_number("45") == "0000000045"
    assert pad_number("0000000045") == "0000000045"
    assert pad_number("ABC") == "ABC"  # non-numeric keys are left untouched


async def test_get_order_maps_head_and_filters_items_by_key(settings):
    head_path = f"{SALES_PATH}/SOHeadSet('0000000045')"
    items_path = f"{SALES_PATH}/SOItemSet"
    gw = FakeGateway(
        single={head_path: {"SONumber": "0000000045", "SOCustomer": "0000001000"}},
        collection={
            items_path: [
                {"SONumber": "0000000045", "SOItemNo": "000010", "MaterialNo": "MAT-1"},
                {"SONumber": "0000000045", "SOItemNo": "000020", "MaterialNo": "MAT-2"},
                {"SONumber": "0000000099", "SOItemNo": "000010", "MaterialNo": "OTHER"},
            ]
        },
    )
    detail = await SalesService(settings, gw).get_order("jwt", "45")

    assert detail.sales_order_id == "0000000045"
    assert detail.customer_id == "0000001000"
    assert [(i.item_number, i.material_id) for i in detail.items] == [
        ("000010", "MAT-1"),
        ("000020", "MAT-2"),
    ]
    # the unrelated SONumber row is excluded
    assert all(i.sales_order_id == "0000000045" for i in detail.items)


async def test_list_orders_filters_on_customer_only(settings):
    path = f"{SALES_PATH}/SOHeadSet"
    gw = FakeGateway(collection={path: [{"SONumber": "0000000001", "SOCustomer": "0000001000"}]})
    await SalesService(settings, gw).list_orders("jwt", "1000", 10, None)

    _, params = gw.params_for[-1]
    assert params == {"$filter": "SOCustomer eq '0000001000'"}


async def test_list_orders_no_filter_sends_no_params(settings):
    path = f"{SALES_PATH}/SOHeadSet"
    gw = FakeGateway(collection={path: [{"SONumber": "0000000001", "SOCustomer": "0000001000"}]})
    await SalesService(settings, gw).list_orders("jwt", None, 10, None)

    _, params = gw.params_for[-1]
    assert params is None  # no $top/$skip/$orderby either (sets are pageable=false)


async def test_list_orders_paginates_in_server(settings):
    path = f"{SALES_PATH}/SOHeadSet"
    rows = [{"SONumber": f"000000{n:04d}", "SOCustomer": "0000001000"} for n in range(1, 26)]
    svc = SalesService(settings, FakeGateway(collection={path: rows}))

    p1 = await svc.list_orders("jwt", None, 10, None)
    assert len(p1.items) == 10 and p1.next_page_token is not None

    p2 = await svc.list_orders("jwt", None, 10, p1.next_page_token)
    assert len(p2.items) == 10 and p2.next_page_token is not None

    p3 = await svc.list_orders("jwt", None, 10, p2.next_page_token)
    assert len(p3.items) == 5 and p3.next_page_token is None

    # pages are disjoint and cover every row in order
    ids = [i.sales_order_id for i in (p1.items + p2.items + p3.items)]
    assert ids == [r["SONumber"] for r in rows]


async def test_list_items_returns_only_matching_order(settings):
    items_path = f"{SALES_PATH}/SOItemSet"
    gw = FakeGateway(
        collection={
            items_path: [
                {"SONumber": "0000000045", "SOItemNo": "000010", "MaterialNo": "MAT-1"},
                {"SONumber": "0000000099", "SOItemNo": "000010", "MaterialNo": "OTHER"},
            ]
        }
    )
    items = await SalesService(settings, gw).list_items("jwt", "45")
    assert len(items) == 1
    assert items[0].sales_order_id == "0000000045"
