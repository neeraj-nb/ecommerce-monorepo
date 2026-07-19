import uuid

from django.db import models


def generate_payment_number():
    """Human-friendly, unique payment reference, e.g. 'PAY-3F9A2B7C4D1E'."""
    return f"PAY-{uuid.uuid4().hex[:12].upper()}"


class Payment(models.Model):
    """A payment ledger entry: one attempt to charge an order.

    The payment-service owns no user/order rows -- ``user_id`` and ``order_id``
    are references into the user- and order-services. A row is created when a
    charge is attempted and updated with the gateway's outcome, giving a durable
    audit trail of every payment and its status.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"        # created, gateway not yet answered
        SUCCEEDED = "succeeded", "Succeeded"  # gateway approved (terminal)
        FAILED = "failed", "Failed"           # gateway declined / errored (terminal)

    # Public, human-friendly reference for this payment.
    payment_number = models.CharField(
        max_length=32, unique=True, editable=False, default=generate_payment_number
    )

    # External references (no FKs -- these live in other services).
    user_id = models.PositiveBigIntegerField(db_index=True)
    order_id = models.PositiveBigIntegerField(db_index=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Which gateway handled this, and its returned transaction reference.
    gateway = models.CharField(max_length=50, blank=True)
    gateway_reference = models.CharField(max_length=100, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    # Provenance: the bus event that triggered this charge (idempotency link).
    source_event_id = models.UUIDField(null=True, blank=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A completed charge is unique per order; retries are only allowed
            # while no successful payment exists.
            models.UniqueConstraint(
                fields=["order_id"],
                condition=models.Q(status="succeeded"),
                name="unique_succeeded_payment_per_order",
            )
        ]

    def __str__(self):
        return f"{self.payment_number} order={self.order_id} ({self.status})"


class ProcessedEvent(models.Model):
    """Idempotency ledger for the consumer. An incoming event is processed only
    if its event_id has not been seen before, making consumption safe against
    Kafka's at-least-once redelivery."""

    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type}:{self.event_id}"
