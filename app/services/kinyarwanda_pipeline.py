"""
app/services/kinyarwanda_pipeline.py — Kinyarwanda (rw) request orchestrator.

Runs the rw-specific answer strategies that sit in FRONT of the shared
RAG/generation steps. Invoked by ``app/routers/chat.py`` for rw queries only,
AFTER input safety + logging + the UNSAFE short-circuit — so the English path
never reaches this module and stays byte-for-byte unchanged.

Two strategies, in order:

1. **FAQ cache** (``FAQ_CACHE_ENABLED``): a near-duplicate rw question returns a
   curated ``answer_rw`` verbatim, skipping translation and generation.

2. **Translate pipeline** (only when ``KINYARWANDA_PIPELINE_MODE=translate`` and
   the FAQ misses): rw→en, then the EXISTING English topic/retrieval/generation
   functions are called *by literal reuse* on the English text, output-side
   safety is re-checked on the English response, then en→rw. A back-translation
   QA check flags (never blocks) low-confidence results.

Contract with the router
-------------------------
``handle_kinyarwanda_query(...)`` returns:
  - an :class:`RwResult` when this module produced the answer (or an output-side
    safety block) — the router persists it and returns; or
  - ``None`` to mean "fall through to the existing shared RAG steps" — i.e. the
    native rw path (bge-m3 retrieval + direct rw generation). This happens on a
    FAQ miss in ``native`` mode, and on ANY translate-pipeline failure/timeout,
    so a translation-layer problem degrades gracefully to current behaviour and
    never raises a 500.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

SAFETY_UNSAFE = 1


@dataclass
class RwResult:
    """Outcome of the rw orchestrator for the router to persist + return."""

    response_text: Optional[str]
    topic: Optional[str]
    pipeline_mode: str  # "faq" | "translate"
    faq_cache_hit: bool = False
    low_confidence_translation: bool = False
    unreviewed: bool = False  # FAQ answer served from an unapproved row
    unsafe: bool = False  # output-side safety blocked it -> router returns fallback


def handle_kinyarwanda_query(
    message: str,
    simplified: bool = False,
    session_id: Optional[str] = None,
    db=None,
) -> Optional[RwResult]:
    """Try the FAQ cache, then (in translate mode) the translation pipeline.

    Returns an :class:`RwResult`, or ``None`` to fall through to the native path.
    """
    # ── 1. FAQ cache ─────────────────────────────────────────────────────────
    if settings.FAQ_CACHE_ENABLED:
        result = _try_faq_cache(message)
        if result is not None:
            return result

    # ── 2. Translate pipeline (feature-flagged) ──────────────────────────────
    if settings.KINYARWANDA_PIPELINE_MODE == "translate":
        return _run_translate_pipeline(message, simplified, session_id, db)

    # native mode + FAQ miss -> let the router run the existing rw path.
    return None


# ── FAQ cache ───────────────────────────────────────────────────────────────
def _try_faq_cache(message: str) -> Optional[RwResult]:
    from app.services.faq_cache import get_faq_cache

    hit = get_faq_cache().lookup(message)
    if hit is None:
        return None

    from app.ml.safety_classifier import classify_response_safety

    # Even a pre-approved answer passes the output-side rule filter — a
    # mis-detected catastrophic case is a safety decision, not a retrieval one.
    if classify_response_safety(hit["answer_rw"]).get("label") == SAFETY_UNSAFE:
        logger.warning("FAQ cache hit blocked by output-side safety filter.")
        return RwResult(
            response_text=None, topic=hit.get("topic"), pipeline_mode="faq",
            faq_cache_hit=True, unsafe=True,
        )

    unreviewed = not hit.get("approved", False)
    logger.info(
        "FAQ cache served rw response (score=%.4f, topic=%s, approved=%s).",
        hit["score"], hit.get("topic"), hit.get("approved"),
    )
    if unreviewed:
        logger.warning(
            "FAQ answer served from an UNREVIEWED row (approved=false); "
            "flagged low-confidence for later clinical review."
        )
    return RwResult(
        response_text=hit["answer_rw"],
        topic=hit.get("topic"),
        pipeline_mode="faq",
        faq_cache_hit=True,
        unreviewed=unreviewed,
    )


# ── Translate pipeline ──────────────────────────────────────────────────────
def _run_translate_pipeline(
    message: str, simplified: bool, session_id: Optional[str], db
) -> Optional[RwResult]:
    """rw→en→(English RAG+gen)→en→rw, with output safety + back-translation QA.

    Any failure/timeout returns ``None`` so the router falls back to native rw.
    """
    from app.ml.conversational_agent import generate_response
    from app.ml.embeddings import retrieve_context
    from app.ml.safety_classifier import classify_response_safety
    from app.ml.topic_classifier import classify_topic
    from app.services.translation import TranslationError, translate

    try:
        # 1. rw -> en
        english_query = translate(message, "rw", "en")
        if not english_query:
            raise TranslationError("empty English translation of the query")

        # 2-4. Reuse the EXISTING English path, literally, on the English text.
        topic = classify_topic(english_query).get("topic")
        context_chunks = retrieve_context(english_query, "en", topic=topic)
        english_response = generate_response(
            english_query, context_chunks, "en", simplified,
            topic=topic, session_id=session_id, db=db,
        )

        # 5. Output-side safety re-check on the ENGLISH response (existing filter).
        if classify_response_safety(english_response).get("label") == SAFETY_UNSAFE:
            logger.warning("Translate-pipeline English response blocked by safety filter.")
            return RwResult(
                response_text=None, topic=topic, pipeline_mode="translate", unsafe=True,
            )

        # 6. en -> rw
        rw_response = translate(english_response, "en", "rw")
        if not rw_response:
            raise TranslationError("empty Kinyarwanda translation of the response")

    except TranslationError as exc:
        logger.warning(
            "Translate pipeline failed (%s); falling back to native rw path.", exc
        )
        return None
    except Exception as exc:  # noqa: BLE001 - never surface a 500 from this layer
        logger.warning(
            "Translate pipeline error (%s); falling back to native rw path.", exc
        )
        return None

    # 7. Back-translation QA (flag, don't block).
    low_conf = _back_translation_low_confidence(english_response, rw_response)
    return RwResult(
        response_text=rw_response,
        topic=topic,
        pipeline_mode="translate",
        low_confidence_translation=low_conf,
    )


def _back_translation_low_confidence(english_response: str, rw_response: str) -> bool:
    """True if rw→en round-trip diverges from the English response (flag only).

    Reuses the English embedder for the similarity check. Any failure returns
    ``False`` (do not flag on our own error).
    """
    try:
        from app.services.translation import translate

        back = translate(rw_response, "rw", "en")
        if not back:
            return False

        import numpy as np

        from app.ml.embeddings import get_embedding_model

        emb = get_embedding_model()
        a = np.asarray(emb.embed_query(english_response), dtype="float32")
        b = np.asarray(emb.embed_query(back), dtype="float32")
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return False
        sim = float(a @ b / (na * nb))
        low = sim < settings.BACK_TRANSLATION_SIMILARITY_THRESHOLD
        logger.info(
            "Back-translation similarity=%.4f (threshold=%.2f) -> low_confidence=%s",
            sim, settings.BACK_TRANSLATION_SIMILARITY_THRESHOLD, low,
        )
        return low
    except Exception as exc:  # noqa: BLE001
        logger.warning("Back-translation QA skipped (%s).", exc)
        return False
