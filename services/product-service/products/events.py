"""Kafka event layer for the product-service (inventory side of the saga).

Every message on the bus shares a common envelope so consumers can dedupe and
route generically::

    {
        "event_id":   "<uuid4>",
        "event_type": "inventory.reserved",
        "version":    1,
        "occurred_at":"2026-07-18T10:00:00+00:00",
        "data":       { ... }
    }

Messages are keyed by ``order_id`` so all events for one order land on the same
partition and are processed in order.

Topics this service CONSUMES (produced by order-service):
    order.created    -> reserve stock
    order.cancelled  -> release any stock reserved for the order (compensation)

Topics this service PRODUCES:
    inventory.reserved -> data: {order_id, user_id, total_amount, currency,
                                 items:[{product_id, quantity}]}
                          (payment-service consumes this to charge the order)
    inventory.rejected -> data: {order_id, user_id, reason}
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

# --- Topic names ------------------------------------------------------------
TOPIC_ORDER_CREATED = "order.created"
TOPIC_ORDER_CANCELLED = "order.cancelled"

TOPIC_INVENTORY_RESERVED = "inventory.reserved"
TOPIC_INVENTORY_REJECTED = "inventory.rejected"

# Topics the inventory consumer subscribes to.
CONSUMED_TOPICS = [
    TOPIC_ORDER_CREATED,
    TOPIC_ORDER_CANCELLED,
]

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


def enqueue(topic, key, data):
    """Durably record that ``topic`` needs to be published, keyed by ``key``.

    Call this from INSIDE the same transaction as the state change it
    announces (no ``on_commit`` needed -- it's a plain DB write). This is the
    transactional-outbox write side: it makes "the state changed" and "this
    needs to reach Kafka" atomic with each other, rather than depending on
    Kafka being reachable at commit time. A separate relay process
    (``run_outbox_relay``) delivers it independently; see events.send_envelope.
    """
    from .models import Outbox  # local import: models imports nothing from here

    envelope = build_envelope(topic, data)
    Outbox.objects.create(topic=topic, key=str(key), envelope=envelope)
    return envelope


def send_envelope(topic, key, envelope):
    """Actually publish a pre-built envelope to Kafka. Used only by the outbox
    relay -- the envelope (and its event_id) was already built once at
    enqueue() time, not regenerated here, so a retried delivery (e.g. after an
    ambiguous timeout) resends the SAME event_id rather than minting a new
    one, keeping consumer-side dedup-by-event_id correct.
    """
    producer = get_producer()
    producer.send(topic, key=key, value=envelope)
    producer.flush(timeout=10)
    logger.info("published %s event_id=%s key=%s", topic, envelope["event_id"], key)
