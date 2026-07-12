"""
Step 2 — API performance vs explicit, pre-declared budgets (single-user latency).

Complements the Locust concurrent test (Step 4): here we measure warm single-user
latency percentiles for the two endpoints that matter, against budgets set BEFORE
running and grounded in the known constraints (Render free tier, 512 MB, ~62 s cold
start, HF-hosted LLM leg).

PRE-DECLARED BUDGETS
  health : p95 <= 1000 ms warm ; cold start <= 90 s ; error rate 0%
  chat   : p95 <= 15000 ms warm ; error rate <= 5% ; timeout (>120 s) rate 0%
           (chat is LLM+RAG-bound; the budget reflects a free-tier HF inference leg,
            not an arbitrary target)

Metrics: p50 / p95 / p99, min, max, mean, throughput (req/s), error rate, timeout
rate. Reproduce:
    venv/Scripts/python.exe testing/performance/perf_api.py
Outputs: testing/performance/results/perf_api_results.md (+ .json)
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import requests

BASE = "https://srh-backend-api.onrender.com/api/v1"
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(parents=True, exist_ok=True)

N_HEALTH = 30
N_CHAT = 20
QUESTIONS = [
    "How do I use a condom correctly?", "What are the symptoms of an STI?",
    "How soon can I take a pregnancy test?", "What changes happen during puberty?",
    "What does consent mean?", "Where can I get contraception?",
]
BUDGETS = {"health_p95_ms": 1000, "chat_p95_ms": 15000,
           "cold_start_s": 90, "chat_err_rate": 0.05}


def pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def summarize(lat_ms):
    return {
        "n": len(lat_ms),
        "p50_ms": round(pct(lat_ms, 50)), "p95_ms": round(pct(lat_ms, 95)),
        "p99_ms": round(pct(lat_ms, 99)), "min_ms": round(min(lat_ms)),
        "max_ms": round(max(lat_ms)), "mean_ms": round(sum(lat_ms) / len(lat_ms)),
    }


def measure(kind: str):
    lat, errors, timeouts = [], 0, 0
    sid = None
    if kind == "chat":
        r = requests.post(f"{BASE}/session/start", timeout=90)
        sid = r.json().get("session_id")
    n = N_CHAT if kind == "chat" else N_HEALTH
    t_wall = time.time()
    for _ in range(n):
        t0 = time.time()
        try:
            if kind == "health":
                resp = requests.get(f"{BASE}/health", timeout=95)
            else:
                resp = requests.post(f"{BASE}/chat", timeout=120, json={
                    "session_id": sid, "message": random.choice(QUESTIONS), "lang": "en"})
            lat.append((time.time() - t0) * 1000)
            ok = resp.status_code == 200
            if kind == "chat" and ok:
                b = resp.json()
                ok = bool(b.get("response") or b.get("fallback_message"))
            if not ok:
                errors += 1
        except requests.Timeout:
            timeouts += 1
            errors += 1
            lat.append((time.time() - t0) * 1000)
        except Exception:
            errors += 1
    wall = time.time() - t_wall
    s = summarize(lat)
    s.update(errors=errors, timeouts=timeouts,
             error_rate=round(errors / n, 3), timeout_rate=round(timeouts / n, 3),
             throughput_rps=round(n / wall, 3), cold_start_ms=round(lat[0]))
    return s


def main():
    print("Measuring health ..."); health = measure("health")
    print("Measuring chat (real LLM path; sequential) ..."); chat = measure("chat")
    res = {"base": BASE, "budgets": BUDGETS, "health": health, "chat": chat}
    (OUT / "perf_api_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    def verdict(val, budget):
        return "PASS" if val <= budget else "MISS"

    cold_s = round(max(health["cold_start_ms"], chat["cold_start_ms"]) / 1000, 1)
    md = [
        "# Step 2 — API performance vs budgets (single-user, warm)", "",
        f"Target: `{BASE}`  ·  health n={health['n']}, chat n={chat['n']}", "",
        "| endpoint | p50 | p95 | p99 | min | max | mean | throughput | err | timeout |",
        "|---|---|---|---|---|---|---|---|---|---|",
        f"| GET /health | {health['p50_ms']} | {health['p95_ms']} | {health['p99_ms']} | "
        f"{health['min_ms']} | {health['max_ms']} | {health['mean_ms']} | "
        f"{health['throughput_rps']}/s | {health['error_rate']} | {health['timeout_rate']} |",
        f"| POST /chat | {chat['p50_ms']} | {chat['p95_ms']} | {chat['p99_ms']} | "
        f"{chat['min_ms']} | {chat['max_ms']} | {chat['mean_ms']} | "
        f"{chat['throughput_rps']}/s | {chat['error_rate']} | {chat['timeout_rate']} |",
        "*(all latencies in ms)*", "",
        "## Budget check", "",
        "| budget | target | measured | verdict |", "|---|---|---|---|",
        f"| health p95 | <= {BUDGETS['health_p95_ms']} ms | {health['p95_ms']} ms | "
        f"{verdict(health['p95_ms'], BUDGETS['health_p95_ms'])} |",
        f"| chat p95 | <= {BUDGETS['chat_p95_ms']} ms | {chat['p95_ms']} ms | "
        f"{verdict(chat['p95_ms'], BUDGETS['chat_p95_ms'])} |",
        f"| chat error rate | <= {BUDGETS['chat_err_rate']} | {chat['error_rate']} | "
        f"{verdict(chat['error_rate'], BUDGETS['chat_err_rate'])} |",
        f"| first-request (cold) | <= {BUDGETS['cold_start_s']} s | {cold_s} s | "
        f"{verdict(cold_s, BUDGETS['cold_start_s'])} |",
        "",
        "> First-request latency includes any cold start. Compare p50 (warm) against "
        "max (possible cold) to distinguish a cold start from a hang.",
    ]
    (OUT / "perf_api_results.md").write_text("\n".join(md), encoding="utf-8")
    print(f"health p95={health['p95_ms']}ms  chat p50={chat['p50_ms']}ms "
          f"p95={chat['p95_ms']}ms err={chat['error_rate']} timeouts={chat['timeouts']}")
    print(f"Wrote {OUT/'perf_api_results.md'}")


if __name__ == "__main__":
    main()
