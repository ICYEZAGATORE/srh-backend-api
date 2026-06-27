"""
app/routers/session.py — Anonymous session management.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SASession

from app.database import get_db
from app.services.session_service import create_session

router = APIRouter(prefix="/session", tags=["Session"])


@router.post("/start")
def start_session(db: SASession = Depends(get_db)) -> dict:
    """Create a new anonymous session and return its UUID."""
    session = create_session(db)
    return {"session_id": str(session.id)}
