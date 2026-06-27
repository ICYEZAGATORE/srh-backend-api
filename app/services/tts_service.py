"""
app/services/tts_service.py — Mozilla TTS wrapper.

STUB: TTS is not yet connected. When the Mozilla TTS server (Kinyarwanda voice
model) is available, POST the text to ``TTS_SERVICE_URL`` and return either an
audio URL or a streamed audio/mpeg response. Keep this signature stable.
"""


def synthesize(text: str, lang: str) -> dict:
    """Return a TTS result. STUB — not yet connected to Mozilla TTS."""
    return {"audio_url": None, "message": "TTS service not yet connected"}
