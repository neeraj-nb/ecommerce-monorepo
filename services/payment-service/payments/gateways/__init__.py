"""Payment gateway abstraction + factory.

The rest of the service depends only on the ``PaymentGateway`` interface and
picks an implementation through ``get_gateway()``. Swapping the placeholder for a
real provider (Stripe, Razorpay, ...) is a matter of adding a new module here and
one branch in the factory -- no caller changes.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import ChargeRequest, GatewayResult, PaymentGateway
from .dummy import DummyPaymentGateway

__all__ = [
    "ChargeRequest",
    "GatewayResult",
    "PaymentGateway",
    "DummyPaymentGateway",
    "get_gateway",
]


def get_gateway():
    """Return the configured PaymentGateway instance (per ``PAYMENT_GATEWAY``)."""
    name = getattr(settings, "PAYMENT_GATEWAY", "dummy")

    if name == "dummy":
        return DummyPaymentGateway(
            mode=settings.PAYMENT_MODE,
            failure_rate=settings.PAYMENT_FAILURE_RATE,
            delay_seconds=settings.PAYMENT_DELAY_SECONDS,
        )

    # Add real providers here, e.g.:
    #   if name == "stripe":
    #       return StripePaymentGateway(api_key=settings.STRIPE_API_KEY)
    raise ImproperlyConfigured(f"Unknown PAYMENT_GATEWAY '{name}'")
