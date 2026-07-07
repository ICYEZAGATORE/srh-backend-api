"""tests/test_chat.py — core chat pipeline (safe + unsafe paths)."""

import app.routers.chat as chat_module
from app.ml.conversational_agent import SRHConversationalAgent

# A deterministic, non-fallback answer injected at the LLM transport layer so the
# safe-path test asserts on genuinely generated content flowing through the whole
# pipeline (retrieve -> generate -> post-process -> API), not on the safe-fallback
# string. Must not appear in any retrieved context (test KB is empty) so the
# agent's post-processing keeps it verbatim.
_FAKE_ANSWER = (
    "Condoms are a barrier method that help protect against STIs and pregnancy. "
    "You can also speak with a health worker about other options."
)


def _new_session(client) -> str:
    return client.post("/api/v1/session/start").json()["session_id"]


def test_safe_message_returns_generated_answer(client, monkeypatch):
    # Inject a known generation at the transport boundary (the hermetic test env
    # blanks HF_API_TOKEN, so without this the LLM call would fast-fail to the
    # safe fallback). This verifies the router surfaces the *generated* answer.
    monkeypatch.setattr(
        SRHConversationalAgent, "_call_llm", lambda self, prompt: _FAKE_ANSWER
    )

    session_id = _new_session(client)
    resp = client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "message": "How do I protect myself from STIs?",
            "lang": "en",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["safe"] is True
    assert body["fallback"] is False
    assert body["topic"] is not None
    # The real generated content must be surfaced verbatim — not the fallback.
    assert body["response"] == _FAKE_ANSWER


def test_unsafe_message_returns_fallback(client, monkeypatch):
    # The safety classifier is stubbed to always return SAFE, so mock it to
    # return UNSAFE for this test (patch the name bound inside the router).
    monkeypatch.setattr(
        chat_module,
        "classify_safety",
        lambda text: {"label": 1, "score": 0.99},
    )

    session_id = _new_session(client)
    resp = client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "message": "How do I force someone",
            "lang": "en",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["safe"] is False
    assert body["fallback"] is True
    assert body["response"] is None
    assert body["fallback_message"] is not None
    assert body["referral"] is not None
