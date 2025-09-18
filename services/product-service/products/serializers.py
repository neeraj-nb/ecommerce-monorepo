from rest_framework import serializers
from .models import Product, Review
from .util import fetch_user_data


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']

    def get_user(self, obj):
        return fetch_user_data(obj.user_id, token=self.context.get('request').auth)


class ProductSerializer(serializers.ModelSerializer):
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock',
            'category', 'sku', 'is_active',
            'average_rating', 'total_reviews', 'reviews',
            'created_at', 'updated_at'
        ]