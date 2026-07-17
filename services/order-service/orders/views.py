import requests
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from . import saga
from .models import Cart, CartItem, Order
from .serializers import (
    AddCartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
)
from .util import fetch_product_data


def _active_cart(user_id):
    cart, _ = Cart.objects.get_or_create(user_id=user_id, status=Cart.Status.ACTIVE)
    return cart


class CartView(APIView):
    """GET the caller's active cart (created on first access)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart = _active_cart(request.user.id)
        return Response(CartSerializer(cart).data)


class CartItemsView(APIView):
    """Add a product to the active cart (quantity is additive)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payload = AddCartItemSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        product_id = payload.validated_data["product_id"]
        quantity = payload.validated_data["quantity"]

        # Snapshot name/price from product-service (synchronous read).
        try:
            product = fetch_product_data(product_id, token=request.auth)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 502
            if code == status.HTTP_404_NOT_FOUND:
                return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": "Product lookup failed."}, status=status.HTTP_502_BAD_GATEWAY)
        except requests.RequestException:
            return Response(
                {"detail": "Product service unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not product.get("is_available", True):
            return Response(
                {"detail": "Product is not available."}, status=status.HTTP_400_BAD_REQUEST
            )

        unit_price = product.get("discount_price") or product.get("price")
        cart = _active_cart(request.user.id)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product_id=product_id,
            defaults={
                "product_name": product.get("name", ""),
                "unit_price": unit_price,
                "quantity": quantity,
            },
        )
        if not created:
            # Refresh the price/name snapshot and add to the existing quantity.
            item.product_name = product.get("name", item.product_name)
            item.unit_price = unit_price
            item.quantity += quantity
            item.save()

        return Response(
            CartSerializer(cart).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CartItemDetailView(APIView):
    """Set the quantity of, or remove, a cart line (keyed by product id)."""

    permission_classes = [permissions.IsAuthenticated]

    def _get_item(self, request, product_id):
        cart = _active_cart(request.user.id)
        return cart, CartItem.objects.filter(cart=cart, product_id=product_id).first()

    def patch(self, request, product_id):
        cart, item = self._get_item(request, product_id)
        if item is None:
            return Response({"detail": "Item not in cart."}, status=status.HTTP_404_NOT_FOUND)
        payload = AddCartItemSerializer(data={"product_id": product_id, **request.data})
        payload.is_valid(raise_exception=True)
        item.quantity = payload.validated_data["quantity"]
        item.save(update_fields=["quantity", "updated_at"])
        return Response(CartSerializer(cart).data)

    def delete(self, request, product_id):
        cart, item = self._get_item(request, product_id)
        if item is None:
            return Response({"detail": "Item not in cart."}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(CartSerializer(cart).data)


class CheckoutView(APIView):
    """Turn the active cart into a PENDING order (kicks off the saga)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payload = CheckoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = (
            Cart.objects.filter(user_id=request.user.id, status=Cart.Status.ACTIVE)
            .prefetch_related("items")
            .first()
        )
        if cart is None:
            return Response({"detail": "No active cart."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = saga.checkout_cart(
                cart,
                shipping_name=payload.validated_data["shipping_name"],
                shipping_address=payload.validated_data["shipping_address"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(ListAPIView):
    """List the caller's orders."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user_id=self.request.user.id).prefetch_related("items")


class OrderDetailView(RetrieveAPIView):
    """Retrieve one of the caller's orders."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user_id=self.request.user.id).prefetch_related("items")


class OrderCancelView(APIView):
    """Cancel a still-cancellable order (emits the compensation event)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = Order.objects.filter(user_id=request.user.id, pk=pk).first()
        if order is None:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            order = saga.cancel_order(order.id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)
