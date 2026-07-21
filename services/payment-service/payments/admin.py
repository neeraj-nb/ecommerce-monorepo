from django.contrib import admin

from .models import Outbox, Payment, ProcessedEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_number", "order_id", "user_id", "amount", "currency",
        "status", "gateway", "created_at",
    )
    list_filter = ("status", "currency", "gateway")
    search_fields = ("payment_number", "order_id", "user_id", "gateway_reference")
    readonly_fields = [f.name for f in Payment._meta.fields]


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at")
    search_fields = ("event_id", "event_type")


@admin.register(Outbox)
class OutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "key", "created_at", "published_at")
    list_filter = ("topic",)
    search_fields = ("key",)
    readonly_fields = [f.name for f in Outbox._meta.fields]
