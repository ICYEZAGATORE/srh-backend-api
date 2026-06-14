"""
config.py — Settings loaded from environment variables (typed + validated).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "dev-secret-change-in-production"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://srh_user:srh_pass@localhost:5432/srh_db"

    # ── LLM providers (free Groq is default; OpenAI is migration target) ──────
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # ── ML artefacts (paths relative to project root) ─────────────────────────
    FAISS_INDEX_PATH: str = "../srh-ml-model/data/srh_faiss.index"
    CHUNKS_CSV_PATH: str = "../srh-ml-model/data/embeddings_cache/chunks_with_text.csv"
    ML_SRC_PATH: str = "../srh-ml-model/src"
    MODELS_TRAINED_PATH: str = "../srh-ml-model/models_trained"

    # ── Auth (JWT) ────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
