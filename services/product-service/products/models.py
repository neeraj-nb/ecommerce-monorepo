from django.db import models
from django.utils.text import slugify

class Product(models.Model):
    name = models.CharField(max_length=100)
    desc = models.TextField(max_length=500)
    category = models.CharField(max_length=50, null=True)
    slug = models.SlugField(max_length=50, unique=True, editable=False)
    picture = models.ImageField(upload_to="products/images",null=True,blank=True)
    stock = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10,decimal_places=2)
    discount_price = models.DecimalField(max_digits=10,decimal_places=2)
    sold_by = models.CharField(max_length=100)
    is_available = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)  # Auto updated
    total_reviews = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name).lower()
        return super(Product, self).save(*args, **kwargs)

    def update_rating(self):
        """Recalculate average rating and total reviews."""
        reviews = self.reviews.all()
        self.total_reviews = reviews.count()
        self.average_rating = (
            reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0
        )
        self.save()
        
    def update_rating_add(self, new):
        """Recalculate average rating and total reviews."""
        self.total_reviews = self.total_reviews + 1
        self.average_rating = (self.average_rating * (self.total_reviews-1) + new)/ self.total_reviews
        self.save()
        
    def update_rating_delete(self, remove):
        """Recalculate average rating and total reviews."""
        self.total_reviews = self.total_reviews - 1
        self.average_rating = (self.average_rating * (self.total_reviews+1) - remove)/ self.total_reviews
        self.save()
    
    def _str_(self):
        return self.name
        
class Review(models.Model):
    
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    user_id = models.PositiveBigIntegerField()  # external user-service id (JWT 'user_id' claim)
    rating = models.PositiveSmallIntegerField()  # 1-5 stars
    title = models.CharField(max_length=100)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user_id')  # Prevent duplicate reviews by the same user
        ordering = ['-created_at']

    def _str_(self):
        return f"{self.product.name} - {self.title}"

    def save(self, *args, **kwargs):
        """Override save to auto-update product rating."""
        super().save(*args, **kwargs)
        self.product.update_rating_add(self.rating)
        
    def delete(self, *args, **kwargs):
        """Override delete to auto-update product rating."""
        super().delete(*args, **kwargs)
        self.product.update_rating_delete(self.rating)


class InventoryReservation(models.Model):
    """Stock held for one order, created when this service reserves inventory in
    response to ``order.created``. Kept so the reservation can be released back
    to stock on ``order.cancelled`` (compensation), and so redelivery of the same
    order does not reserve twice (``order_id`` is unique)."""

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        RELEASED = "released", "Released"

    order_id = models.PositiveBigIntegerField(unique=True)  # external order-service id
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RESERVED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reservation order={self.order_id} ({self.status})"


class ReservationItem(models.Model):
    """A per-product quantity within a reservation (the amount to give back on release)."""

    reservation = models.ForeignKey(
        InventoryReservation, related_name="items", on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product, related_name="reservation_items", on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x product {self.product_id} (reservation {self.reservation_id})"


class ProcessedEvent(models.Model):
    """Idempotency ledger for the inventory consumer. An incoming event is
    processed only if its event_id has not been seen before, making consumption
    safe against Kafka's at-least-once redelivery."""

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