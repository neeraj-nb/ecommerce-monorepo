// Smoke test: one VU, one full pass through the golden path, including
// polling the async saga to completion. This is a correctness gate (run on
// every deploy), not a load test -- see load-test.js for throughput/SLOs.
//
// Run:
//   docker compose --profile loadtest run k6
//   (or against the Mutagen-forwarded ports directly: k6 run smoke.js)
import http from 'k6/http';
import { check, sleep } from 'k6';
import { USER_URL, PRODUCT_URL, ORDER_URL, PAYMENT_URL } from './lib/config.js';
import { registerAndLogin, authHeaders } from './lib/auth.js';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    // Every check must pass -- any failure here means the golden path itself
    // is broken, which should fail the deploy, not just get reported.
    checks: ['rate==1.0'],
  },
};

export default function () {
  const stamp = `${__VU}_${Date.now()}`;
  const email = `smoke_${stamp}@example.com`;
  const session = registerAndLogin(email, 'Zx9qBv7Lm2wKpQ!', `smoke_${stamp}`);
  check(session, { 'got access token': (s) => !!s.access });
  const auth = authHeaders(session);

  const productRes = http.post(
    `${PRODUCT_URL}/api/products/create/`,
    JSON.stringify({
      name: `Smoke Widget ${stamp}`,
      desc: 'k6 smoke test',
      stock: 10,
      price: '49.99',
      discount_price: '39.99',
      sold_by: 'k6',
    }),
    auth
  );
  check(productRes, { 'product created': (r) => r.status === 201 });
  const productId = productRes.json('id');

  const cartRes = http.post(
    `${ORDER_URL}/api/cart/items/`,
    JSON.stringify({ product_id: productId, quantity: 1 }),
    auth
  );
  check(cartRes, { 'cart add ok': (r) => r.status === 201 || r.status === 200 });

  const checkoutRes = http.post(
    `${ORDER_URL}/api/checkout/`,
    JSON.stringify({ shipping_name: 'k6 smoke', shipping_address: '1 Test St' }),
    auth
  );
  check(checkoutRes, { 'checkout accepted': (r) => r.status === 201 });
  const orderId = checkoutRes.json('id');

  // Poll for saga completion. The 60s OTel metric-export interval doesn't
  // affect this -- the saga itself (Kafka choreography) settles in a few
  // seconds, independent of when metrics get scraped.
  let finalStatus = null;
  for (let i = 0; i < 20; i++) {
    sleep(1.5);
    const orderRes = http.get(`${ORDER_URL}/api/orders/${orderId}/`, auth);
    const status = orderRes.json('status');
    if (status === 'confirmed' || status === 'cancelled') {
      finalStatus = status;
      break;
    }
  }
  check(finalStatus, { 'saga reached confirmed': (s) => s === 'confirmed' });

  const paymentsRes = http.get(`${PAYMENT_URL}/api/payments/?order_id=${orderId}`, auth);
  const payments = Array.isArray(paymentsRes.json())
    ? paymentsRes.json()
    : paymentsRes.json('results') || [];
  check(payments, { 'exactly one payment recorded': (p) => p.length === 1 });
  check(payments, {
    'payment succeeded': (p) => p.length === 1 && p[0].status === 'succeeded',
  });
}
