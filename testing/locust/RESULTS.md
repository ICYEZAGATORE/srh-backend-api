# Step 4 — Scalability / concurrent-user load test (Locust)

**Config:** 10 concurrent users, spawn rate 2/s, 3 min, realistic session
(start session → ask → think 3–8 s → repeat) against the **deployed** backend
`https://srh-backend-api.onrender.com`. Cap = 10 users (deliberate — real production
evidence without risking a free-tier outage). Artifacts: `results/locust_report.html`,
`results/locust_stats.csv`, `results/locust_stats_history.csv`.

Reproduce:
```
cd testing/locust
../../venv/Scripts/python.exe -m locust -f locustfile.py \
  --host https://srh-backend-api.onrender.com --headless -u 10 -r 2 -t 3m \
  --html results/locust_report.html --csv results/locust
```

## Result — stable at 10 concurrent users, 0% errors

| endpoint | reqs | fails | p50 | p90 | p95 | p99 | max | throughput |
|---|---|---|---|---|---|---|---|---|
| POST /chat | 259 | **0 (0.00%)** | 520 ms | 740 ms | 2800 ms | 3800 ms | 4022 ms | 1.46 req/s |
| POST /session/start | 10 | 0 (0.00%) | 650 ms | 1200 ms | 1200 ms | 1200 ms | 1156 ms | — |
| GET /health | 31 | 0 (0.00%) | 370 ms | 450 ms | 510 ms | 510 ms | 513 ms | 0.17 req/s |
| **Aggregated** | **300** | **0 (0.00%)** | 510 ms | 740 ms | 1700 ms | 3800 ms | 4022 ms | 1.69 req/s |

- **Error rate: 0.00%** (0/300). **Timeout rate: 0%.** No exceptions.
- Chat p95 = 2.8 s at 10 users — well within the 15 s budget; the p99/max (~4 s) reflect
  the LLM leg under concurrency, not failures.
- No cold start occurred during the run (backend was warm); the first-request cold-start
  (~62 s) is characterised separately in `testing/performance/`.

## Interpretation for the panel
- The system is **stable at the tested load (10 concurrent users) with zero errors** — a
  legitimate, useful data point even though nothing broke. It is **not** a breaking-point
  result; finding the breaking point was intentionally not attempted against production.
- **Caching decision:** there is **no application-level response cache**. At the expected
  load (a pilot with well under 10 concurrent users) this is an acceptable, deliberate call
  — 0% errors and p95 ≈ 2.8 s confirm the uncached RAG+LLM path holds. It **would** become a
  gap at higher scale (repeated identical questions re-run the full LLM path); a semantic/
  response cache is the first scaling lever if load grows.

## Recommended next step (not run now)
Higher-concurrency breaking-point testing (25 / 50 / 100 users) against a **local or staging
replica** — never production — to locate the knee of the latency curve. Re-authorisation
required before exceeding 10 users anywhere near production.
