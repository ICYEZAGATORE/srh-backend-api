"""
app/schemas/chat.py — Request/response schemas for the /chat endpoint.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Anonymous session UUID.")
    message: str = Field(..., description="The user's SRH question.")
    lang: str = Field(default="en", description="Language code: 'en' or 'rw'.")
    simplified: bool = Field(
        default=False,
        description="Request a simplified/easy-read response (accessibility).",
    )


class ChatResponse(BaseModel):
    response: str | None = None
    safe: bool
    topic: str | None = None
    lang: str
    fallback: bool
    fallback_message: str | None = None
    referral: dict | None = None
