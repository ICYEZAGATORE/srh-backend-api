# SRH Platform — System Testing & V&V Suite

Runnable tests + captured evidence for the capstone defense. Organised modularly by
category. Every category has a short results summary with **tables across realistic
conditions** and honestly-reported findings (real bugs/degradation are documented, not
hidden). Requirements are cross-checked against the proposal in Step 0.

**Systems under test (deployed):**
- Frontend PWA: **https://srh-frontend.vercel.app**
- Backend API: **https://srh-backend-api.onrender.com** (base `/api/v1`)
- ML artifacts: `srh-backend-api/models/*.pkl`; held-out data + training notebooks in the
  sibling `srh-ml-model/` repo.

## Prerequisites
```
# Python (backend venv) — ML eval, Locust, API perf
srh-backend-api/venv/Scripts/python.exe   # sklearn, xgboost, pandas, matplotlib, seaborn, locust, requests

# Node — Playwright e2e, bandwidth, web vitals
cd testing && npm install && npx playwright install chromium
```

## Test categories, how to reproduce, where evidence lives

| # | Category | Reproduce | Evidence |
|---|---|---|---|
| 0 | **Requirements traceability** | (read) | `00-traceability/requirements_traceability.md` |
| 1 | **Functional / e2e** (journey + varied data) | `npx playwright test e2e/journey.spec.js e2e/varied-data.spec.js --project=desktop-chromium` ; mobile: `... e2e/mobile.spec.js --project=mobile-android` | `e2e/RESULTS.md`, `e2e/results/evidence/*.png|*.json`, `e2e/results/html/` |
| 2 | **Performance vs budgets** (API latency; web vitals; min spec) | `venv/Scripts/python.exe performance/perf_api.py` ; `node performance/lcp_tti.mjs` | `performance/results/perf_api_results.md`, `performance/results/web_vitals.md` |
| 3 | **Low-bandwidth** (50/10/2 Mbps + Slow 3G) | `node network-bandwidth/bandwidth_throttle.mjs` | `network-bandwidth/results/bandwidth_results.md` (+ `state_*.png`) |
| 4 | **Scalability** (Locust, ≤10 users) | `cd locust && ../../venv/Scripts/python.exe -m locust -f locustfile.py --host <backend> --headless -u 10 -r 2 -t 3m --html results/locust_report.html --csv results/locust` | `locust/RESULTS.md`, `locust/results/locust_report.html`, `*.csv` |
| 5 | **ML accuracy** (efficacy + convergence) | `venv/Scripts/python.exe ml-eval/evaluate_efficacy.py` ; `../srh-ml-model/venv/Scripts/python.exe ml-eval/evaluate_convergence.py` | `ml-eval/results/efficacy_results.md`, `convergence_notes.md`, `confusion_*.png`, `convergence_*.png` |
| 6 | **Usability + accessibility** | frontend a11y: `cd srh-frontend && npx vitest run src/test` ; usability form ready to administer | `usability/RESULTS.md`, `usability/usability_feedback_form.md` |
| 7 | **Deployment verification** (live end-to-end) | included in `e2e/journey.spec.js` ("deployment is live end-to-end") | `e2e/results/evidence/deployment_evidence.json` + screenshots |

## Headline results (see each RESULTS.md for the full tables)

- **Step 0:** core platform delivered; **gaps disclosed** — sign-language integration (not
  built), in-app pre/post assessment (placeholder), transformer classifiers (replaced by
  TF-IDF+XGBoost), 4-class safety (reduced to binary + output re-check), accessibility
  microservice (built but dormant in prod). Over-deliveries: language-ID model, RW dedicated
  index, voice input, PWA offline shell.
- **Step 1:** all e2e passing; **real finding** — the binary safety classifier
  *over-blocks* a valid question ("How do I use a condom correctly?" → safety fallback);
  off-topic queries are declined safely (no hallucination).
- **Step 2:** chat p95 **4.25 s** (budget 15 s — PASS, 0 errors); health p95 **2.13 s**
  (budget 1 s — **MISS**, attributable to free-tier network RTT + a live DB round-trip);
  1x LCP good (landing 2.11 s, chat 1.42 s). Min spec: 2019-era Android, 2 GB RAM, 2 Mbps.
- **Step 3:** journey **completes at every bandwidth** (50/10/2 Mbps + Slow 3G); shell load
  3.0 s → 5.1 s at Slow 3G; loading spinner keeps a cold start distinguishable from a hang.
- **Step 4:** **stable at 10 concurrent users, 0.00% errors**; chat p95 2.8 s.
- **Step 5:** safety F1 and language F1 **match recorded baselines exactly** (no version
  drift); topic accuracy matches, macro-F1 gap explained by n=7 minority-class support;
  all three models **converge** (curves saved).
- **Step 6:** jest-axe **0 violations** (9 assertions / 5 suites); manual NVDA/TalkBack
  checklist + moderated-session form ready (human step pending).

## Constraints honoured
- No application logic was modified to make a test pass; degraded behaviour is reported.
- Load testing was capped at **10 concurrent users** against production (no re-authorisation
  was requested to exceed it).
