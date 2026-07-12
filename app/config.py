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

    # ── CORS ────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins. Defaults to local dev
    # origins only — set CORS_ALLOW_ORIGINS to the deployed SRH-FRONTEND origin(s)
    # in production. Never use "*" with credentials (invalid per the CORS spec).
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"

    @property
    def cors_allow_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    # ── Privacy ─────────────────────────────────────────────────────────────
    # When False, the raw text of UNSAFE queries is discarded before storage;
    # only the safety label/flag is kept for auditing. Safe queries are always
    # stored as anonymised text (no user identity is ever linked — see models).
    LOG_UNSAFE_TEXT: bool = False

    # ── Trained classifiers (Models 1–3) ────────────────────────────────────
    # Bare sklearn Pipelines (joblib) copied from the srh-ml-model repo into
    # ./models. Loaded once at startup via app/ml/model_registry.py. If a file
    # is absent the classifier falls back to a safe default (see each module).
    SAFETY_MODEL_PATH: str = "models/safety_classifier.pkl"
    TOPIC_MODEL_PATH: str = "models/topic_classifier_B.pkl"
    LANGUAGE_MODEL_PATH: str = "models/language_classifier.pkl"

    # ── RAG: embeddings ─────────────────────────────────────────────────────
    # Multilingual sentence-transformer (384-dim); handles Kinyarwanda via
    # cross-lingual transfer. Loaded locally as a singleton (see app/ml/embeddings.py).
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384
    # Where embeddings are computed:
    #   "auto"   — try local sentence-transformers, fall back to the HF API.
    #   "hf_api" — force the HF Inference API; NEVER import torch/sentence-
    #              transformers (required on the 512 MB Render tier, where loading
    #              the local model OOMs and 502s the /chat endpoint).
    #   "local"  — force local sentence-transformers.
    EMBEDDING_BACKEND: str = "auto"
    # Optional HuggingFace token (used only if the embedder falls back to the
    # HF Inference API, and by the LLM layer / benchmark).
    HF_API_TOKEN: str = ""

    # ── RAG: vector store ───────────────────────────────────────────────────
    # "pinecone" (cloud) or "chroma" (local dev / CI, no API key required).
    VECTOR_STORE_BACKEND: str = "pinecone"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "srh-knowledge-base"
    # Modern Pinecone serverless spec (the deprecated pod-based
    # PINECONE_ENVIRONMENT is kept below for backward compatibility only).
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    PINECONE_ENVIRONMENT: str = ""  # legacy pod-based indexes only; unused for serverless
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"

    # ── RAG: LLM ────────────────────────────────────────────────────────────
    # HuggingFace model ID for response generation. Update after the Part 5
    # benchmark selects a winner (also exposed as the LLM_MODEL env var).
    # Qwen2.5-7B-Instruct: the Part-5 benchmark's winning family (Qwen), now
    # servable by the HF Inference providers on our token. Replaces
    # Meta-Llama-3-8B-Instruct, which the enabled providers dropped
    # ("model_not_supported"), breaking generation for ALL languages.
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    DEFAULT_LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    LLM_MAX_NEW_TOKENS: int = 300
    LLM_TIMEOUT_SECONDS: int = 30
    # Optional — only used for the GPT-4o reference benchmark (Part 5).
    OPENAI_API_KEY: str = ""

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
