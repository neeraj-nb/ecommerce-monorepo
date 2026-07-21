// Shared auth helpers: register/login once (in setup()), then reuse the
// token across a VU's iterations rather than hitting /register/ or /login/
// every time -- that keeps auth-endpoint load intentional/controlled instead
// of an accidental side effect of running any other scenario.
import http from 'k6/http';
import { check } from 'k6';
import { USER_URL } from './config.js';

// SimpleJWT's default access-token lifetime is 5 minutes; refresh a bit
// before that so a long-running load/soak test doesn't start seeing 401s
// that are a test artifact rather than a real app problem.
const ACCESS_TOKEN_MAX_AGE_S = 4 * 60;

export function registerAndLogin(email, password, username) {
  http.post(
    `${USER_URL}/api/register/`,
    JSON.stringify({ username, email, password }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  return login(email, password);
}

export function login(email, password) {
  const res = http.post(
    `${USER_URL}/api/login/`,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  check(res, { 'login succeeded': (r) => r.status === 200 });
  const body = res.json();
  return { access: body.access, refresh: body.refresh, issuedAt: Date.now() };
}

// Returns a session guaranteed to have a fresh-enough access token. Cheap to
// call every iteration -- it only makes a network call when actually needed.
export function refreshIfNeeded(session) {
  const ageS = (Date.now() - session.issuedAt) / 1000;
  if (ageS < ACCESS_TOKEN_MAX_AGE_S) return session;

  const res = http.post(
    `${USER_URL}/api/token/refresh/`,
    JSON.stringify({ refresh: session.refresh }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  if (res.status !== 200) return session; // stale refresh token; caller's next request will surface the 401
  return { access: res.json('access'), refresh: session.refresh, issuedAt: Date.now() };
}

export function authHeaders(session) {
  return {
    headers: {
      Authorization: `Bearer ${session.access}`,
      'Content-Type': 'application/json',
    },
  };
}
