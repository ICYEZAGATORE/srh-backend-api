"""tests/test_health.py — readiness probe."""


def test_health_ok(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "timestamp" in body
    # Readiness reports its components, not just a bare status.
    assert body["components"]["database"] == "ok"
    assert set(body["components"]["models"]) == {"safety", "topic", "language"}


def test_health_unavailable_when_models_missing(client, monkeypatch):
    # Simulate a broken deploy (artifacts absent): readiness must go 503, not
    # stay trivially green.
    import app.routers.health as health_module

    monkeypatch.setattr(
        health_module,
        "warmup",
        lambda: {"safety": False, "topic": False, "language": False},
    )
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unavailable"
