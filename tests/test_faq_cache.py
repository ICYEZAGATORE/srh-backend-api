"""tests/test_faq_cache.py — predefined-question FAQ cache lookup.

Exercises the in-memory cosine lookup with a tiny fixture file and a
deterministic fake rw embedder (no bge-m3 download, no network). Verifies the
high-threshold hit/miss behaviour, the unreviewed-row flag, and that a missing
or disabled cache degrades to "no hit" rather than raising.
"""

import json

import pytest

from app.config import settings
from app.services.faq_cache import FaqCache


class _FakeRwEmbedder:
    """Returns a fixed 4-dim vector per exact query string (else zeros)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def embed_query(self, text):
        return self._mapping.get(text, [0.0, 0.0, 0.0, 0.0])


@pytest.fixture
def fixture_cache(tmp_path):
    rows = [
        {"question_rw": "Ubugimbi ni iki?", "answer_rw": "Ubugimbi ni impinduka.",
         "topic": "puberty", "approved": False, "embedding": [1.0, 0.0, 0.0, 0.0]},
        {"question_rw": "Kuboneza urubyaro?", "answer_rw": "Hari uburyo bwinshi.",
         "topic": "contraception", "approved": True, "embedding": [0.0, 1.0, 0.0, 0.0]},
    ]
    path = tmp_path / "faq_cache_rw.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(path)


@pytest.fixture
def patch_embedder(monkeypatch):
    def _apply(mapping):
        from app.ml import embeddings

        monkeypatch.setattr(
            embeddings, "get_rw_embedding_model", lambda: _FakeRwEmbedder(mapping)
        )
    return _apply


def test_near_duplicate_hit_returns_answer(fixture_cache, patch_embedder, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "FAQ_SIMILARITY_THRESHOLD", 0.90)
    patch_embedder({"Ubugimbi ni iki cyane?": [1.0, 0.0, 0.0, 0.0]})

    hit = FaqCache(fixture_cache).lookup("Ubugimbi ni iki cyane?")
    assert hit is not None
    assert hit["answer_rw"] == "Ubugimbi ni impinduka."
    assert hit["topic"] == "puberty"
    assert hit["approved"] is False  # unreviewed row -> caller flags low-confidence
    assert hit["score"] >= 0.90


def test_low_similarity_is_a_miss(fixture_cache, patch_embedder, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "FAQ_SIMILARITY_THRESHOLD", 0.90)
    # Orthogonal to every stored vector -> cosine 0 < threshold.
    patch_embedder({"unrelated question": [0.0, 0.0, 1.0, 0.0]})

    assert FaqCache(fixture_cache).lookup("unrelated question") is None


def test_approved_row_reports_approved(fixture_cache, patch_embedder, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "FAQ_SIMILARITY_THRESHOLD", 0.90)
    patch_embedder({"kuboneza?": [0.0, 1.0, 0.0, 0.0]})

    hit = FaqCache(fixture_cache).lookup("kuboneza?")
    assert hit is not None and hit["approved"] is True


def test_disabled_cache_returns_none(fixture_cache, patch_embedder, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", False)
    patch_embedder({"anything": [1.0, 0.0, 0.0, 0.0]})
    assert FaqCache(fixture_cache).lookup("anything") is None


def test_missing_file_returns_none(tmp_path, patch_embedder, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    patch_embedder({"anything": [1.0, 0.0, 0.0, 0.0]})
    missing = str(tmp_path / "does_not_exist.jsonl")
    assert FaqCache(missing).lookup("anything") is None


def test_blank_query_returns_none(fixture_cache, monkeypatch):
    monkeypatch.setattr(settings, "FAQ_CACHE_ENABLED", True)
    assert FaqCache(fixture_cache).lookup("   ") is None
