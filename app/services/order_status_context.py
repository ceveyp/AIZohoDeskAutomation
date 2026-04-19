from __future__ import annotations

import logging
from typing import Any

from app.apparel_magic.client_async import AsyncApparelMagicClient
from app.apparel_magic.models import Customer, Order, OrderItem
from app.shopify.admin_client_async import AsyncShopifyAdminClient

logger = logging.getLogger(__name__)

MAX_AM_ORDERS = 50
MAX_SHOPIFY_ORDERS = 50
MAX_LINE_ITEMS = 25


def _sort_am_orders_newest_first(orders: list[Order]) -> list[Order]:
    return sorted(orders, key=lambda o: o.date or "", reverse=True)


def summarize_shopify_customer(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c.get("id"),
        "email": c.get("email"),
        "first_name": c.get("first_name"),
        "last_name": c.get("last_name"),
        "orders_count": c.get("orders_count"),
        "last_order_id": c.get("last_order_id"),
        "last_order_name": c.get("last_order_name"),
        "currency": c.get("currency"),
        "state": c.get("state"),
    }


def summarize_shopify_order(o: dict[str, Any]) -> dict[str, Any]:
    raw_items = o.get("line_items") or []
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for li in raw_items[:MAX_LINE_ITEMS]:
            if not isinstance(li, dict):
                continue
            items.append(
                {
                    "title": li.get("title"),
                    "quantity": li.get("quantity"),
                    "sku": li.get("sku"),
                    "fulfillment_status": li.get("fulfillment_status"),
                }
            )
    return {
        "id": o.get("id"),
        "name": o.get("name"),
        "order_number": o.get("order_number"),
        "created_at": o.get("created_at"),
        "processed_at": o.get("processed_at"),
        "cancelled_at": o.get("cancelled_at"),
        "cancel_reason": o.get("cancel_reason"),
        "financial_status": o.get("financial_status"),
        "fulfillment_status": o.get("fulfillment_status"),
        "current_total_price": o.get("current_total_price"),
        "currency": o.get("currency"),
        "line_items": items,
    }


def _summarize_am_line_item(li: OrderItem) -> dict[str, Any]:
    return {
        "description": li.description,
        "size": li.size,
        "color": li.attr_2,
        "qty": li.qty,
        "qty_open": li.qty_open,
        "qty_shipped": li.qty_shipped,
        "unit_price": li.unit_price,
        "amount": li.amount,
    }


def summarize_am_order(order: Order) -> dict[str, Any]:
    items = [_summarize_am_line_item(li) for li in (order.order_items or [])[:MAX_LINE_ITEMS]]
    return {
        "order_id": order.order_id,
        "customer_po": order.customer_po,
        "customer_name": order.customer_name,
        "dates": {
            "ordered": order.date,
            "due": order.date_due,
            "start": order.date_start,
            "last_modified": order.last_modified_time,
        },
        "status": {
            "fulfillment": order.fulfillment_status,
            "wms": order.wms_status,
            "credit": order.credit_status,
            "is_open": order.is_open,
        },
        "quantities": {"qty": order.qty, "qty_open": order.qty_open, "qty_shipped": order.qty_shipped},
        "amounts": {
            "amount": order.amount,
            "balance": order.balance,
            "currency": order.currency_name,
        },
        "ship_to": {
            "address_1": order.address_1,
            "city": order.city,
            "state": order.state,
            "postal_code": order.postal_code,
            "country": order.country,
        },
        "line_items": items,
    }


def summarize_am_customer_row(c: Customer) -> dict[str, Any]:
    return {
        "customer_id": c.customer_id,
        "customer_name": c.customer_name,
        "email": c.email,
        "account_number": c.account_number,
    }


async def build_order_status_context(
    *,
    am: AsyncApparelMagicClient,
    shopify: AsyncShopifyAdminClient | None,
    requester_email: str,
    intent_email: str | None,
    customer: Customer | None,
    intent_order_id: str | None,
) -> dict[str, Any] | None:
    """
    Build summarized JSON for the order-status agent.

    Returns None when the automation should noop (no Shopify customer after AM miss,
    or Shopify not configured when AM miss).
    """
    # --- AM B2B path ---
    if customer and customer.customer_id:
        cid = str(customer.customer_id)
        payload: dict[str, Any] = {
            "source": "apparel_magic",
            "matched_customer": summarize_am_customer_row(customer),
        }
        oid = (intent_order_id or "").strip()
        if oid:
            order = await am.get_order_by_id(oid)
            if order is None:
                payload["orders"] = []
                payload["notes"] = f"No AM order found for order_id={oid!r} from ticket."
            else:
                mismatch = (
                    order.customer_id
                    and str(order.customer_id).strip() != str(cid).strip()
                )
                payload["orders"] = [summarize_am_order(order)]
                if mismatch:
                    payload["customer_mismatch"] = {
                        "ticket_customer_id": cid,
                        "order_customer_id": str(order.customer_id),
                    }
        else:
            all_o = await am.get_orders_by_customer_id(cid)
            sorted_o = _sort_am_orders_newest_first(all_o)[:MAX_AM_ORDERS]
            payload["orders"] = [summarize_am_order(o) for o in sorted_o]
            if len(all_o) > MAX_AM_ORDERS:
                payload["notes"] = f"Showing newest {MAX_AM_ORDERS} of {len(all_o)} AM orders."
        return payload

    # --- Shopify retail path (AM customer not found) ---
    if shopify is None or not shopify.configured():
        logger.info("order_status: no AM customer and Shopify not configured; noop")
        return None

    emails = [requester_email.strip()]
    if intent_email and intent_email.strip().lower() != requester_email.strip().lower():
        emails.append(intent_email.strip())

    sc: list[dict[str, Any]] = []
    for em in emails:
        found = await shopify.search_customers_by_email(em)
        if found:
            sc = found
            break

    if not sc:
        logger.info("order_status: no AM customer and no Shopify customer for emails=%s; noop", emails)
        return None

    shopify_customer = sc[0]
    cust_id = shopify_customer.get("id")
    if cust_id is None:
        return None

    raw_orders = await shopify.list_orders_for_customer(cust_id, limit=MAX_SHOPIFY_ORDERS)
    erp_linkage: list[dict[str, Any]] = []
    for o in raw_orders:
        name = str(o.get("name") or "").strip()
        if not name:
            continue
        am_rows = await am.get_orders_by_customer_po(name)
        erp_linkage.append(
            {
                "shopify_order": summarize_shopify_order(o),
                "erp_order": summarize_am_order(am_rows[0]) if am_rows else None,
                "erp_rows_matched": len(am_rows),
            }
        )

    return {
        "source": "shopify_retail",
        "matched_customer": summarize_shopify_customer(shopify_customer),
        "shopify_orders": [summarize_shopify_order(o) for o in raw_orders],
        "erp_by_shopify_order": erp_linkage,
    }
