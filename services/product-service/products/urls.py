from django.urls import path
from .views import ProductListView, ProductView, ProductCreateView, ReviewListCreateView
urlpatterns = [
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/create/', ProductCreateView.as_view(), name='product-create'),
    path('products/<int:pk>/', ProductView.as_view(), name='product-detail'),
    path('products/<int:product_pk>/reviews/', ReviewListCreateView.as_view(), name='review-list-create'),
]