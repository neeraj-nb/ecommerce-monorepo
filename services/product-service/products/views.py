from rest_framework import viewsets, permissions
from rest_framework.exceptions import ValidationError
from .models import Product, Review
from .serializers import ProductSerializer, ReviewSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    # permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        product_id = self.kwargs['product_pk']
        return Review.objects.filter(product_id=product_id)

    def perform_create(self, serializer):
        product_id = self.kwargs['product_pk']
        product = Product.objects.get(id=product_id)

        # Check if user already reviewed
        if Review.objects.filter(product=product, user=self.request.user).exists():
            raise ValidationError("You have already reviewed this product.")

        serializer.save(user=self.request.user, product=product)
