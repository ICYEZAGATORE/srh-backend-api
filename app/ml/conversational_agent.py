"""
app/ml/conversational_agent.py — RAG + LLM response generation.

Role in the RAG pipeline
------------------------
``SRHConversationalAgent`` turns a (safety-cleared) user query into a grounded,
safety-constrained answer:

  embed+retrieve (via retrieve_context) → build the safety system prompt →
  call the LLM (HuggingFace Inference API) → strip prompt/context leakage →
  enforce max length → return {response_text, retrieved_chunks,
  confidence_score, language}.

``generate_response(...)`` is kept as the STABLE, router-facing function (same
positional signature as the original stub, plus additive optional ``topic`` /
``session_id`` / ``db``). It delegates to the agent and returns the answer
string, so the chat router needs no structural change.

Safety behaviour
----------------
- The exact safety-constrained system prompt below is always used.
- If the LLM call fails or times out, the bilingual safe fallback from
  ``app/services/moderation.py`` is returned instead.
- The system prompt and retrieved chunk text are never echoed in the output.

Runtime dependencies
--------------------
- ``HF_API_TOKEN`` + a HuggingFace-hosted instruct model (``LLM_MODEL``).
- The embedding model + vector store (via ``retrieve_context``).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.config import settings
from app.ml.embeddings import retrieve_context
from app.services.moderation import get_fallback

logger = logging.getLogger(__name__)

_LANG_NAME = {"en": "English", "rw": "Kinyarwanda"}
MIN_CHUNKS = 3
TOP_K = 5

# ── Safety-constrained system prompt (Part 4.3 — use exactly) ───────────────
SYSTEM_PROMPT_TEMPLATE = """You are an SRH (Sexual and Reproductive Health) education assistant for
teenagers and persons with disabilities in Rwanda. You provide accurate,
age-appropriate, non-judgmental health information in {language}.

You ONLY answer questions using the verified health information provided
below. If the answer is not in the provided information, say:
"I don't have specific information on that. Please speak with a qualified
health worker or call the Rwanda health hotline at 114."

You NEVER provide medical diagnoses, prescriptions, or emergency guidance.
For any emergency, always refer the user to emergency services (112 in Rwanda).
For abuse or GBV disclosures, always provide the Isange One Stop Centre
contact: +250 788 389 547.

Verified SRH Information:
{retrieved_context}

Conversation history:
{chat_history}

User question: {user_query}

Respond in {language}. Be clear, kind, and age-appropriate."""


def _recent_history(db, session_id, limit: int = 5) -> List[dict]:
    """Return the last ``limit`` (user, assistant) turns for a session."""
    if db is None or not session_id:
        return []
    try:
        from app.models.query import Query

        rows = (
            db.query(Query)
            .filter(Query.session_id == session_id, Query.response.isnot(None))
            .order_by(Query.created_at.desc())
            .limit(limit)
            .all()
        )
        return [{"user": r.text or "", "assistant": r.response or ""}
                for r in reversed(rows)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("history lookup failed: %s", exc)
        return []


class SRHConversationalAgent:
    """LangChain-style RAG agent over the SRH knowledge base."""

    def __init__(self, model_id: Optional[str] = None) -> None:
        self.model_id = model_id or settings.LLM_MODEL
        self._client = None

    # ── LLM transport (mockable in tests) ───────────────────────────────────
    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient

            self._client = InferenceClient(
                model=self.model_id,
                token=settings.HF_API_TOKEN or None,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
        return self._client

    def _call_llm(self, prompt: str) -> str:
        """Call the HF Inference API. Raises on failure/timeout (caught upstream)."""
        if not settings.HF_API_TOKEN:
            # No token configured -> don't attempt a network call; the caller
            # will emit the safe fallback. Keeps tests/offline dev fast.
            raise RuntimeError("HF_API_TOKEN not set; skipping LLM call.")
        client = self._get_client()
        return client.text_generation(
            prompt,
            max_new_tokens=settings.LLM_MAX_NEW_TOKENS,
            temperature=0.3,
            repetition_penalty=1.1,
            return_full_text=False,
        )

    # ── retrieval with broaden fallback (Part 4.3 step 3) ───────────────────
    def _retrieve(self, query: str, lang: str, topic: Optional[str]) -> List[dict]:
        chunks = retrieve_context(query, lang=lang, top_k=TOP_K, topic=topic)
        if len(chunks) < MIN_CHUNKS and topic:
            logger.info("Broadening retrieval: <%d chunks with topic=%s; "
                        "retrying without topic filter.", MIN_CHUNKS, topic)
            chunks = retrieve_context(query, lang=lang, top_k=TOP_K, topic=None)
        return chunks

    # ── output hygiene ──────────────────────────────────────────────────────
    @staticmethod
    def _post_process(text: str, context: str) -> str:
        if not text:
            return ""
        # Strip any leaked prompt scaffolding.
        for marker in ("Verified SRH Information:", "Conversation history:",
                       "User question:", "System:", "You are an SRH"):
            idx = text.find(marker)
            if idx != -1:
                text = text[:idx]
        text = text.strip()
        # Never echo retrieved chunk text verbatim as the whole answer.
        if context and text and text in context:
            return ""
        # Enforce a rough max length (deployed cap ~300 tokens ≈ 320 words).
        words = text.split()
        if len(words) > 320:
            text = " ".join(words[:320]).rstrip() + "…"
        return text

    def generate(
        self,
        user_query: str,
        detected_language: str = "en",
        topic_label: Optional[str] = None,
        session_id: Optional[str] = None,
        context_chunks: Optional[List[dict]] = None,
        simplified: bool = False,
        db=None,
    ) -> dict:
        """Run the full RAG chain and return the structured result."""
        language = _LANG_NAME.get(detected_language, "English")

        chunks = (context_chunks if context_chunks is not None
                  else self._retrieve(user_query, detected_language, topic_label))

        context = "\n\n".join(
            f"- {c.get('text', '')}" for c in chunks if c.get("text")
        ) or "(no verified information retrieved)"
        history = _recent_history(db, session_id)
        history_str = "\n".join(
            f"User: {h['user']}\nAssistant: {h['assistant']}" for h in history
        ) or "(no previous conversation)"

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            language=language,
            retrieved_context=context,
            chat_history=history_str,
            user_query=user_query,
        )
        if simplified:
            prompt += "\n\nUse very simple, short sentences (easy-read)."

        try:
            raw = self._call_llm(prompt)
            response_text = self._post_process(raw, context)
            if not response_text:
                raise ValueError("empty response after post-processing")
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM generation failed (%s); using safe fallback.", exc)
            response_text = get_fallback(detected_language)["fallback_message"]

        scores = [c.get("score", 0.0) for c in chunks if c.get("score") is not None]
        confidence = round(sum(scores) / len(scores), 4) if scores else 0.0

        return {
            "response_text": response_text,
            "retrieved_chunks": chunks,
            "confidence_score": confidence,
            "language": detected_language,
        }


# Module-level singleton so the model client is reused across requests.
_agent: SRHConversationalAgent | None = None


def get_agent() -> SRHConversationalAgent:
    global _agent
    if _agent is None:
        _agent = SRHConversationalAgent()
    return _agent


# ── Router-facing wrapper (STABLE signature; additive optional params) ──────
def generate_response(
    query: str,
    context_chunks: list,
    lang: str,
    simplified: bool = False,
    topic: Optional[str] = None,
    session_id: Optional[str] = None,
    db=None,
) -> str:
    """Generate the assistant's answer string (router contract preserved).

    Delegates to ``SRHConversationalAgent`` and returns only the response text,
    so the existing ``ChatResponse`` schema is unchanged.
    """
    result = get_agent().generate(
        user_query=query,
        detected_language=lang,
        topic_label=topic,
        session_id=session_id,
        context_chunks=context_chunks,
        simplified=simplified,
        db=db,
    )
    return result["response_text"]
