"""
app/db/init_db.py
──────────────────
Run once at startup:
  1. Creates all tables if they don't exist.
  2. Seeds the first admin account from env variables
     (only if no admin exists yet).
"""
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import Base, engine
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


def create_tables() -> None:
    """Create all ORM-mapped tables. Safe to call repeatedly (no-op if exists)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified / created.")


def seed_first_admin(db: Session) -> None:
    """Seed the first admin from env vars — only if zero admins exist."""
    existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if existing_admin:
        logger.info("Admin account already exists — skipping seed.")
        return

    admin = User(
        email=settings.FIRST_ADMIN_EMAIL,
        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
        full_name="System Administrator",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    db.commit()
    logger.info(f"First admin seeded: {settings.FIRST_ADMIN_EMAIL}")
