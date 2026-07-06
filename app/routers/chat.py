"""
app/routers/chat.py — Core conversational endpoint.

Pipeline order (must not change when real models replace the stubs):
    1. Safety classification (INPUT side — the user query).
    2. Language detection.
    3. Log the query regardless of the result (anonymised audit trail).
    4. If the query is UNSAFE -> fallback response, no downstream processing.
    5. Topic classification.
    6. RAG retrieval + LLM generation.
    7. Safety classification (OUTPUT side — the generated response, per §3.6):
       last line of defence; a flagged generation is replaced with a fallback.
    8. Persist the result.
    9. Return the response.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as SASession

from app.config import settings
from app.database import get_db
from app.ml.conversational_agent import generate_response
from app.ml.embeddings import retrieve_context
from app.ml.language_classifier import detect_language
from app.ml.safety_classifier import classify_safety
from app.ml.topic_classifier import classify_topic
from app.models.query import Query
from app.models.session import Session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.moderation import get_fallback

router = APIRouter(tags=["Chat"])

SAFETY_UNSAFE = 1


def _resolve_session_id(db: SASession, raw: str) -> uuid.UUID | None:
    """Return the session UUID if it is valid and exists, else None.

    Keeps query logging robust during the stub phase: an unknown or malformed
    session_id is logged as NULL rather than raising a foreign-key error.
    """
    try:
        sid = uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None
    exists = db.get(Session, sid) is not None
    return sid if exists else None


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: SASession = Depends(get_db)) -> ChatResponse:
    # 1. Safety check — always runs first.
    safety = classify_safety(request.message)
    is_unsafe = safety.get("label") == SAFETY_UNSAFE

    # 2. Language detection (proxy stub until the trained model is swapped in).
    #    The detected language flows through retrieval + generation. We keep the
    #    client-declared `lang` for the response contract, but prefer the
    #    detected language for the RAG pipeline.
    detected = detect_language(request.message, hint=request.lang)
    detected_lang = detected.get("language", request.lang)

    session_id = _resolve_session_id(db, request.session_id)

    # 3. Log the query regardless of safety result. For UNSAFE queries the raw
    #    text is discarded unless LOG_UNSAFE_TEXT is enabled (privacy default).
    store_text = request.message
    if is_unsafe and not settings.LOG_UNSAFE_TEXT:
        store_text = None

    query = Query(
        session_id=session_id,
        text=store_text,
        lang=detected_lang,
        safe=not is_unsafe,
        fallback=False,
    )
    db.add(query)
    db.commit()
    db.refresh(query)

    # 3. UNSAFE -> short-circuit with a fallback + referral; no model calls.
    if is_unsafe:
        query.safe = False
        query.fallback = True
        db.commit()

        fb = get_fallback(request.lang)
        return ChatResponse(
            response=None,
            safe=False,
            topic=None,
            lang=request.lang,
            fallback=True,
            fallback_message=fb["fallback_message"],
            referral=fb["referral"],
        )

    # 4. Topic classification.
    topic_result = classify_topic(request.message)
    topic = topic_result.get("topic")

    # 5. RAG retrieval + LLM generation (filtered by detected language + topic).
    context_chunks = retrieve_context(request.message, detected_lang, topic=topic)
    response_text = generate_response(
        request.message,
        context_chunks,
        detected_lang,
        request.simplified,
        topic=topic,
        session_id=str(session_id) if session_id else None,
        db=db,
    )

    # 7. Output-side safety check (§3.6) — re-run the safety classifier on the
    #    generated response. This is the last line of defence against a bad
    #    generation; a flagged response is never returned to the user.
    response_safety = classify_safety(response_text)
    if response_safety.get("label") == SAFETY_UNSAFE:
        query.safe = False
        query.topic = topic
        query.response = None  # do not persist the unsafe generation
        query.fallback = True
        db.commit()

        fb = get_fallback(request.lang)
        return ChatResponse(
            response=None,
            safe=False,
            topic=topic,
            lang=request.lang,
            fallback=True,
            fallback_message=fb["fallback_message"],
            referral=fb["referral"],
        )

    # 8. Persist the result.
    query.safe = True
    query.topic = topic
    query.response = response_text
    query.fallback = False
    db.commit()

    # 9. Return.
    return ChatResponse(
        response=response_text,
        safe=True,
        topic=topic,
        lang=request.lang,
        fallback=False,
        fallback_message=None,
        referral=None,
    )
