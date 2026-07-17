from rest_framework import serializers
from .models import Product, Review


class ReviewSerializer(serializers.ModelSerializer):
    # user_id is the external user-service id, taken from the verified JWT
    # in the view (perform_create) -- never set by the client.
    class Meta:
        model = Review
        fields = ['id', 'user_id', 'rating', 'title', 'comment', 'created_at']
        read_only_fields = ['id', 'user_id', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'desc', 'slug', 'picture', 'price', 'stock', 'discount_price',
            'category', 'is_active', 'sold_by', 'is_available', 'is_visible',
            'average_rating', 'total_reviews', 'reviews',
            'created_at', 'updated_at'
        ]
