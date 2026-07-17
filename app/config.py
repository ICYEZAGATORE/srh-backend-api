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

    # ── RAG: Kinyarwanda embedder (English path above is UNCHANGED) ──────────
    # The English MiniLM embedder (EMBEDDING_MODEL, 384-d) discriminates
    # Kinyarwanda poorly. bge-m3 (1024-d, built for 100+ languages incl.
    # low-resource) is far better for rw retrieval (validated). Its dimension
    # differs from the English index, so rw vectors live in a SEPARATE Pinecone
    # index and rw queries are embedded + searched via this model. Both models
    # run under the same EMBEDDING_BACKEND (hf_api on Render; both are served by
    # the HF feature-extraction API).
    RW_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RW_EMBEDDING_DIM: int = 1024
    RW_PINECONE_INDEX_NAME: str = "srh-knowledge-base-rw"

    # ── Kinyarwanda pipeline mode (English path is UNCHANGED) ────────────────
    # Selects how Kinyarwanda (rw) queries are answered AFTER the FAQ cache:
    #   "native"    — CURRENT behaviour: bge-m3 retrieval on the rw index +
    #                 direct Kinyarwanda generation by the LLM (default; no
    #                 behaviour change unless this flag is flipped).
    #   "translate" — rw→en→(English RAG + generation)→en→rw. Reuses the English
    #                 path so rw benefits from the richer English KB. Requires a
    #                 working TRANSLATION_PROVIDER; on any failure it falls back
    #                 to the "native" path (never a hard error to the user).
    # English (en) queries never consult this flag.
    KINYARWANDA_PIPELINE_MODE: str = "native"

    @field_validator("KINYARWANDA_PIPELINE_MODE")
    @classmethod
    def _valid_rw_mode(cls, v: str) -> str:
        v = (v or "native").strip().lower()
        return v if v in ("native", "translate") else "native"

    # ── FAQ cache (predefined Kinyarwanda Q&A; runs before RAG for rw) ───────
    # A high-similarity lookup against curated rw question/answer pairs. On a
    # near-duplicate hit the pre-approved answer is returned verbatim, skipping
    # translation + LLM generation. Built offline by scripts/build_faq_cache.py
    # into FAQ_CACHE_PATH (embeddings precomputed to avoid a startup embed storm
    # on the free tier). Threshold is intentionally high — this must be a
    # paraphrase/near-duplicate match, not a topic match. Tune after seeing real
    # hit rates. Missing file / any error => cache is a no-op (never raises).
    FAQ_CACHE_ENABLED: bool = True
    FAQ_SIMILARITY_THRESHOLD: float = 0.90
    FAQ_CACHE_PATH: str = "data/faq_cache_rw.jsonl"

    # ── Translation provider (used only by KINYARWANDA_PIPELINE_MODE=translate)
    # Provider-agnostic adapters live in app/services/translation.py. Adapters
    # stay switchable; the offline harness (srh-ml-model) picks the winner.
    #   "google" | "nllb" | "digital_umuganda" | "none"
    TRANSLATION_PROVIDER: str = "google"
    TRANSLATION_TIMEOUT_SECONDS: int = 10
    # Back-translation QA: rw response is translated back to en and compared to
    # the English-generated response. Below this cosine similarity the response
    # is FLAGGED (low_confidence_translation) for later review — not blocked.
    BACK_TRANSLATION_SIMILARITY_THRESHOLD: float = 0.75
    # Provider credentials / endpoints (blank defaults; set via env, never hardcode).
    GOOGLE_TRANSLATE_API_KEY: str = ""
    # A hosted/managed NLLB-200 endpoint (e.g. an HF Inference Endpoint URL).
    # Local GPU inference is NOT viable on the Render free tier, so NLLB is only
    # usable here when a hosted endpoint is configured.
    NLLB_ENDPOINT_URL: str = ""
    # Digital Umuganda's published Kinyarwanda MT model id on HuggingFace, if any.
    DIGITAL_UMUGANDA_MODEL_ID: str = ""

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
