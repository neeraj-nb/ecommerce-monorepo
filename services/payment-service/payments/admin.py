from django.contrib import admin

from .models import Payment, ProcessedEvent


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
