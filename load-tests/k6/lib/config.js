// Base URLs for each service. Defaults match the Mutagen-forwarded laptop
// ports (see mutagen.yml) so these scripts also run unchanged directly from a
// laptop against the dev VM. Inside docker-compose/k8s, the env vars point at
// internal service DNS names instead (see the k6 service in docker-compose.yaml).
export const USER_URL = __ENV.USER_URL || 'http://localhost:8000';
export const PRODUCT_URL = __ENV.PRODUCT_URL || 'http://localhost:8001';
export const ORDER_URL = __ENV.ORDER_URL || 'http://localhost:8002';
export const PAYMENT_URL = __ENV.PAYMENT_URL || 'http://localhost:8003';
