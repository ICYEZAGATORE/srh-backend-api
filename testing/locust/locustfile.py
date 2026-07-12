"""
Step 4 — Scalability / concurrent-user load test (Locust), capped at 10 users.

Simulates a realistic anonymous SRH chat session against the DEPLOYED backend:
    on_start:  POST /api/v1/session/start        (obtain a session_id)
    task:      POST /api/v1/chat                  (ask an SRH question)
               ... think-time ...  repeat
plus an occasional health poll, mirroring how the frontend behaves.

CAP: run at a MAXIMUM of 10 concurrent users (-u 10). This is a deliberate limit
to gather real production evidence without risking a free-tier outage. Do NOT
exceed 10 against production without explicit re-authorisation. Higher-concurrency
breaking-point testing belongs on a local/staging replica (see README, "next steps").

Reproduce (headless, 10 users, ~5 min, save HTML + CSV):
    cd testing/locust
    ../../venv/Scripts/python.exe -m locust -f locustfile.py \
        --host https://srh-backend-api.onrender.com \
        --headless -u 10 -r 1 -t 5m \
        --html results/locust_report.html --csv results/locust

Note: the free tier cold-starts (~62 s) on the first request after idle; the first
few samples will show that latency. Interpret p50 (warm) separately from max (cold).
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

# One realistic SRH question per topic (safe, English) — the load test exercises
# the full RAG+LLM path, not a trivial echo endpoint.
QUESTIONS = [
    "How do I use a condom correctly?",
    "What are the symptoms of an STI?",
    "How soon can I take a pregnancy test?",
    "What changes happen during puberty?",
    "What does consent mean in a relationship?",
    "Where can I get contraception near me?",
    "Is it normal to have irregular periods?",
    "How is HIV transmitted and prevented?",
]


class SRHChatUser(HttpUser):
    # Human-like think time between messages (read the answer, type the next one).
    wait_time = between(3, 8)
    session_id: str | None = None

    def on_start(self) -> None:
        """Start an anonymous session, mirroring the consent → chat entry flow."""
        with self.client.post("/api/v1/session/start", name="POST /session/start",
                              catch_response=True) as resp:
            if resp.status_code == 200:
                try:
                    self.session_id = resp.json().get("session_id")
                    resp.success()
                except Exception as exc:  # noqa: BLE001
                    resp.failure(f"bad session json: {exc}")
            else:
                resp.failure(f"session start {resp.status_code}")

    @task(10)
    def ask_question(self) -> None:
        if not self.session_id:
            self.on_start()
            if not self.session_id:
                return
        payload = {
            "session_id": self.session_id,
            "message": random.choice(QUESTIONS),
            "lang": "en",
        }
        # Generous timeout: the LLM leg is the slow part; we still want to record it
        # rather than abort, so the p95/p99/max reflect real end-to-end latency.
        with self.client.post("/api/v1/chat", json=payload, name="POST /chat",
                              catch_response=True, timeout=120) as resp:
            if resp.status_code != 200:
                resp.failure(f"chat {resp.status_code}")
                return
            try:
                body = resp.json()
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"chat non-json: {exc}")
                return
            # A 200 with neither an answer nor a fallback is a functional failure.
            if not body.get("response") and not body.get("fallback_message"):
                resp.failure("200 but empty response+fallback")
            else:
                resp.success()

    @task(1)
    def health(self) -> None:
        self.client.get("/api/v1/health", name="GET /health")
