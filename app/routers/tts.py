"""
app/routers/tts.py — Text-to-speech endpoint (stub).
"""

from fastapi import APIRouter

from app.schemas.tts import TTSRequest
from app.services.tts_service import synthesize

router = APIRouter(tags=["TTS"])


@router.post("/tts")
def tts(request: TTSRequest) -> dict:
    """Synthesise speech. STUB — Mozilla TTS not yet connected."""
    return synthesize(request.text, request.lang)
