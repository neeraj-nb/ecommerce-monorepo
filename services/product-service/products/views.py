from rest_framework import viewsets, permissions
from rest_framework.generics import (
    ListAPIView,
    RetrieveAPIView,
    CreateAPIView,
    UpdateAPIView,
    ListCreateAPIView
)
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .models import Product, Review
from .serializers import ProductSerializer, ReviewSerializer


class ProductListView(ListAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer

class ProductView(RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer

class ProductCreateView(CreateAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

class ReviewListCreateView(ListCreateAPIView):
    serializer_class = ReviewSerializer
    # Anyone can read reviews; only authenticated users may post one.
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        product_id = self.kwargs['product_pk']
        return Review.objects.filter(product_id=product_id)

    def perform_create(self, serializer):
        product = get_object_or_404(Product, id=self.kwargs['product_pk'])
        user_id = self.request.user.id  # from the verified JWT (RemoteUser)

        # Check if user already reviewed
        if Review.objects.filter(product=product, user_id=user_id).exists():
            raise ValidationError("You have already reviewed this product.")

        serializer.save(user_id=user_id, product=product)
