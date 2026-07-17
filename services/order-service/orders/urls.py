from django.urls import path

from .views import (
    CartItemDetailView,
    CartItemsView,
    CartView,
    CheckoutView,
    OrderCancelView,
    OrderDetailView,
    OrderListView,
)

urlpatterns = [
    # Cart
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/items/', CartItemsView.as_view(), name='cart-items'),
    path('cart/items/<int:product_id>/', CartItemDetailView.as_view(), name='cart-item-detail'),
    # Orders
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
]
