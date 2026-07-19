"""The gateway interface every payment provider implements.

Keeping this provider-agnostic means the ledger/saga code never depends on a
specific processor: it builds a ``ChargeRequest``, calls ``charge()``, and reads a
``GatewayResult`` back. A real integration just returns the same shapes.
"""

import abc
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ChargeRequest:
    """A request to charge a customer for an order."""

    order_id: int
    user_id: int
    amount: Decimal
    currency: str = "USD"
    # Passed to the provider so a retry of the same charge is not double-billed.
    idempotency_key: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class GatewayResult:
    """A provider's answer to a charge, normalised across gateways."""

    success: bool
    reference: str = ""      # provider transaction id
    status: str = ""         # provider-native status, e.g. "succeeded"/"declined"
    message: str = ""        # human-readable detail (esp. on failure)
    raw: dict = field(default_factory=dict)  # full provider response, for audit


class PaymentGateway(abc.ABC):
    """Interface implemented by every payment provider (real or placeholder)."""

    name = "base"

    @abc.abstractmethod
    def charge(self, request: ChargeRequest) -> GatewayResult:
        """Attempt to charge; return a GatewayResult (never raise on decline)."""
        raise NotImplementedError

    def refund(self, reference: str, amount: Decimal = None) -> GatewayResult:
        """Refund a previous charge. Optional; override in providers that support it."""
        raise NotImplementedError(f"{self.name} gateway does not support refunds")
