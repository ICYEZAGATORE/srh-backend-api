"""
app/services/translation.py — Provider-agnostic machine translation.

Used ONLY by the Kinyarwanda "translate" pipeline
(``KINYARWANDA_PIPELINE_MODE=translate``); the English request path never
imports this module. Exposes a single stable entry point::

    translate(text, source_lang, target_lang) -> str

backed by whichever adapter ``settings.TRANSLATION_PROVIDER`` selects. Adapters
stay switchable so the offline comparison harness (srh-ml-model) can pick a
winner without a single-provider hard dependency.

Design contract
---------------
- Language codes at THIS interface are the app's short codes: ``"en"`` /
  ``"rw"``. Each adapter maps them to its own convention (e.g. NLLB FLORES
  ``eng_Latn`` / ``kin_Latn``).
- Every network call is bounded by ``settings.TRANSLATION_TIMEOUT_SECONDS`` and
  raises :class:`TranslationError` on failure/timeout/empty output. Callers
  (see app/services/kinyarwanda_pipeline.py) catch this and fall back to the
  native rw path — a translation failure must NEVER surface as a 500.
- No provider network call happens at import time; clients are built lazily and
  cached on the adapter instance.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# App short code -> (Google code, NLLB FLORES-200 code).
_LANG = {
    "en": {"google": "en", "nllb": "eng_Latn"},
    "rw": {"google": "rw", "nllb": "kin_Latn"},
}


class TranslationError(RuntimeError):
    """Raised when translation is unavailable or fails (caller falls back)."""


def _code(lang: str, provider: str) -> str:
    try:
        return _LANG[lang][provider]
    except KeyError as exc:
        raise TranslationError(
            f"Unsupported language '{lang}' for provider '{provider}'."
        ) from exc


# ── Provider adapters ───────────────────────────────────────────────────────
class TranslationProvider(ABC):
    """Common interface for all translation backends."""

    name: str = "base"

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate ``text`` from ``source_lang`` to ``target_lang`` (short codes)."""


class GoogleTranslateProvider(TranslationProvider):
    """Google Cloud Translation API v2 (REST, API-key auth).

    Uses the simple v2 REST endpoint so only an API key is required (no service
    account / ADC), matching the existing key-in-env pattern. Managed + no local
    GPU, so it is viable on the Render free tier.
    """

    name = "google"
    _ENDPOINT = "https://translation.googleapis.com/language/translate/v2"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not settings.GOOGLE_TRANSLATE_API_KEY:
            raise TranslationError("GOOGLE_TRANSLATE_API_KEY not set.")
        import requests

        try:
            resp = requests.post(
                self._ENDPOINT,
                params={"key": settings.GOOGLE_TRANSLATE_API_KEY},
                data={
                    "q": text,
                    "source": _code(source_lang, "google"),
                    "target": _code(target_lang, "google"),
                    "format": "text",
                },
                timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            payload = resp.json()
            out = payload["data"]["translations"][0]["translatedText"]
        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001 - unify to TranslationError
            raise TranslationError(f"Google translate failed: {exc}") from exc
        if not out or not out.strip():
            raise TranslationError("Google translate returned empty output.")
        return out.strip()


class NLLBProvider(TranslationProvider):
    """NLLB-200 via a HOSTED endpoint (e.g. an HF Inference Endpoint).

    Local GPU inference is not viable on the free tier, so this adapter only
    works when ``NLLB_ENDPOINT_URL`` points at a managed endpoint. NLLB-200 is
    CC-BY-NC 4.0 (non-commercial) — see the harness output before deploying it
    beyond the academic pilot.
    """

    name = "nllb"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not settings.NLLB_ENDPOINT_URL:
            raise TranslationError("NLLB_ENDPOINT_URL not set.")
        import requests

        headers = {"Content-Type": "application/json"}
        if settings.HF_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.HF_API_TOKEN}"
        try:
            resp = requests.post(
                settings.NLLB_ENDPOINT_URL,
                headers=headers,
                json={
                    "inputs": text,
                    "parameters": {
                        "src_lang": _code(source_lang, "nllb"),
                        "tgt_lang": _code(target_lang, "nllb"),
                    },
                },
                timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            out = _parse_hf_translation(resp.json())
        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"NLLB translate failed: {exc}") from exc
        if not out or not out.strip():
            raise TranslationError("NLLB translate returned empty output.")
        return out.strip()


class DigitalUmugandaProvider(TranslationProvider):
    """Digital Umuganda's fine-tuned Kinyarwanda MT model, via HF Inference.

    Requires ``DIGITAL_UMUGANDA_MODEL_ID`` (a published HF model id). If no
    public, license-clear model is configured this adapter raises and the caller
    falls back — the harness documents availability/license explicitly.
    """

    name = "digital_umuganda"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        model_id = settings.DIGITAL_UMUGANDA_MODEL_ID
        if not model_id:
            raise TranslationError("DIGITAL_UMUGANDA_MODEL_ID not set.")
        try:
            from huggingface_hub import InferenceClient

            client = InferenceClient(
                model=model_id,
                token=settings.HF_API_TOKEN or None,
                timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
            )
            out = client.translation(
                text,
                src_lang=_code(source_lang, "nllb"),
                tgt_lang=_code(target_lang, "nllb"),
            )
            # InferenceClient may return a str or an object with .translation_text.
            out = getattr(out, "translation_text", out)
        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"Digital Umuganda translate failed: {exc}") from exc
        if not isinstance(out, str) or not out.strip():
            raise TranslationError("Digital Umuganda returned empty output.")
        return out.strip()


def _parse_hf_translation(payload) -> str:
    """Extract translated text from common HF response shapes."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return payload.get("translation_text") or payload.get("generated_text") or ""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return first.get("translation_text") or first.get("generated_text") or ""
        if isinstance(first, str):
            return first
    return ""


_PROVIDERS = {
    "google": GoogleTranslateProvider,
    "nllb": NLLBProvider,
    "digital_umuganda": DigitalUmugandaProvider,
}


def get_translator(provider: Optional[str] = None) -> TranslationProvider:
    """Return the adapter for ``provider`` (defaults to TRANSLATION_PROVIDER)."""
    name = (provider or settings.TRANSLATION_PROVIDER or "").strip().lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise TranslationError(
            f"No translation provider configured (TRANSLATION_PROVIDER='{name}'). "
            f"Valid: {', '.join(_PROVIDERS)}."
        )
    return cls()


def translate(
    text: str,
    source_lang: str,
    target_lang: str,
    provider: Optional[str] = None,
) -> str:
    """Translate ``text`` between app short codes ("en"/"rw").

    Raises :class:`TranslationError` on any failure/timeout/empty output so the
    caller can fall back to the native path. A blank input short-circuits to "".
    """
    if not text or not text.strip():
        return ""
    return get_translator(provider).translate(text, source_lang, target_lang)
