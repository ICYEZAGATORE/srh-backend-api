"""
app/routers/admin.py — Protected admin endpoints.

Every route requires a bearer token equal to the ADMIN_API_KEY env var. The
token is verified (via the ``require_admin`` dependency) BEFORE any handler
logic runs.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SASession

from app.config import settings
from app.database import get_db
from app.models.query import Query

router = APIRouter(prefix="/admin", tags=["Admin"])

_bearer = HTTPBearer(auto_error=True)


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """Reject the request unless the bearer token matches ADMIN_API_KEY."""
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )


@router.get("/analytics", dependencies=[Depends(require_admin)])
def analytics(db: SASession = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Query)) or 0
    safe = db.scalar(
        select(func.count()).select_from(Query).where(Query.safe.is_(True))
    ) or 0
    unsafe = db.scalar(
        select(func.count()).select_from(Query).where(Query.safe.is_(False))
    ) or 0
    return {
        "total_queries": total,
        "safe_queries": safe,
        "unsafe_queries": unsafe,
    }


@router.post("/knowledge/upload", dependencies=[Depends(require_admin)])
def upload_knowledge() -> dict:
    """Upload new SRH content to the knowledge base. STUB."""
    return {"status": "not yet implemented"}
