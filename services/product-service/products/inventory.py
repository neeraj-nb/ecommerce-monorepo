"""Inventory saga handlers (product-service side).

These are the single place stock is reserved or released in response to order
events, mirroring the order-service's ``saga.py``:

* each handler runs in a transaction and locks the affected product rows
  (``select_for_update``) so concurrent orders can't oversell;
* reservation is guarded by ``order_id`` (unique), and release by reservation
  status, so replays / out-of-order delivery are no-ops (belt-and-braces with
  the consumer's ``ProcessedEvent`` dedupe);
* outbound events are recorded via ``events.enqueue`` (a transactional outbox
  write) in the SAME transaction as the state change, so "the state changed"
  and "this needs to reach Kafka" are atomic with each other -- a separate
  relay process delivers them, so a Kafka outage can't turn a successful
  write into a client-facing error or a silently-dropped event.
"""

import logging

from django.db import transaction
from django.db.models import F

from . import events
from .models import InventoryReservation, Product, ReservationItem

logger = logging.getLogger(__name__)


def _emit_rejected(order_id, user_id, reason):
    data = {"order_id": order_id, "user_id": user_id, "reason": reason}
    events.enqueue(events.TOPIC_INVENTORY_REJECTED, order_id, data)
    logger.info("order %s -> inventory REJECTED: %s", order_id, reason)


@transaction.atomic
def reserve_for_order(order_id, user_id, items, total_amount=None, currency="USD"):
    """Reserve stock for an order and emit inventory.reserved / inventory.rejected.

    ``items`` is the order.created payload list: ``[{product_id, quantity, ...}]``.
    """
    if InventoryReservation.objects.filter(order_id=order_id).exists():
        logger.info("order %s already has a reservation; skipping", order_id)
        return

    # Collapse to {product_id: total_quantity}, ignoring malformed lines.
    wanted = {}
    for item in items or []:
        product_id = item.get("product_id")
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if product_id is None or quantity <= 0:
            continue
        wanted[product_id] = wanted.get(product_id, 0) + quantity

    if not wanted:
        _emit_rejected(order_id, user_id, "Order has no valid items.")
        return

    # Lock the product rows for the duration of the check + decrement.
    products = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=list(wanted))
    }

    problems = []
    for product_id, quantity in wanted.items():
        product = products.get(product_id)
        if product is None or not product.is_active:
            problems.append(f"product {product_id} unavailable")
        elif product.stock < quantity:
            problems.append(
                f"product {product_id} out of stock (need {quantity}, have {product.stock})"
            )
    if problems:
        _emit_rejected(order_id, user_id, "; ".join(problems))
        return

    reservation = InventoryReservation.objects.create(order_id=order_id)
    for product_id, quantity in wanted.items():
        Product.objects.filter(id=product_id).update(stock=F("stock") - quantity)
        ReservationItem.objects.create(
            reservation=reservation, product_id=product_id, quantity=quantity
        )

    data = {
        "order_id": order_id,
        "user_id": user_id,
        "total_amount": total_amount,
        "currency": currency,
        "items": [{"product_id": pid, "quantity": qty} for pid, qty in wanted.items()],
    }
    events.enqueue(events.TOPIC_INVENTORY_RESERVED, order_id, data)
    logger.info("order %s -> inventory RESERVED (%d lines)", order_id, len(wanted))


@transaction.atomic
def release_for_order(order_id):
    """Return any stock reserved for an order back to inventory (compensation).

    A no-op if there is no reservation, or it was already released.
    """
    reservation = (
        InventoryReservation.objects.select_for_update()
        .filter(order_id=order_id)
        .first()
    )
    if reservation is None:
        logger.info("no reservation for order %s to release", order_id)
        return
    if reservation.status != InventoryReservation.Status.RESERVED:
        logger.info("reservation for order %s already %s", order_id, reservation.status)
        return

    for item in reservation.items.all():
        Product.objects.filter(id=item.product_id).update(stock=F("stock") + item.quantity)

    reservation.status = InventoryReservation.Status.RELEASED
    reservation.save(update_fields=["status", "updated_at"])
    logger.info("order %s -> inventory RELEASED", order_id)
