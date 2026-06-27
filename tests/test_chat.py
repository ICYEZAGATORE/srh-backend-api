"""tests/test_chat.py — core chat pipeline (safe + unsafe paths)."""

import app.routers.chat as chat_module


def _new_session(client) -> str:
    return client.post("/api/v1/session/start").json()["session_id"]


def test_safe_message_returns_response(client):
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
    assert body["response"] is not None
    assert body["topic"] is not None


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
