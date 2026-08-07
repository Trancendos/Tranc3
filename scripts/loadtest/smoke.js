// scripts/loadtest/smoke.js
//
// No perf/load-testing gate has existed anywhere in this repo's CI — no
// k6/locust, no latency regression check, nothing. This is a deliberately
// small first step, not a full load-test suite: light, constant traffic
// against the root API's cheapest real endpoints, checking that basic
// request handling doesn't regress into multi-second latency or start
// erroring under a handful of concurrent users.
//
// This is NOT a capacity/stress test — 5 VUs proves "didn't break", not
// "handles production load". Thresholds are deliberately generous (no
// historical baseline exists yet to tighten them against); see
// .forgejo/workflows/perf-smoke.yml for how this is wired in as
// warn-only until a real baseline is established.
//
// Usage: k6 run scripts/loadtest/smoke.js
//        k6 run -e BASE_URL=http://localhost:8000 scripts/loadtest/smoke.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: 5,
      duration: "20s",
    },
  },
  thresholds: {
    // Generous on purpose — first-ever gate, no baseline to tighten
    // against. Revisit once this has run for a while on real hardware.
    http_req_duration: ["p(95)<1000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "/health is 200": (r) => r.status === 200,
  });

  const ready = http.get(`${BASE_URL}/ready`);
  check(ready, {
    // /ready is 503 while bootstrapping — that's a valid, non-error state
    // this smoke test must not fail on, only genuine 4xx/5xx-elsewhere or
    // connection failures should count against http_req_failed.
    "/ready responds 200 or 503": (r) => r.status === 200 || r.status === 503,
  });

  sleep(1);
}
