"""Read-only ledger API.

Payments are created by the event-driven saga, not by clients, so the API is
query-only. A caller sees their own payments; a staff caller (``role=admin`` in
the JWT) sees all. Both list and detail can be filtered by ``order_id``.
"""

from rest_framework import permissions
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import Payment
from .serializers import PaymentSerializer


class _ScopedPaymentQuerysetMixin:
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.all()
        # Non-staff callers only ever see their own payments.
        if not self.request.user.is_staff:
            qs = qs.filter(user_id=self.request.user.id)
        order_id = self.request.query_params.get("order_id")
        if order_id:
            qs = qs.filter(order_id=order_id)
        return qs


class PaymentListView(_ScopedPaymentQuerysetMixin, ListAPIView):
    """List the caller's payments (all payments if staff)."""


class PaymentDetailView(_ScopedPaymentQuerysetMixin, RetrieveAPIView):
    """Retrieve one of the caller's payments by id."""
