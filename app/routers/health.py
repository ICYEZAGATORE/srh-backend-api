"""
app/routers/health.py — Liveness / readiness probe.

``/health`` is a real readiness check, not a trivially-green stub: it verifies
(1) database connectivity and (2) that the trained ML classifiers actually load
from disk. If either fails the endpoint returns HTTP 503 so a broken deploy
(e.g. missing ``.pkl`` artifacts, or an unreachable DB) is visible to Render's
health check and to operators, instead of reporting "ok" while /chat is broken.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from app.database import get_db
from app.ml.model_registry import warmup

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(response: Response, db: SASession = Depends(get_db)) -> dict:
    components: dict = {}
    ready = True

    # 1) Database connectivity.
    try:
        db.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        components["database"] = f"error: {type(exc).__name__}"
        ready = False

    # 2) ML classifiers actually load (small sklearn pipelines; does NOT load the
    #    embedding model / torch, so this stays cheap and memory-safe).
    models = warmup()  # {"safety": bool, "topic": bool, "language": bool}
    components["models"] = models
    if not all(models.values()):
        ready = False

    if not ready:
        response.status_code = 503

    return {
        "status": "ok" if ready else "unavailable",
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
