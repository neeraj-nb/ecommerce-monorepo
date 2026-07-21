from decimal import Decimal

from django.db import models


class Cart(models.Model):
    """A user's active shopping cart. One active cart per user_id at a time."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CHECKED_OUT = "checked_out", "Checked out"

    user_id = models.PositiveBigIntegerField()  # external user-service id (JWT 'user_id')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # At most one active cart per user (checked-out carts are kept for history).
            models.UniqueConstraint(
                fields=["user_id"],
                condition=models.Q(status="active"),
                name="unique_active_cart_per_user",
            )
        ]

    def __str__(self):
        return f"Cart<{self.id}> user={self.user_id} ({self.status})"

    @property
    def total_amount(self):
        return sum((item.subtotal for item in self.items.all()), Decimal("0.00"))


class CartItem(models.Model):
    """A product line in a cart. Product name/price are snapshotted from the
    product-service at add time (a synchronous read); stock is not touched here."""

    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product_id = models.PositiveBigIntegerField()  # external product-service id
    product_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("cart", "product_id")  # one line per product per cart

    def __str__(self):
        return f"{self.quantity} x {self.product_name} (cart {self.cart_id})"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


class Order(models.Model):
    """An order and its saga state.

    Lifecycle (choreography saga):
        PENDING            -> created at checkout, order.created emitted
        INVENTORY_RESERVED -> inventory.reserved received
        CONFIRMED          -> payment.succeeded received (terminal, success)
        CANCELLED          -> inventory.rejected / payment.failed / user cancel
                              (terminal; order.cancelled emitted for compensation)
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending inventory"
        INVENTORY_RESERVED = "inventory_reserved", "Inventory reserved / awaiting payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    # States from which a user may still cancel, and non-terminal states.
    CANCELLABLE_STATUSES = {Status.PENDING, Status.INVENTORY_RESERVED}
    TERMINAL_STATUSES = {Status.CONFIRMED, Status.CANCELLED}

    user_id = models.PositiveBigIntegerField()  # external user-service id
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    # Denormalised shipping snapshot (order owns its shipping data).
    shipping_name = models.CharField(max_length=120, blank=True)
    shipping_address = models.TextField(blank=True)

    # Reason recorded when an order is cancelled/failed.
    cancel_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order<{self.id}> user={self.user_id} ({self.status})"

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL_STATUSES

    @property
    def can_cancel(self):
        return self.status in self.CANCELLABLE_STATUSES


class OrderItem(models.Model):
    """A line in an order. Price/name are snapshotted at checkout so the order
    is immutable against later product changes."""

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_id = models.PositiveBigIntegerField()
    product_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.product_name} (order {self.order_id})"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


class ProcessedEvent(models.Model):
    """Idempotency ledger for the consumer. An incoming event is processed only
    if its event_id has not been seen before, making consumption safe against
    Kafka's at-least-once redelivery."""

    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type}:{self.event_id}"


class Outbox(models.Model):
    """Transactional outbox: durably records that an event needs to be sent to
    Kafka, written in the SAME transaction as the state change it announces
    (see events.enqueue). A separate relay process (run_outbox_relay) delivers
    it, retrying independently of whether Kafka happened to be reachable at
    commit time -- so a Kafka outage can no longer turn a successful DB write
    into a client-facing error, or silently drop an event after a crash."""

    topic = models.CharField(max_length=100)
    key = models.CharField(max_length=100)  # Kafka message key, e.g. order_id
    # The full, already-built envelope (event_id/event_type/version/occurred_at/
    # data) -- built once here, not regenerated by the relay, so a retried
    # delivery resends the SAME event_id and downstream dedupe stays correct.
    envelope = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['published_at', 'created_at']),
        ]

    def __str__(self):
        return f"Outbox<{self.id}> {self.topic} key={self.key} published={bool(self.published_at)}"
