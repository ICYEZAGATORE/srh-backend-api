"""
app/core/config.py
─────────────────
Centralised settings loaded from environment variables / .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = "postgresql://srh_user:password@localhost:5432/srh_db"

    # ── JWT ──────────────────────────────────────────────
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Admin seeding ─────────────────────────────────────
    FIRST_ADMIN_EMAIL: str = "admin@srh-platform.rw"
    FIRST_ADMIN_PASSWORD: str = "Admin@SRH2025!"

    # ── CORS ─────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ── App ──────────────────────────────────────────────
    APP_ENV: str = "development"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
