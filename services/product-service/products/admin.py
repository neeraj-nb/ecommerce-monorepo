from django.contrib import admin

from .models import InventoryReservation, Outbox, ProcessedEvent, ReservationItem


class ReservationItemInline(admin.TabularInline):
    model = ReservationItem
    extra = 0


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = ("order_id", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("order_id",)
    inlines = [ReservationItemInline]


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
