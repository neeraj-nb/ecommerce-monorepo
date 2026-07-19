"""Kafka event layer for the payment-service (choreography saga).

Every message on the bus shares a common envelope so consumers can dedupe and
route generically::

    {
        "event_id":   "<uuid4>",     # unique per emission; used for idempotency
        "event_type": "payment.succeeded",
        "version":    1,
        "occurred_at":"2026-07-18T10:00:00+00:00",
        "data":       { ... }
    }

Messages are keyed by ``order_id`` so all events for one order land on the same
partition and are processed in order.

This service CONSUMES a trigger (``settings.PAYMENT_TRIGGER_TOPIC``, default
``inventory.reserved``) that signals an order is ready to be charged, and
PRODUCES:

    payment.succeeded -> data: {order_id, user_id, amount, currency,
                                payment_number, transaction_id}
    payment.failed    -> data: {order_id, user_id, payment_number, reason}
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

# --- Topic names ------------------------------------------------------------
TOPIC_PAYMENT_SUCCEEDED = "payment.succeeded"
TOPIC_PAYMENT_FAILED = "payment.failed"

# What tells us to charge an order. Overridable so payment can be demoed off
# ``order.created`` before product-service's inventory consumer exists.
TRIGGER_TOPIC = settings.PAYMENT_TRIGGER_TOPIC

CONSUMED_TOPICS = [TRIGGER_TOPIC]

SCHEMA_VERSION = 1

_producer = None


def get_producer():
    """Lazily build a singleton KafkaProducer.

    Kept lazy so importing this module (e.g. during migrations or in the web
    process before it ever publishes) does not require a live broker.
    """
    global _producer
    if _producer is None:
        from kafka import KafkaProducer  # imported lazily to keep import cheap

        _producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: str(k).encode("utf-8") if k is not None else None,
            acks="all",              # wait for full replication ack
            retries=5,
            linger_ms=10,
        )
    return _producer


def build_envelope(event_type, data):
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "version": SCHEMA_VERSION,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def publish(topic, key, data):
    """Publish one enveloped event to ``topic``, keyed by ``key`` (order id).

    Call this from within ``transaction.on_commit(...)`` so an event is only
    emitted after the owning DB transaction has durably committed.
    """
    envelope = build_envelope(topic, data)
    producer = get_producer()
    producer.send(topic, key=key, value=envelope)
    producer.flush(timeout=10)
    logger.info("published %s event_id=%s key=%s", topic, envelope["event_id"], key)
    return envelope
