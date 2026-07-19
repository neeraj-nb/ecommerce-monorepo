"""Placeholder payment gateway.

Does not talk to any real processor -- it fabricates a gateway-like response and
decides success/failure from configurable policy, so the rest of the system can
be exercised end-to-end. Its response shape mimics a real provider (an id + a
status + the echoed amount) so swapping in a real gateway needs no caller change.

Policy (from settings, ultimately env vars):
    mode = "always_success"  -> every charge approved (default)
    mode = "always_fail"     -> every charge declined
    mode = "random"          -> declined with probability ``failure_rate``
"""

import logging
import random
import time
import uuid

from .base import ChargeRequest, GatewayResult, PaymentGateway

logger = logging.getLogger(__name__)

MODE_ALWAYS_SUCCESS = "always_success"
MODE_ALWAYS_FAIL = "always_fail"
MODE_RANDOM = "random"
VALID_MODES = {MODE_ALWAYS_SUCCESS, MODE_ALWAYS_FAIL, MODE_RANDOM}


class DummyPaymentGateway(PaymentGateway):
    name = "dummy"

    def __init__(self, mode=MODE_ALWAYS_SUCCESS, failure_rate=0.3,
                 delay_seconds=0.0, rng=None):
        mode = (mode or MODE_ALWAYS_SUCCESS).strip().lower()
        if mode not in VALID_MODES:
            logger.warning("invalid PAYMENT_MODE=%r; using %s", mode, MODE_ALWAYS_SUCCESS)
            mode = MODE_ALWAYS_SUCCESS
        self.mode = mode
        self.failure_rate = min(max(failure_rate, 0.0), 1.0)
        self.delay_seconds = max(delay_seconds, 0.0)
        self._rng = rng or random

    def _approves(self):
        if self.mode == MODE_ALWAYS_SUCCESS:
            return True
        if self.mode == MODE_ALWAYS_FAIL:
            return False
        return self._rng.random() >= self.failure_rate  # MODE_RANDOM

    def charge(self, request: ChargeRequest) -> GatewayResult:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)  # simulate provider latency

        reference = f"dummy_{uuid.uuid4().hex}"
        approved = self._approves()
        amount_str = f"{request.amount}"

        if approved:
            raw = {
                "id": reference,
                "object": "charge",
                "status": "succeeded",
                "amount": amount_str,
                "currency": request.currency,
                "livemode": False,
            }
            return GatewayResult(
                success=True, reference=reference, status="succeeded", raw=raw
            )

        raw = {
            "id": reference,
            "object": "charge",
            "status": "declined",
            "amount": amount_str,
            "currency": request.currency,
            "failure_code": "card_declined",
            "livemode": False,
        }
        return GatewayResult(
            success=False,
            reference=reference,
            status="declined",
            message="Payment declined (simulated).",
            raw=raw,
        )
