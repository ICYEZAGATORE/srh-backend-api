"""
app/schemas/tts.py — Request schema for the /tts endpoint.
"""

from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesise to speech.")
    lang: str = Field(..., description="Language code: 'en' or 'rw'.")
