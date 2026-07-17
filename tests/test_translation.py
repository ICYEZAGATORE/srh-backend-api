"""tests/test_translation.py — provider-agnostic translation adapters.

No real network calls: verifies provider selection, the language-code mapping,
blank-input handling, credential-missing errors, and that provider failures are
unified into TranslationError (which callers catch to fall back).
"""

import pytest

from app.config import settings
from app.services import translation
from app.services.translation import (
    DigitalUmugandaProvider,
    GoogleTranslateProvider,
    NLLBProvider,
    TranslationError,
    _code,
    _parse_hf_translation,
    get_translator,
    translate,
)


def test_get_translator_selects_provider(monkeypatch):
    monkeypatch.setattr(settings, "TRANSLATION_PROVIDER", "google")
    assert isinstance(get_translator(), GoogleTranslateProvider)
    assert isinstance(get_translator("nllb"), NLLBProvider)
    assert isinstance(get_translator("digital_umuganda"), DigitalUmugandaProvider)


def test_unknown_provider_raises():
    with pytest.raises(TranslationError):
        get_translator("none")


def test_blank_input_short_circuits():
    assert translate("", "rw", "en") == ""
    assert translate("   ", "en", "rw") == ""


def test_language_code_mapping():
    assert _code("en", "nllb") == "eng_Latn"
    assert _code("rw", "nllb") == "kin_Latn"
    assert _code("en", "google") == "en"
    with pytest.raises(TranslationError):
        _code("fr", "google")


def test_missing_credentials_raise(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(settings, "NLLB_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "DIGITAL_UMUGANDA_MODEL_ID", "")
    with pytest.raises(TranslationError):
        GoogleTranslateProvider().translate("muraho", "rw", "en")
    with pytest.raises(TranslationError):
        NLLBProvider().translate("muraho", "rw", "en")
    with pytest.raises(TranslationError):
        DigitalUmugandaProvider().translate("muraho", "rw", "en")


def test_google_success(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_TRANSLATE_API_KEY", "test-key")

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"translations": [{"translatedText": "hello"}]}}

    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    assert GoogleTranslateProvider().translate("muraho", "rw", "en") == "hello"


def test_google_failure_unified_to_translation_error(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_TRANSLATE_API_KEY", "test-key")

    import requests

    def _boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(requests, "post", _boom)
    with pytest.raises(TranslationError):
        GoogleTranslateProvider().translate("muraho", "rw", "en")


def test_parse_hf_translation_shapes():
    assert _parse_hf_translation("plain") == "plain"
    assert _parse_hf_translation({"translation_text": "x"}) == "x"
    assert _parse_hf_translation([{"translation_text": "y"}]) == "y"
    assert _parse_hf_translation([{"generated_text": "z"}]) == "z"
    assert _parse_hf_translation({}) == ""
