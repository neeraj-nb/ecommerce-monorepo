"""Kafka consumer that charges orders in response to the trigger event.

Run as a long-lived worker process (separate from the web server):

    python manage.py run_payment_consumer

It subscribes to the trigger topic (``settings.PAYMENT_TRIGGER_TOPIC``, default
``inventory.reserved``), dedupes each message by ``event_id`` (via the
``ProcessedEvent`` table) so redelivery is safe, charges through the configured
gateway, and emits ``payment.succeeded`` / ``payment.failed``. Offsets are
committed only after a message is handled, so a crash mid-processing re-delivers
rather than loses the event.
"""

import json
import logging
import signal

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from payments import events, service
from payments.models import ProcessedEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume the order-ready trigger and process payments."

    def handle(self, *args, **options):
        from kafka import KafkaConsumer  # lazy import; broker not needed to load Django

        from django.conf import settings

        consumer = KafkaConsumer(
            *events.CONSUMED_TOPICS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="payment-service",
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
            self.style.SUCCESS(f"Payment consumer listening on {events.CONSUMED_TOPICS}")
        )

        try:
            while self._running:
                # Poll so we can react to shutdown signals between batches.
                batch = consumer.poll(timeout_ms=1000)
                for _tp, messages in batch.items():
                    for message in messages:
                        self._process(message)
                    consumer.commit()
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
            return

        try:
            with transaction.atomic():
                # Insert-first dedupe: the unique event_id makes a replay raise
                # IntegrityError, and the handler shares this transaction so both
                # commit or both roll back.
                ProcessedEvent.objects.create(event_id=event_id, event_type=event_type)
                service.process_payment(
                    order_id=order_id,
                    user_id=data.get("user_id"),
                    amount=data.get("total_amount") or data.get("amount"),
                    currency=data.get("currency", "USD"),
                    source_event_id=event_id,
                )
        except IntegrityError:
            logger.info("duplicate event %s (%s) ignored", event_id, event_type)
        except Exception:  # noqa: BLE001 - log; offset not committed so it redelivers
            logger.exception("failed handling %s for order %s", event_type, order_id)
            raise
