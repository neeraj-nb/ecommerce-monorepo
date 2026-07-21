"""Outbox relay: delivers durably-recorded events to Kafka.

Run as a long-lived worker process (separate from the web server and the
inventory consumer):

    python manage.py run_outbox_relay

Polls for Outbox rows with no published_at, sends each via
events.send_envelope(), and marks it published on success. If Kafka is
unreachable, a row is simply left unpublished and retried on the next poll --
nothing is lost, since the event was already durably recorded in the same
transaction as the state change it announces (see events.enqueue).

On a failed send, this stops the current batch rather than skipping ahead to
later rows -- otherwise a later row for an unrelated key could be delivered
before an earlier, still-stuck one, reordering delivery relative to how the
events were actually created.
"""
import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from products import events
from products.models import Outbox

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 2
BATCH_SIZE = 100


class Command(BaseCommand):
    help = "Deliver outbox events to Kafka (transactional outbox relay)."

    def handle(self, *args, **options):
        self._running = True

        def _stop(signum, frame):
            self.stdout.write("Shutting down outbox relay...")
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        self.stdout.write(self.style.SUCCESS("Outbox relay started"))

        while self._running:
            sent = self._relay_batch()
            if sent == 0:
                time.sleep(POLL_INTERVAL_S)

    def _relay_batch(self):
        rows = list(
            Outbox.objects.filter(published_at__isnull=True).order_by("created_at")[:BATCH_SIZE]
        )
        sent = 0
        for row in rows:
            try:
                events.send_envelope(row.topic, row.key, row.envelope)
            except Exception:  # noqa: BLE001 -- leave unpublished; retried next poll
                logger.exception(
                    "failed relaying outbox row %s (topic=%s); stopping this batch "
                    "so a later, unrelated row can't be delivered out of order",
                    row.id, row.topic,
                )
                break
            row.published_at = timezone.now()
            row.save(update_fields=["published_at"])
            sent += 1
        return sent
