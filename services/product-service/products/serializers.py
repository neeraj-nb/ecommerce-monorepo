from rest_framework import serializers
from .models import Product, Review
from .util import fetch_user_data


class ReviewSerializer(serializers.ModelSerializer):
    user_id = serializers.StringRelatedField(read_only=True)
    # TODO : Broken
    class Meta:
        model = Review
        fields = ['id', 'user_id', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user_id', 'created_at']

    def get_user_id(self, obj):
        return fetch_user_data(obj.user_id, token=self.context.get('request').auth)


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