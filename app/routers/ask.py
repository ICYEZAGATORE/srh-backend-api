"""
ask.py — POST /api/v1/ask
The core SRH conversational AI endpoint.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime

from app.services.rag_service import rag_service
from app.routers.auth import get_current_user_optional


router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The user's SRH question in English or Kinyarwanda.",
        examples=["How do condoms protect against HIV?",
                  "Kondomu ikora ite kugira ngo iringanire HIV?"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID to group conversation turns.",
    )
    accessibility_mode: Optional[str] = Field(
        default="standard",
        description="standard | simplified | tts_optimised",
    )


class AskResponse(BaseModel):
    query_id: str = Field(description="Unique ID for this query (for logging).")
    response: str = Field(description="The SRH answer.")
    language: str = Field(description="Detected language: 'en' or 'rw' (from trained classifier).")
    safe: bool = Field(description="Whether the response passed safety checks.")
    latency_ms: int = Field(description="End-to-end latency in milliseconds.")
    topics: list[str] = Field(description="SRH topics retrieved as context.")
    retrieval_scores: list[float] = Field(description="Cosine similarity scores of retrieved chunks.")
    predicted_topic: Optional[str] = Field(
        default=None,
        description="Topic predicted by the trained classifier."
    )
    topic_confidence: Optional[float] = Field(
        default=None,
        description="Confidence of the topic classifier (0-1)."
    )
    unsafe_probability: Optional[float] = Field(
        default=None,
        description="Probability the query was unsafe, from the trained safety classifier."
    )
    blocked_at: Optional[str] = Field(
        default=None,
        description="Pipeline step that blocked the query if applicable: 'query' | 'response' | 'no_context'."
    )
    timestamp: str = Field(description="ISO 8601 response timestamp.")
    disclaimer: str = Field(description="Standard health disclaimer.")


DISCLAIMER_EN = (
    "This information is for educational purposes only. "
    "Please consult a qualified health worker for personal medical advice."
)
DISCLAIMER_RW = (
    "Ibi ni amakuru y'uburezi gusa. "
    "Baza umujyanama w'ubuzima ukenya ku makuru y'ubuvuzi bwite."
)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask an SRH question",
    description=(
        "Submit an SRH question in English or Kinyarwanda. The pipeline routes the query "
        "through three trained classifiers (language → safety → topic), retrieves relevant "
        "SRH context from FAISS, generates a response using the configured LLM, and re-checks "
        "the response for safety before returning."
    ),
    responses={
        200: {"description": "Successful SRH response"},
        400: {"description": "Malformed query"},
        503: {"description": "RAG pipeline not ready"},
    },
)
async def ask_srh_question(
    body: AskRequest,
    current_user=Depends(get_current_user_optional),
):
    try:
        result = await rag_service.query(body.query)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"RAG pipeline not ready: {str(e)}. Run the ML notebooks first.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {str(e)}",
        )

    lang = result.get("language", "en")
    disclaimer = DISCLAIMER_RW if lang == "rw" else DISCLAIMER_EN

    return AskResponse(
        query_id=str(uuid.uuid4()),
        response=result["response"],
        language=lang,
        safe=result["safe"],
        latency_ms=result.get("latency_ms", 0),
        topics=result.get("topics", []),
        retrieval_scores=result.get("retrieval_scores", []),
        predicted_topic=result.get("predicted_topic"),
        topic_confidence=result.get("topic_confidence"),
        unsafe_probability=result.get("unsafe_probability"),
        blocked_at=result.get("blocked_at"),
        timestamp=datetime.utcnow().isoformat() + "Z",
        disclaimer=disclaimer,
    )
