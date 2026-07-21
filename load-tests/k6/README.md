# k6 Load Tests

Commands used to seed data, run the tests, and view results. Design rationale
(why the saga watchdog is isolated, why funnel conversion rates are what they
are, why metric names are what they are, etc.) lives in comments in the
scripts themselves, not here.

## Files
- `smoke.js` — 1 VU, golden path once, polls the saga to completion. Correctness gate, not a load test.
- `load-test.js` — ramping `shopper` funnel scenario (browse → cart → checkout with drop-off) plus a low-frequency `saga_watchdog` that measures saga SLA independently.
- `lib/` — shared config, auth, and helpers used by both.

## 1. Prerequisites
Observability stack must be up (Prometheus/Grafana) to see results:
```bash
cd ~/ecom
docker compose --profile observability up -d
```

## 2. Seed data (one-time, before a load-test run)
Makes the tables realistically large — several endpoints (unpaginated product
list with nested reviews, unindexed `Order.user_id` filter) only show their
real cost at volume.
```bash
docker compose exec user-service python manage.py generate_users_dummy_data --count 20000
docker compose exec product-service python manage.py generate_products_dummy_data --count 50000
docker compose exec product-service python manage.py generate_reviews_dummy_data --per-product 20
docker compose exec order-service python manage.py generate_orders_dummy_data --count 50000
```
Each command's `--help` lists its other options (batch size, user/product ID
ranges, etc.).

## 3. (Optional) Realistic payment failures
The base compose runs `PAYMENT_MODE=always_success`, so nothing ever hits the
CANCELLED/inventory-release path. To exercise it during a load test:
```bash
docker compose -f docker-compose.yaml -f docker-compose.loadtest.yml \
  up -d payment-service payment-consumer

# verify the merge before relying on it:
docker compose -f docker-compose.yaml -f docker-compose.loadtest.yml config
```
Revert afterward (restores `always_success`, which `smoke.js`'s deploy-gate
assertion depends on):
```bash
docker compose up -d payment-service payment-consumer
```

## 4. Run the smoke test (deploy gate)
```bash
docker compose --profile loadtest run k6
# equivalent explicitly:
docker compose --profile loadtest run k6 run /scripts/smoke.js --out experimental-prometheus-rw
```

## 5. Run the load test
```bash
docker compose --profile loadtest run k6 run /scripts/load-test.js --out experimental-prometheus-rw
```
Takes ~3 minutes (matches the scenario stage durations in `load-test.js`).

## 6. View results
- Grafana: `http://127.0.0.1:3000` (use `127.0.0.1`, not `localhost` — Windows browsers often resolve `localhost` to IPv6, which the Mutagen port forward doesn't cover) → **Ecommerce Overview** (app-side metrics) and **K6 Load Test** (VUs, request rate/latency, saga success rate/completion time) dashboards.
- Or query Prometheus directly, e.g.:
  ```bash
  curl -s "http://127.0.0.1:9090/api/v1/label/__name__/values" | grep k6_
  ```

## Reference: env vars
| Var | Where | Purpose |
|---|---|---|
| `USER_URL`, `PRODUCT_URL`, `ORDER_URL`, `PAYMENT_URL` | k6 service env (compose) | Base URLs; default to Mutagen-forwarded localhost ports if unset, so scripts also run directly from a laptop |
| `K6_PROMETHEUS_RW_SERVER_URL` | k6 service env (compose) | Where k6 pushes its own metrics (`http://prometheus:9090/api/v1/write`) |
| `K6_PROMETHEUS_RW_TREND_STATS` | k6 service env (compose) | Pins which stats (`p(95)`, `p(99)`, `avg`, `min`, `max`) get exported per Trend metric — keeps `k6_<metric>_<stat>` names deterministic |
| `PAYMENT_MODE`, `PAYMENT_FAILURE_RATE` | `docker-compose.loadtest.yml` override | Makes payments fail sometimes during load testing (see §3) |

## Gotchas already hit once
- Compose `command:`/`environment:` changes need `docker compose up -d <service>`, not `restart` — a running container doesn't pick up either.
- k6's Rate-type metrics get an auto-appended `_rate` suffix in Prometheus (e.g. `saga_success` → `k6_saga_success_rate`) — don't include `_rate` in the metric name in the script itself.
