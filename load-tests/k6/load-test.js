// Load test: a single "shopper" funnel scenario (browse -> maybe cart-add ->
// maybe checkout, with realistic drop-off at each step and a Zipfian-ish hot
// product bias) plus a low-frequency "saga watchdog" that independently
// measures whether the async choreography (order.created -> inventory
// reserved -> payment -> confirmed) keeps up with its SLA under that load.
//
// The watchdog runs its own full checkout+poll flow rather than polling
// orders created by the shopper scenario, for two reasons: (1) there's no
// simple way to hand dynamically-created order IDs from one k6 scenario to
// another (k6 VUs are isolated JS runtimes; setup()'s return value is the
// only clean shared state, and it's fixed before the run starts), and
// (2) keeping it self-contained means saga_completion_time/saga_success stay
// a clean signal -- "is the saga meeting its SLA under load" -- instead of
// being entangled with the shopper scenario's own request pacing.
//
// The watchdog also gets its OWN dedicated small user pool, separate from the
// shopper scenario's pool: this app has one-active-cart-per-user, so two
// concurrent VUs sharing a user (one from `shopper`, one from the watchdog)
// could race on the same cart and produce a failure that's a test artifact,
// not a real saga problem.
//
// The realistic funnel/hot-product shape only matters for THIS scenario's own
// product picks; the raw size of the product/review/order tables (see the
// generate_*_dummy_data management commands) matters independently -- it
// makes the unpaginated browse-list/order-list endpoints expensive for
// EVERY caller regardless of which specific IDs this script happens to hit,
// so there's no need to coordinate product IDs between the two.
//
// Run:
//   docker compose --profile loadtest run k6 run /scripts/load-test.js --out experimental-prometheus-rw
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { PRODUCT_URL, ORDER_URL } from './lib/config.js';
import { registerAndLogin, refreshIfNeeded, authHeaders } from './lib/auth.js';
import { randomIntBetween, pickWeightedProduct } from './lib/util.js';

const sagaCompletionTime = new Trend('saga_completion_time', true);
// Named 'saga_success', not 'saga_success_rate': k6's Prometheus remote-write
// output auto-appends "_rate" to every Rate metric (confirmed against a real
// run -- e.g. the built-in http_req_failed exports as k6_http_req_failed_rate),
// so naming the raw metric 'saga_success_rate' would export as the redundant
// 'k6_saga_success_rate_rate'.
const sagaSuccessRate = new Rate('saga_success');

// Sized to match the shopper scenario's peak VU target (100) below, roughly
// 1:1, so concurrent VUs rarely have to share a user's cart -- this app has
// one-active-cart-per-user, and sharing under load creates test noise that
// isn't a real app problem (see the module docstring on the watchdog's pool).
const SHOPPER_USER_POOL_SIZE = 100;
const WATCHDOG_USER_POOL_SIZE = 5;
const PRODUCT_POOL_SIZE = 30;

// Funnel conversion rates: ~30% of browsers add to cart, ~40% of those check
// out (~12% of all sessions overall) -- commonly-cited realistic ballpark
// ranges for e-commerce, not this app's actual measured numbers. Tune these
// to whatever your real analytics say once you have them.
const CART_ADD_CONVERSION = 0.30;
const CHECKOUT_CONVERSION = 0.40;

export const options = {
  scenarios: {
    shopper: {
      executor: 'ramping-vus',
      exec: 'shopper',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 100 },
        { duration: '2m', target: 100 },
        { duration: '30s', target: 0 },
      ],
    },
    saga_watchdog: {
      executor: 'constant-arrival-rate',
      exec: 'sagaWatchdog',
      rate: 6, // 6 iterations per timeUnit
      timeUnit: '1m', // -> one full checkout+poll flow every ~10s
      duration: '3m',
      preAllocatedVUs: 3,
      maxVUs: 5,
    },
  },
  thresholds: {
    // Tagged per request type (see the `tags: { name: ... }` params below)
    // rather than per scenario -- now that browse/cart/checkout all happen
    // within one `shopper` scenario, scenario-level tagging can't tell them
    // apart the way separate scenarios used to.
    'http_req_duration{name:browse_list}': ['p(95)<300'],
    'http_req_duration{name:browse_detail}': ['p(95)<300'],
    'http_req_duration{name:checkout}': ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
    saga_success: ['rate>0.98'],
    saga_completion_time: ['p(95)<8000'],
  },
};

export function setup() {
  const shopperUsers = [];
  for (let i = 0; i < SHOPPER_USER_POOL_SIZE; i++) {
    const stamp = `${Date.now()}_sh_${i}`;
    shopperUsers.push(registerAndLogin(`loadtest_${stamp}@example.com`, 'Zx9qBv7Lm2wKpQ!', `loadtest_${stamp}`));
  }

  const watchdogUsers = [];
  for (let i = 0; i < WATCHDOG_USER_POOL_SIZE; i++) {
    const stamp = `${Date.now()}_wd_${i}`;
    watchdogUsers.push(registerAndLogin(`watchdog_${stamp}@example.com`, 'Zx9qBv7Lm2wKpQ!', `watchdog_${stamp}`));
  }

  const auth = authHeaders(shopperUsers[0]);
  const productIds = [];
  for (let i = 0; i < PRODUCT_POOL_SIZE; i++) {
    const res = http.post(
      `${PRODUCT_URL}/api/products/create/`,
      JSON.stringify({
        name: `Load Widget ${Date.now()}_${i}`,
        desc: 'k6 load test',
        stock: 100000, // effectively unlimited so stock exhaustion isn't a variable in this run
        price: '19.99',
        discount_price: '14.99',
        sold_by: 'k6',
      }),
      auth
    );
    if (res.status === 201) productIds.push(res.json('id'));
  }

  return { shopperUsers, watchdogUsers, productIds };
}

export function shopper(data) {
  const productId = pickWeightedProduct(data.productIds);

  // Everyone browses.
  const listRes = http.get(`${PRODUCT_URL}/api/products/`, { tags: { name: 'browse_list' } });
  check(listRes, { 'browse list ok': (r) => r.status === 200 });
  const detailRes = http.get(`${PRODUCT_URL}/api/products/${productId}/`, { tags: { name: 'browse_detail' } });
  check(detailRes, { 'browse detail ok': (r) => r.status === 200 });
  sleep(randomIntBetween(1, 3));

  if (Math.random() > CART_ADD_CONVERSION) return; // drops off here -- browsed, didn't add to cart

  let session = data.shopperUsers[__VU % data.shopperUsers.length];
  session = refreshIfNeeded(session);
  const auth = authHeaders(session);
  const cartParams = Object.assign({}, auth, { tags: { name: 'cart_add' } });
  http.post(
    `${ORDER_URL}/api/cart/items/`,
    JSON.stringify({ product_id: productId, quantity: randomIntBetween(1, 3) }),
    cartParams
  );
  sleep(randomIntBetween(1, 2));

  if (Math.random() > CHECKOUT_CONVERSION) return; // drops off here -- cart abandoned

  const checkoutParams = Object.assign({}, auth, { tags: { name: 'checkout' } });
  const res = http.post(
    `${ORDER_URL}/api/checkout/`,
    JSON.stringify({ shipping_name: 'k6 load', shipping_address: '1 Load St' }),
    checkoutParams
  );
  check(res, { 'checkout accepted': (r) => r.status === 201 });
}

export function sagaWatchdog(data) {
  const session = data.watchdogUsers[randomIntBetween(0, data.watchdogUsers.length - 1)];
  const auth = authHeaders(session);
  const productId = data.productIds[randomIntBetween(0, data.productIds.length - 1)];

  http.post(`${ORDER_URL}/api/cart/items/`, JSON.stringify({ product_id: productId, quantity: 1 }), auth);
  const checkoutRes = http.post(
    `${ORDER_URL}/api/checkout/`,
    JSON.stringify({ shipping_name: 'watchdog', shipping_address: 'watchdog' }),
    auth
  );
  if (checkoutRes.status !== 201) {
    sagaSuccessRate.add(false);
    return;
  }
  const orderId = checkoutRes.json('id');

  const start = Date.now();
  let finalStatus = null;
  for (let i = 0; i < 15; i++) {
    sleep(1);
    const orderRes = http.get(`${ORDER_URL}/api/orders/${orderId}/`, auth);
    const status = orderRes.json('status');
    if (status === 'confirmed' || status === 'cancelled') {
      finalStatus = status;
      break;
    }
  }
  sagaCompletionTime.add(Date.now() - start);
  sagaSuccessRate.add(finalStatus === 'confirmed');
}
