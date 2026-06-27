"""
app/services/session_service.py — Anonymous session handling.

Sessions are random UUIDs with no PII (see README "Security Notes").
"""

from sqlalchemy.orm import Session as SASession

from app.models.session import Session


def create_session(
    db: SASession, lang: str = "en", accessibility_prefs: dict | None = None
) -> Session:
    """Create and persist a new anonymous session, returning the ORM row."""
    session = Session(lang=lang, accessibility_prefs=accessibility_prefs)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
