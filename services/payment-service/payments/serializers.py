from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id", "payment_number", "user_id", "order_id",
            "amount", "currency", "status",
            "gateway", "gateway_reference", "failure_reason",
            "created_at", "updated_at", "processed_at",
        ]
        read_only_fields = fields
