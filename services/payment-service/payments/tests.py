from decimal import Decimal

from django.test import TestCase, override_settings

from .gateways.dummy import DummyPaymentGateway
from .gateways.base import ChargeRequest
from .models import Payment
from . import service


def _req(order_id=1, user_id=1, amount="42.00"):
    return ChargeRequest(order_id=order_id, user_id=user_id, amount=Decimal(amount))


class DummyGatewayTests(TestCase):
    def test_always_success(self):
        gw = DummyPaymentGateway(mode="always_success")
        self.assertTrue(all(gw.charge(_req()).success for _ in range(50)))

    def test_always_fail(self):
        gw = DummyPaymentGateway(mode="always_fail")
        results = [gw.charge(_req()) for _ in range(50)]
        self.assertFalse(any(r.success for r in results))
        self.assertTrue(all(r.message for r in results))

    def test_random_respects_rate(self):
        import random
        gw = DummyPaymentGateway(mode="random", failure_rate=0.3, rng=random.Random(0))
        successes = sum(gw.charge(_req()).success for _ in range(2000))
        self.assertTrue(0.62 < successes / 2000 < 0.78)

    def test_invalid_mode_falls_back(self):
        self.assertEqual(DummyPaymentGateway(mode="bogus").mode, "always_success")


@override_settings(PAYMENT_GATEWAY="dummy", PAYMENT_MODE="always_success",
                   PAYMENT_FAILURE_RATE=0.0, PAYMENT_DELAY_SECONDS=0.0)
class ProcessPaymentTests(TestCase):
    def test_success_records_ledger(self):
        p = service.process_payment(order_id=10, user_id=5, amount="99.99")
        self.assertEqual(p.status, Payment.Status.SUCCEEDED)
        self.assertEqual(p.amount, Decimal("99.99"))
        self.assertTrue(p.gateway_reference)
        self.assertTrue(p.payment_number.startswith("PAY-"))

    def test_idempotent_no_double_charge(self):
        first = service.process_payment(order_id=11, user_id=5, amount="10.00")
        second = service.process_payment(order_id=11, user_id=5, amount="10.00")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.filter(order_id=11).count(), 1)

    @override_settings(PAYMENT_MODE="always_fail")
    def test_failure_records_reason(self):
        p = service.process_payment(order_id=12, user_id=5, amount="10.00")
        self.assertEqual(p.status, Payment.Status.FAILED)
        self.assertTrue(p.failure_reason)
