"""
app/services/faq_cache.py — Predefined-question FAQ cache for Kinyarwanda.

Purpose
-------
Before the RAG/generation pipeline runs for a Kinyarwanda (rw) query, check it
against a curated set of predefined rw question/answer pairs. On a
near-duplicate (high-similarity) match we return the pre-approved ``answer_rw``
verbatim, skipping translation and LLM generation entirely. This gives an
accuracy floor for common questions and sidesteps the known rw-generation
weakness of the LLM.

Data
----
The cache is built OFFLINE by ``scripts/build_faq_cache.py`` into
``settings.FAQ_CACHE_PATH`` (JSONL, one record per line)::

    {"question_rw", "answer_rw", "topic", "approved", "embedding": [float, ...]}

Embeddings are precomputed with the SAME bge-m3 model used for rw retrieval
(``get_rw_embedding_model``) so we never run a 100-call embed storm at startup
on the 512 MB free tier. Only the incoming query is embedded at request time
(one call — the same cost the native path already pays for retrieval).

Robustness
----------
Loading is lazy and defensive: a missing/malformed file, an embedding failure,
or a dimension mismatch all degrade to "no hit" (``lookup`` returns ``None``),
never an exception — so a broken cache can never take down ``/chat``.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class FaqCache:
    """In-memory cosine-similarity lookup over curated rw Q&A pairs."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or settings.FAQ_CACHE_PATH
        self._matrix = None  # np.ndarray (N, dim), L2-normalised
        self._records: List[dict] = []
        self._loaded = False
        self._lock = threading.Lock()

    # ── loading ─────────────────────────────────────────────────────────────
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load()
            self._loaded = True

    def _load(self) -> None:
        import os

        import numpy as np

        if not os.path.exists(self.path):
            logger.warning(
                "FAQ cache file '%s' not found; FAQ cache disabled (no-op).", self.path
            )
            self._records, self._matrix = [], None
            return
        records, vectors = [], []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    emb = row.get("embedding")
                    if not emb or not row.get("answer_rw"):
                        continue
                    records.append(
                        {
                            "question_rw": row.get("question_rw", ""),
                            "answer_rw": row["answer_rw"],
                            "topic": row.get("topic"),
                            "approved": bool(row.get("approved", False)),
                        }
                    )
                    vectors.append(emb)
        except Exception as exc:  # noqa: BLE001 - a bad file must not crash startup
            logger.error("Failed to load FAQ cache '%s': %s", self.path, exc)
            self._records, self._matrix = [], None
            return

        if not vectors:
            logger.warning("FAQ cache '%s' loaded 0 usable rows.", self.path)
            self._records, self._matrix = [], None
            return

        mat = np.asarray(vectors, dtype="float32")
        # Re-normalise defensively so lookups are true cosine via dot product.
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = mat / norms
        self._records = records
        logger.info("FAQ cache loaded: %d rw Q&A pairs from %s", len(records), self.path)

    # ── lookup ────────────────────────────────────────────────────────────────
    def lookup(
        self, query_rw: str, threshold: Optional[float] = None
    ) -> Optional[dict]:
        """Return the best FAQ match for ``query_rw`` or ``None``.

        A hit is returned only if cosine similarity >=
        ``settings.FAQ_SIMILARITY_THRESHOLD`` (override via ``threshold``).
        Result shape: ``{"answer_rw", "topic", "score", "approved",
        "question_rw"}``. Any failure returns ``None`` (never raises).
        """
        if not settings.FAQ_CACHE_ENABLED or not query_rw or not query_rw.strip():
            return None
        thr = settings.FAQ_SIMILARITY_THRESHOLD if threshold is None else threshold
        try:
            self._ensure_loaded()
            if self._matrix is None or not self._records:
                return None

            import numpy as np

            from app.ml.embeddings import get_rw_embedding_model

            q = np.asarray(get_rw_embedding_model().embed_query(query_rw), dtype="float32")
            if q.shape[0] != self._matrix.shape[1]:
                logger.warning(
                    "FAQ cache dim mismatch (query=%d, cache=%d); skipping.",
                    q.shape[0],
                    self._matrix.shape[1],
                )
                return None
            qn = np.linalg.norm(q)
            if qn == 0:
                return None
            q = q / qn
            sims = self._matrix @ q  # cosine, both normalised
            idx = int(sims.argmax())
            score = float(sims[idx])
            if score < thr:
                return None
            rec = self._records[idx]
            return {
                "question_rw": rec["question_rw"],
                "answer_rw": rec["answer_rw"],
                "topic": rec["topic"],
                "approved": rec["approved"],
                "score": round(score, 4),
            }
        except Exception as exc:  # noqa: BLE001 - lookup must never break /chat
            logger.warning("FAQ cache lookup failed (%s); treating as miss.", exc)
            return None


# ── module singleton ────────────────────────────────────────────────────────
_cache: Optional[FaqCache] = None
_singleton_lock = threading.Lock()


def get_faq_cache() -> FaqCache:
    global _cache
    if _cache is None:
        with _singleton_lock:
            if _cache is None:
                _cache = FaqCache()
    return _cache


def reset_faq_cache() -> None:
    """Drop the cached singleton (used by tests to point at a fixture file)."""
    global _cache
    _cache = None
