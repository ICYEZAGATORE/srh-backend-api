"""
app/config.py — Application settings loaded from environment variables.

Uses pydantic-settings so values are typed and validated. A ``.env`` file is
read automatically in local development (see ``.env.example``).
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://srh_user:srh_pass@db:5432/srh_db"

    @field_validator("DATABASE_URL")
    @classmethod
    def _clean_db_url(cls, v: str) -> str:
        # Strip stray whitespace/newlines that can sneak in when pasting the URL
        # into a dashboard env-var field (otherwise the DB name ends up as
        # "srh_db\n"). Also normalize the legacy ``postgres://`` scheme that
        # Render/Heroku emit but SQLAlchemy 2.0 rejects.
        v = v.strip()
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        return v

    # ── Admin ───────────────────────────────────────────────────────────────
    # Bearer token required by /api/v1/admin/* endpoints.
    ADMIN_API_KEY: str = "change-me-in-production"

    # ── App ─────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── Privacy ─────────────────────────────────────────────────────────────
    # When False, the raw text of UNSAFE queries is discarded before storage;
    # only the safety label/flag is kept for auditing. Safe queries are always
    # stored as anonymised text (no user identity is ever linked — see models).
    LOG_UNSAFE_TEXT: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
