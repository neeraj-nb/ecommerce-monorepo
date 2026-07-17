from rest_framework import serializers

from .models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product_id", "product_name", "unit_price", "quantity", "subtotal"]
        read_only_fields = ["id", "product_name", "unit_price", "subtotal"]


class AddCartItemSerializer(serializers.Serializer):
    """Input for adding/updating a cart line. Only the product id and quantity
    come from the client; name and price are snapshotted from product-service."""

    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "user_id", "status", "items", "total_amount", "created_at", "updated_at"]
        read_only_fields = fields


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_id", "product_name", "unit_price", "quantity", "subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "user_id", "status", "total_amount", "currency",
            "shipping_name", "shipping_address", "cancel_reason",
            "items", "created_at", "updated_at",
        ]
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    """Input for turning the active cart into an order."""

    shipping_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    shipping_address = serializers.CharField(required=False, allow_blank=True, default="")
