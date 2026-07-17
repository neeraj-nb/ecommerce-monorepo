"""Order saga (choreography).

Every function here is the *single* place a given order state transition happens,
so the checkout API and the Kafka consumer share identical, race-safe logic:

* each transition locks the order row (``select_for_update``) inside a
  transaction, so the API and consumer can't interleave a bad write;
* each transition is **guarded by the current status**, so replays / out-of-order
  delivery are no-ops (belt-and-braces with the consumer's ``ProcessedEvent``
  dedupe);
* outbound events are emitted via ``transaction.on_commit`` so they only fire
  after the DB change durably commits.
"""

import logging
from decimal import Decimal

from django.db import transaction

from . import events
from .models import Cart, Order, OrderItem

logger = logging.getLogger(__name__)


# --- outbound event helpers -------------------------------------------------

def _emit_order_cancelled(order, reason):
    items = [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items.all()]
    data = {
        "order_id": order.id,
        "user_id": order.user_id,
        "items": items,
        "reason": reason,
    }
    transaction.on_commit(
        lambda: events.publish(events.TOPIC_ORDER_CANCELLED, order.id, data)
    )


def _emit_order_confirmed(order):
    data = {"order_id": order.id, "user_id": order.user_id}
    transaction.on_commit(
        lambda: events.publish(events.TOPIC_ORDER_CONFIRMED, order.id, data)
    )


def _lock_order(order_id):
    return Order.objects.select_for_update().filter(id=order_id).first()


# --- saga initiation: checkout ---------------------------------------------

@transaction.atomic
def checkout_cart(cart, shipping_name="", shipping_address=""):
    """Convert an active cart into a PENDING order and emit ``order.created``.

    Returns the created Order. Raises ValueError if the cart is not
    checkout-able (inactive or empty).
    """
    cart = Cart.objects.select_for_update().get(id=cart.id)
    if cart.status != Cart.Status.ACTIVE:
        raise ValueError("Cart is not active.")

    items = list(cart.items.all())
    if not items:
        raise ValueError("Cart is empty.")

    total = sum((i.subtotal for i in items), Decimal("0.00"))
    order = Order.objects.create(
        user_id=cart.user_id,
        status=Order.Status.PENDING,
        total_amount=total,
        shipping_name=shipping_name,
        shipping_address=shipping_address,
    )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order,
            product_id=i.product_id,
            product_name=i.product_name,
            unit_price=i.unit_price,
            quantity=i.quantity,
        )
        for i in items
    ])

    cart.status = Cart.Status.CHECKED_OUT
    cart.save(update_fields=["status", "updated_at"])

    data = {
        "order_id": order.id,
        "user_id": order.user_id,
        "items": [
            {"product_id": i.product_id, "quantity": i.quantity, "unit_price": str(i.unit_price)}
            for i in items
        ],
        "total_amount": str(total),
        "currency": order.currency,
    }
    transaction.on_commit(
        lambda: events.publish(events.TOPIC_ORDER_CREATED, order.id, data)
    )
    logger.info("checkout: created order %s for user %s", order.id, order.user_id)
    return order


# --- user-initiated cancel --------------------------------------------------

@transaction.atomic
def cancel_order(order_id, reason="Cancelled by user."):
    """Cancel an order that is still cancellable and emit the compensation event.

    Raises ValueError if the order is already terminal (confirmed/cancelled).
    """
    order = _lock_order(order_id)
    if order is None:
        raise ValueError("Order not found.")
    if not order.can_cancel:
        raise ValueError(f"Order in status '{order.status}' cannot be cancelled.")

    order.status = Order.Status.CANCELLED
    order.cancel_reason = reason
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    _emit_order_cancelled(order, reason)
    logger.info("cancel: order %s cancelled (%s)", order.id, reason)
    return order


# --- inbound event handlers (called by the consumer) ------------------------

@transaction.atomic
def apply_inventory_reserved(order_id):
    order = _lock_order(order_id)
    if order is None:
        logger.warning("inventory.reserved for unknown order %s", order_id)
        return
    if order.status != Order.Status.PENDING:
        logger.info(
            "ignoring inventory.reserved for order %s in status %s", order_id, order.status
        )
        return
    order.status = Order.Status.INVENTORY_RESERVED
    order.save(update_fields=["status", "updated_at"])
    logger.info("order %s -> INVENTORY_RESERVED", order_id)


@transaction.atomic
def apply_inventory_rejected(order_id, reason=""):
    order = _lock_order(order_id)
    if order is None:
        logger.warning("inventory.rejected for unknown order %s", order_id)
        return
    if order.is_terminal:
        logger.info("ignoring inventory.rejected for terminal order %s", order_id)
        return
    reason = reason or "Inventory could not be reserved."
    order.status = Order.Status.CANCELLED
    order.cancel_reason = reason
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    _emit_order_cancelled(order, reason)
    logger.info("order %s -> CANCELLED (inventory rejected)", order_id)


@transaction.atomic
def apply_payment_succeeded(order_id):
    order = _lock_order(order_id)
    if order is None:
        logger.warning("payment.succeeded for unknown order %s", order_id)
        return
    if order.status != Order.Status.INVENTORY_RESERVED:
        logger.info(
            "ignoring payment.succeeded for order %s in status %s", order_id, order.status
        )
        return
    order.status = Order.Status.CONFIRMED
    order.save(update_fields=["status", "updated_at"])
    _emit_order_confirmed(order)
    logger.info("order %s -> CONFIRMED", order_id)


@transaction.atomic
def apply_payment_failed(order_id, reason=""):
    order = _lock_order(order_id)
    if order is None:
        logger.warning("payment.failed for unknown order %s", order_id)
        return
    if order.is_terminal:
        logger.info("ignoring payment.failed for terminal order %s", order_id)
        return
    reason = reason or "Payment failed."
    order.status = Order.Status.CANCELLED
    order.cancel_reason = reason
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    # Compensation: releasing any reserved stock happens via order.cancelled.
    _emit_order_cancelled(order, reason)
    logger.info("order %s -> CANCELLED (payment failed)", order_id)
