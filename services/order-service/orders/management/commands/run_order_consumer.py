"""Kafka consumer that drives the order saga from inbound events.

Run as a long-lived worker process (separate from the web server):

    python manage.py run_order_consumer

It subscribes to the inventory/payment topics, dedupes each message by
``event_id`` (via the ``ProcessedEvent`` table) so redelivery is safe, and
applies the matching saga transition. Offsets are committed only after a message
is handled, so a crash mid-processing re-delivers rather than loses the event.
"""

import json
import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from orders import consumer_metrics, events, saga
from orders.models import ProcessedEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume inventory/payment events and advance order saga state."

    def handle(self, *args, **options):
        from kafka import KafkaConsumer  # lazy import; broker not needed to load Django

        from django.conf import settings

        consumer = KafkaConsumer(
            *events.CONSUMED_TOPICS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="order-service",
            enable_auto_commit=False,          # commit only after successful handling
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )

        self._running = True

        def _stop(signum, frame):
            self.stdout.write("Shutting down consumer...")
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        self.stdout.write(
            self.style.SUCCESS(f"Order consumer listening on {events.CONSUMED_TOPICS}")
        )

        try:
            while self._running:
                # Poll so we can react to shutdown signals between batches.
                batch = consumer.poll(timeout_ms=1000)
                for _tp, messages in batch.items():
                    for message in messages:
                        self._process(message)
                    consumer.commit()
                # Same thread as poll() -- kafka-python's client isn't
                # thread-safe, so lag is computed here, not via an async gauge.
                consumer_metrics.maybe_record_lag(consumer)
        finally:
            consumer.close()

    def _process(self, message):
        envelope = message.value or {}
        event_id = envelope.get("event_id")
        event_type = envelope.get("event_type") or message.topic
        data = envelope.get("data") or {}
        order_id = data.get("order_id")

        if not event_id or order_id is None:
            logger.warning("skipping malformed message on %s: %r", message.topic, envelope)
            consumer_metrics.record_event(event_type, "malformed", 0.0)
            return

        start = time.monotonic()
        try:
            with transaction.atomic():
                # Insert-first dedupe: the unique event_id makes a replay raise
                # IntegrityError, and the handler shares this transaction so both
                # commit or both roll back.
                ProcessedEvent.objects.create(event_id=event_id, event_type=event_type)
                self._route(message.topic, order_id, data)
            consumer_metrics.record_event(event_type, "success", (time.monotonic() - start) * 1000)
        except IntegrityError:
            logger.info("duplicate event %s (%s) ignored", event_id, event_type)
            consumer_metrics.record_event(event_type, "duplicate", (time.monotonic() - start) * 1000)
        except Exception:  # noqa: BLE001 - log and move on; offset not committed on crash
            logger.exception("failed handling %s for order %s", event_type, order_id)
            consumer_metrics.record_event(event_type, "error", (time.monotonic() - start) * 1000)
            raise

    def _route(self, topic, order_id, data):
        if topic == events.TOPIC_INVENTORY_RESERVED:
            saga.apply_inventory_reserved(order_id)
        elif topic == events.TOPIC_INVENTORY_REJECTED:
            saga.apply_inventory_rejected(order_id, data.get("reason", ""))
        elif topic == events.TOPIC_PAYMENT_SUCCEEDED:
            saga.apply_payment_succeeded(order_id)
        elif topic == events.TOPIC_PAYMENT_FAILED:
            saga.apply_payment_failed(order_id, data.get("reason", ""))
        else:
            logger.warning("no handler for topic %s", topic)
