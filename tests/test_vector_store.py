"""tests/test_vector_store.py — Chroma backend upsert / search / filtering.

Uses the keyless local Chroma backend (forced by the conftest autouse fixture),
so no Pinecone key is required. Pinecone-specific behaviour is covered by a
separate, skipped-by-default test.
"""

import os

import pytest

from app.services.vector_store import ChromaVectorStore


def _chunk(cid, text, topic, language, vec):
    return {
        "id": cid,
        "embedding": vec,
        "text": text,
        "metadata": {"topic": topic, "language": language, "title": None,
                     "source": "test"},
    }


@pytest.fixture
def store(tmp_path):
    return ChromaVectorStore(persist_dir=str(tmp_path / "chroma"))


def test_chroma_upsert_and_search(store):
    store.upsert([
        _chunk("a", "condoms and birth control", "contraception", "en", [1.0, 0.0, 0.0]),
        _chunk("b", "kuboneza urubyaro", "contraception", "rw", [0.9, 0.1, 0.0]),
    ])
    hits = store.similarity_search([1.0, 0.0, 0.0], top_k=2)
    assert len(hits) == 2
    assert {h["entry_id"] for h in hits} == {"a", "b"}
    assert "text" in hits[0] and "topic" in hits[0] and "lang" in hits[0]


def test_similarity_search_returns_top_k_results(store):
    store.upsert([
        _chunk(str(i), f"doc {i}", "general_srh", "en", [float(i), 1.0, 0.0])
        for i in range(5)
    ])
    hits = store.similarity_search([0.0, 1.0, 0.0], top_k=3)
    assert len(hits) == 3


def test_language_filter_works(store):
    store.upsert([
        _chunk("en1", "english text", "sti_hiv", "en", [1.0, 0.0, 0.0]),
        _chunk("rw1", "kinyarwanda", "sti_hiv", "rw", [1.0, 0.0, 0.0]),
    ])
    hits = store.similarity_search([1.0, 0.0, 0.0], top_k=5, filter={"language": "rw"})
    assert len(hits) == 1
    assert hits[0]["entry_id"] == "rw1"
    assert hits[0]["lang"] == "rw"


@pytest.mark.skipif(
    not os.getenv("PINECONE_API_KEY"), reason="Pinecone not configured"
)
def test_pinecone_backend_constructs():
    from app.services.vector_store import PineconeVectorStore

    store = PineconeVectorStore()
    assert store is not None
