"""tests/test_kinyarwanda_pipeline.py — rw orchestrator + router integration.

Covers, with everything downstream mocked (no network, no models):
  - FAQ hit short-circuits translation + generation and flags unreviewed rows.
  - FAQ hit that trips the output-side safety filter -> safety block.
  - native-mode FAQ miss -> None (router falls through to the existing rw path).
  - translate mode reuses the ENGLISH functions on the translated text.
  - a translation failure -> None (graceful fallback, never a 500).
  - back-translation QA sets the low_confidence flag when the round-trip diverges.
  - router: UNSAFE rw still short-circuits BEFORE the FAQ cache; a rw FAQ hit is
    surfaced; a None result falls through to native generation.
"""

import pytest

import app.routers.chat as chat_module
from app.config import settings
from app.ml.conversational_agent import SRHConversationalAgent
from app.services import kinyarwanda_pipeline as kp
from app.services.kinyarwanda_pipeline import RwResult, handle_kinyarwanda_query


class _FakeFaq:
    def __init__(self, hit):
        self._hit = hit

    def lookup(self, query, threshold=None):
        return self._hit


class _FakeEmbedder:
    """Maps exact text -> vector; default vector otherwise."""

    def __init__(self, mapping, default):
        self._mapping = mapping
        self._default = default

    def embed_query(self, text):
        return self._mapping.get(text, self._default)


def _patch_faq(monkeypatch, hit):
    import app.services.faq_cache as faq

    monkeypatch.setattr(faq, "get_faq_cache", lambda: _FakeFaq(hit))


def _patch_safe_response(monkeypatch, label=0):
    import app.ml.safety_classifier as sc

    monkeypatch.setattr(sc, "classify_response_safety", lambda text: {"label": label})


# ── FAQ cache path ──────────────────────────────────────────────────────────
def test_faq_hit_short_circuits(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    _patch_faq(monkeypatch, {
        "answer_rw": "Ubugimbi ni impinduka.", "topic": "puberty",
        "approved": False, "score": 0.97,
    })
    _patch_safe_response(monkeypatch, label=0)
    # translation must NOT be consulted on a FAQ hit.
    import app.services.translation as tr
    monkeypatch.setattr(tr, "translate", lambda *a, **k: pytest.fail("translate called"))

    res = handle_kinyarwanda_query("Ubugimbi ni iki?")
    assert isinstance(res, RwResult)
    assert res.faq_cache_hit is True
    assert res.pipeline_mode == "faq"
    assert res.response_text == "Ubugimbi ni impinduka."
    assert res.unreviewed is True   # approved=False row
    assert res.unsafe is False


def test_faq_hit_blocked_by_output_safety(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    _patch_faq(monkeypatch, {
        "answer_rw": "bad", "topic": "gbv_consent", "approved": True, "score": 0.99,
    })
    _patch_safe_response(monkeypatch, label=1)

    res = handle_kinyarwanda_query("something")
    assert res.unsafe is True
    assert res.response_text is None
    assert res.faq_cache_hit is True


def test_native_miss_falls_through(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "KINYARWANDA_PIPELINE_MODE", "native")
    _patch_faq(monkeypatch, None)

    assert handle_kinyarwanda_query("off-cache rw query") is None


# ── Translate pipeline path ─────────────────────────────────────────────────
def _patch_translate_pipeline(monkeypatch, *, generate_ret="English answer",
                              response_label=0, same_embedding=True):
    """Wire up the translate pipeline with recording stubs; return a call log."""
    calls = {}

    import app.ml.conversational_agent as ca
    import app.ml.embeddings as emb
    import app.ml.safety_classifier as sc
    import app.ml.topic_classifier as tc
    import app.services.translation as tr

    def fake_translate(text, src, tgt, provider=None):
        calls.setdefault("translate", []).append((text, src, tgt))
        return f"[{src}->{tgt}]{text}"

    def fake_topic(text):
        calls["topic_text"] = text
        return {"topic": "contraception", "label": 0, "score": 0.9}

    def fake_retrieve(query, lang="en", top_k=5, topic=None):
        calls["retrieve"] = {"query": query, "lang": lang, "topic": topic}
        return []

    def fake_generate(query, context_chunks, lang, simplified=False, **kw):
        calls["generate"] = {"query": query, "lang": lang}
        return generate_ret

    monkeypatch.setattr(tr, "translate", fake_translate)
    monkeypatch.setattr(tc, "classify_topic", fake_topic)
    monkeypatch.setattr(emb, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(ca, "generate_response", fake_generate)
    monkeypatch.setattr(sc, "classify_response_safety", lambda text: {"label": response_label})

    if same_embedding:
        fake_emb = _FakeEmbedder({}, [1.0, 0.0])          # identical -> cosine 1.0
    else:
        fake_emb = _FakeEmbedder({generate_ret: [1.0, 0.0]}, [0.0, 1.0])  # diverge -> 0.0
    monkeypatch.setattr(emb, "get_embedding_model", lambda: fake_emb)
    return calls


def test_translate_mode_reuses_english_path(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "KINYARWANDA_PIPELINE_MODE", "translate")
    _patch_faq(monkeypatch, None)
    calls = _patch_translate_pipeline(monkeypatch, same_embedding=True)

    res = handle_kinyarwanda_query("Ikibazo cyanjye")
    assert res is not None
    assert res.pipeline_mode == "translate"
    # English functions were called on the rw->en translated text.
    assert calls["topic_text"] == "[rw->en]Ikibazo cyanjye"
    assert calls["retrieve"]["lang"] == "en"
    assert calls["retrieve"]["query"] == "[rw->en]Ikibazo cyanjye"
    assert calls["generate"]["lang"] == "en"
    # Final answer is the English response translated back to rw.
    assert res.response_text == "[en->rw]English answer"
    assert res.low_confidence_translation is False


def test_translate_failure_falls_back_to_none(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "KINYARWANDA_PIPELINE_MODE", "translate")
    _patch_faq(monkeypatch, None)

    import app.services.translation as tr

    def boom(text, src, tgt, provider=None):
        raise tr.TranslationError("provider down")

    monkeypatch.setattr(tr, "translate", boom)
    assert handle_kinyarwanda_query("Ikibazo") is None


def test_translate_blocked_by_output_safety(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "KINYARWANDA_PIPELINE_MODE", "translate")
    _patch_faq(monkeypatch, None)
    _patch_translate_pipeline(monkeypatch, response_label=1)

    res = handle_kinyarwanda_query("Ikibazo")
    assert res is not None and res.unsafe is True and res.response_text is None


def test_back_translation_low_confidence_flag(monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "KINYARWANDA_PIPELINE_MODE", "translate")
    monkeypatch.setattr(settings, "BACK_TRANSLATION_SIMILARITY_THRESHOLD", 0.75)
    _patch_faq(monkeypatch, None)
    _patch_translate_pipeline(monkeypatch, same_embedding=False)

    res = handle_kinyarwanda_query("Ikibazo")
    assert res is not None
    assert res.low_confidence_translation is True


# ── Router integration ──────────────────────────────────────────────────────
def _new_session(client) -> str:
    return client.post("/api/v1/session/start").json()["session_id"]


def _force_rw(monkeypatch):
    monkeypatch.setattr(
        chat_module, "detect_language", lambda text, hint=None: {"language": "rw"}
    )


def test_router_rw_faq_hit_is_surfaced(client, monkeypatch):
    _force_rw(monkeypatch)
    monkeypatch.setattr(
        chat_module, "handle_kinyarwanda_query",
        lambda *a, **k: RwResult(
            response_text="Igisubizo cy'ubugimbi.", topic="puberty",
            pipeline_mode="faq", faq_cache_hit=True, unreviewed=True,
        ),
    )
    sid = _new_session(client)
    body = client.post("/api/v1/chat", json={
        "session_id": sid, "message": "Ubugimbi ni iki?", "lang": "rw",
    }).json()
    assert body["safe"] is True
    assert body["fallback"] is False
    assert body["response"] == "Igisubizo cy'ubugimbi."
    assert body["topic"] == "puberty"


def test_router_unsafe_rw_skips_faq(client, monkeypatch):
    _force_rw(monkeypatch)
    monkeypatch.setattr(chat_module, "classify_safety",
                        lambda text: {"label": 1, "score": 0.99})

    def _should_not_run(*a, **k):
        raise AssertionError("handle_kinyarwanda_query called on an UNSAFE query")

    monkeypatch.setattr(chat_module, "handle_kinyarwanda_query", _should_not_run)

    sid = _new_session(client)
    body = client.post("/api/v1/chat", json={
        "session_id": sid, "message": "kwica umuntu", "lang": "rw",
    }).json()
    assert body["safe"] is False and body["fallback"] is True
    assert body["response"] is None


def test_router_rw_native_miss_falls_through(client, monkeypatch):
    _force_rw(monkeypatch)
    # Orchestrator returns None -> shared native path runs; inject an LLM answer.
    monkeypatch.setattr(chat_module, "handle_kinyarwanda_query", lambda *a, **k: None)
    monkeypatch.setattr(
        SRHConversationalAgent, "_call_llm", lambda self, prompt: "Igisubizo gisanzwe."
    )
    sid = _new_session(client)
    body = client.post("/api/v1/chat", json={
        "session_id": sid, "message": "ikibazo kidasanzwe", "lang": "rw",
    }).json()
    assert body["safe"] is True
    assert body["response"] == "Igisubizo gisanzwe."
