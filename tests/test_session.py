"""tests/test_session.py — anonymous session creation."""

import uuid


def test_start_session_returns_valid_uuid(client):
    resp = client.post("/api/v1/session/start")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    # Must be a parseable UUID.
    parsed = uuid.UUID(session_id)
    assert str(parsed) == session_id
