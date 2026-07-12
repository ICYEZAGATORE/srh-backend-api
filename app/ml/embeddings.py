"""
app/ml/embeddings.py — Embedding model + vector-DB retrieval wrapper.

Role in the RAG pipeline
------------------------
Two responsibilities live here:

1. ``SRHEmbeddingModel`` — turns text into 384-dim vectors using
   ``paraphrase-multilingual-MiniLM-L12-v2`` (multilingual; handles Kinyarwanda
   via cross-lingual transfer). Loaded once as a singleton at first use.

2. ``retrieve_context(...)`` — the STABLE, router-facing function (unchanged
   signature, plus an additive optional ``topic`` filter). It embeds the query
   and runs a similarity search against the active vector store, returning the
   top-k SRH knowledge chunks. This is a thin wrapper over ``SRHEmbeddingModel``
   + ``app/services/vector_store.py`` so the router never changes when the real
   model is swapped in.

Runtime dependencies
--------------------
- ``sentence-transformers`` (local inference; downloads the model on first use).
- Optional ``HF_API_TOKEN`` — only used if local load fails and the HF Inference
  API fallback is engaged.
- A vector store (Pinecone or Chroma) via ``get_vector_store()``.
"""

from __future__ import annotations

import logging
import threading
from typing import List

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingUnavailableError(RuntimeError):
    """Raised when neither local nor HF-API embedding is available."""


class SRHEmbeddingModel:
    """Singleton wrapper around the multilingual sentence-transformer.

    Prefers local ``sentence-transformers`` inference. If that cannot be loaded
    (e.g. torch missing) and an ``HF_API_TOKEN`` is set, falls back to the
    HuggingFace Inference API. Never returns a silent empty result — it raises
    ``EmbeddingUnavailableError`` with a clear message instead.
    """

    _instances: "dict[str, SRHEmbeddingModel]" = {}
    _lock = threading.Lock()

    def __init__(self, model_name: str | None = None, dim: int | None = None) -> None:
        self.model_name: str = model_name or settings.EMBEDDING_MODEL
        self.dim: int = dim or settings.EMBEDDING_DIM
        self._backend: str = "uninitialised"
        self._local_model = None
        self._hf_client = None
        self._load()

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def instance(
        cls, model_name: str | None = None, dim: int | None = None
    ) -> "SRHEmbeddingModel":
        """Return a per-model singleton, constructing each distinct model once.

        Keyed by model name so English (MiniLM) and Kinyarwanda (bge-m3) can
        coexist as independent singletons.
        """
        key = model_name or settings.EMBEDDING_MODEL
        inst = cls._instances.get(key)
        if inst is None:
            with cls._lock:
                inst = cls._instances.get(key)
                if inst is None:
                    inst = cls(key, dim)
                    cls._instances[key] = inst
        return inst

    def _load(self) -> None:
        mode = (settings.EMBEDDING_BACKEND or "auto").lower()

        # 1) Local sentence-transformers. Skipped entirely when mode == "hf_api"
        #    so torch is never imported (avoids OOM on the 512 MB Render tier).
        if mode in ("auto", "local"):
            try:
                from sentence_transformers import SentenceTransformer

                self._local_model = SentenceTransformer(self.model_name)
                self._backend = "local"
                logger.info("SRHEmbeddingModel: loaded '%s' locally.", self.model_name)
                return
            except Exception as exc:  # pragma: no cover - depends on env
                if mode == "local":
                    raise EmbeddingUnavailableError(
                        f"EMBEDDING_BACKEND=local but could not load "
                        f"'{self.model_name}': {exc}"
                    ) from exc
                logger.warning("Local embedding load failed (%s); trying HF API.", exc)

        # 2) HuggingFace Inference API (forced when mode == "hf_api", else fallback).
        if settings.HF_API_TOKEN:
            try:
                from huggingface_hub import InferenceClient

                self._hf_client = InferenceClient(
                    model=self._hf_repo_id(), token=settings.HF_API_TOKEN
                )
                self._backend = "hf_api"
                logger.info(
                    "SRHEmbeddingModel: using HF Inference API (%s).", self._hf_repo_id()
                )
                return
            except Exception as exc:  # pragma: no cover
                logger.error("HF Inference API init failed: %s", exc)

        raise EmbeddingUnavailableError(
            "Embedding model unavailable: could not load "
            f"'{self.model_name}' locally and no working HF_API_TOKEN fallback "
            f"(EMBEDDING_BACKEND={mode}). Install sentence-transformers or set "
            "HF_API_TOKEN (and EMBEDDING_BACKEND=hf_api on memory-limited hosts)."
        )

    def _hf_repo_id(self) -> str:
        """Fully-qualified HF repo id for the API path.

        ``SentenceTransformer`` resolves the bare name locally, but the HF
        Inference API needs the full ``sentence-transformers/<name>`` repo id.
        """
        name = self.model_name
        return name if "/" in name else f"sentence-transformers/{name}"

    # ── public API (Part 4.1 contract) ──────────────────────────────────────
    @property
    def backend(self) -> str:
        return self._backend

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string into a 384-dim vector."""
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts into 384-dim vectors."""
        if not texts:
            return []
        if self._backend == "local":
            vecs = self._local_model.encode(
                texts, normalize_embeddings=True, convert_to_numpy=True
            )
            return [v.tolist() for v in vecs]
        if self._backend == "hf_api":
            out: List[List[float]] = []
            for t in texts:
                vec = self._hf_client.feature_extraction(t)
                # HF may return nested token embeddings; mean-pool if 2-D.
                out.append(_to_sentence_vector(vec))
            return out
        raise EmbeddingUnavailableError("Embedding backend not initialised.")


def _to_sentence_vector(vec) -> List[float]:
    """Coerce an HF feature-extraction result to a flat sentence vector."""
    import numpy as np

    arr = np.asarray(vec, dtype="float32")
    if arr.ndim == 2:  # token embeddings -> mean pool
        arr = arr.mean(axis=0)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def get_embedding_model() -> SRHEmbeddingModel:
    """Accessor for the English (default) embedding model singleton."""
    return SRHEmbeddingModel.instance()


def get_rw_embedding_model() -> SRHEmbeddingModel:
    """Accessor for the Kinyarwanda embedding model (bge-m3; separate index)."""
    return SRHEmbeddingModel.instance(
        settings.RW_EMBEDDING_MODEL, settings.RW_EMBEDDING_DIM
    )


# ── Router-facing retrieval wrapper (STABLE signature) ──────────────────────
def retrieve_context(
    query: str,
    lang: str = "en",
    top_k: int = 5,
    topic: str | None = None,
) -> list[dict]:
    """Return the top-k SRH knowledge chunks most relevant to ``query``.

    Embeds the query and runs a filtered similarity search against the active
    vector store. Filters on ``lang`` (prefer same-language content) and, when
    provided, ``topic``. Returns chunk dicts shaped as:
        {"entry_id", "topic", "lang", "title", "text", "score"}

    Retrieval failures are swallowed (logged) and return ``[]`` so the chat
    endpoint stays available and the agent can emit its safe fallback.
    """
    try:
        from app.services.vector_store import get_rw_vector_store, get_vector_store

        # Kinyarwanda uses a stronger embedder (bge-m3) + its own index; English
        # keeps the MiniLM embedder + English index. The query embedding and the
        # index MUST use the same model, so route both together by language.
        if lang == "rw":
            emb = get_rw_embedding_model().embed_query(query)
            store = get_rw_vector_store()
        else:
            emb = get_embedding_model().embed_query(query)
            store = get_vector_store()
        flt: dict = {}
        if lang:
            flt["language"] = lang
        # Topic filtering is skipped for Kinyarwanda: the topic classifier is
        # English-trained and mislabels rw queries (in practice almost everything
        # -> "pregnancy"), so filtering by the predicted topic retrieves the WRONG
        # chunks. For rw we rely on language + embedding similarity alone. English
        # keeps topic filtering (the classifier is reliable there).
        if topic and lang != "rw":
            flt["topic"] = topic
        return store.similarity_search(emb, top_k=top_k, filter=flt or None)
    except Exception as exc:  # keep the endpoint resilient
        logger.warning("retrieve_context failed (%s); returning no context.", exc)
        return []
