"""Payment processing -- the single place a charge is attempted and recorded.

Both the (event-driven) consumer and any future manual/API trigger funnel
through ``process_payment`` so the ledger write, the gateway call, and the
outbound result event stay consistent and idempotent.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from . import events
from .gateways import ChargeRequest, get_gateway
from .models import Payment

logger = logging.getLogger(__name__)


# --- outbound event helpers -------------------------------------------------

def _emit_payment_succeeded(payment):
    data = {
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "payment_number": payment.payment_number,
        "transaction_id": payment.gateway_reference,
    }
    events.enqueue(events.TOPIC_PAYMENT_SUCCEEDED, payment.order_id, data)


def _emit_payment_failed(payment):
    data = {
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "payment_number": payment.payment_number,
        "reason": payment.failure_reason or "Payment failed.",
    }
    events.enqueue(events.TOPIC_PAYMENT_FAILED, payment.order_id, data)


def _to_amount(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("could not parse amount %r; defaulting to 0.00", value)
        return Decimal("0.00")


@transaction.atomic
def process_payment(order_id, user_id, amount, currency="USD", source_event_id=None):
    """Charge an order through the configured gateway and record the outcome.

    Idempotent at the business level: if a SUCCEEDED payment already exists for
    the order, it is returned unchanged (no re-charge). The consumer additionally
    dedupes redelivery by ``event_id`` via ``ProcessedEvent``.

    Returns the Payment row. Records ``payment.succeeded`` / ``payment.failed``
    to the transactional outbox (same transaction) for a separate relay
    process to deliver -- see events.enqueue.
    """
    existing = Payment.objects.filter(
        order_id=order_id, status=Payment.Status.SUCCEEDED
    ).first()
    if existing is not None:
        logger.info("order %s already paid (%s); skipping", order_id, existing.payment_number)
        return existing

    amount = _to_amount(amount)
    payment = Payment.objects.create(
        order_id=order_id,
        user_id=user_id,
        amount=amount,
        currency=currency or "USD",
        status=Payment.Status.PENDING,
        source_event_id=source_event_id,
    )

    # NOTE: for a real gateway the network charge should happen outside the DB
    # transaction (charge with an idempotency key, then persist the result). The
    # dummy gateway is in-process, so a single transaction is fine here.
    gateway = get_gateway()
    result = gateway.charge(
        ChargeRequest(
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            currency=payment.currency,
            idempotency_key=str(source_event_id or payment.payment_number),
            metadata={"payment_number": payment.payment_number},
        )
    )

    payment.gateway = gateway.name
    payment.gateway_reference = result.reference
    payment.processed_at = timezone.now()

    if result.success:
        payment.status = Payment.Status.SUCCEEDED
        payment.save(update_fields=[
            "gateway", "gateway_reference", "status", "processed_at", "updated_at",
        ])
        _emit_payment_succeeded(payment)
        logger.info("order %s -> payment SUCCEEDED (%s)", order_id, payment.payment_number)
    else:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = result.message or "Payment failed."
        payment.save(update_fields=[
            "gateway", "gateway_reference", "status", "failure_reason",
            "processed_at", "updated_at",
        ])
        _emit_payment_failed(payment)
        logger.info("order %s -> payment FAILED (%s)", order_id, payment.payment_number)

    return payment
