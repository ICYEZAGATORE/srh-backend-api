# Step 2 — API performance vs budgets (single-user, warm)

Target: `https://srh-backend-api.onrender.com/api/v1`  ·  health n=30, chat n=20

| endpoint | p50 | p95 | p99 | min | max | mean | throughput | err | timeout |
|---|---|---|---|---|---|---|---|---|---|
| GET /health | 1418 | 2130 | 2317 | 1204 | 2317 | 1521 | 0.657/s | 0.0 | 0.0 |
| POST /chat | 1885 | 4251 | 6626 | 1472 | 6626 | 2516 | 0.397/s | 0.0 | 0.0 |
*(all latencies in ms)*

## Budget check

| budget | target | measured | verdict |
|---|---|---|---|
| health p95 | <= 1000 ms | 2130 ms | MISS |
| chat p95 | <= 15000 ms | 4251 ms | PASS |
| chat error rate | <= 0.05 | 0.0 | PASS |
| first-request (cold) | <= 90 s | 6.6 s | PASS |

> First-request latency includes any cold start. Compare p50 (warm) against max (possible cold) to distinguish a cold start from a hang.