from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem, ProcessedEvent


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "status", "updated_at")
    list_filter = ("status",)
    inlines = [CartItemInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "status", "total_amount", "currency", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("id", "user_id")
    inlines = [OrderItemInline]


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at")
    search_fields = ("event_id", "event_type")
