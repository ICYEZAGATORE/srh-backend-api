"""tests/test_rw_routing.py — dual-index (English MiniLM / Kinyarwanda bge-m3) routing.

Validates the plumbing that keeps English and Kinyarwanda on separate embedders
and separate vector indexes, WITHOUT downloading the real bge-m3 model:

  - ``ingest_rw_chunks`` embeds with the RW embedder and upserts to the RW index.
  - the English (default) index is never touched by an RW ingest.
  - ``retrieve_context(lang="rw")`` reads from the RW index; ``lang="en"`` reads
    from the English index.

The real embedders are stubbed with deterministic fakes so the test is offline
and fast; correctness of bge-m3 itself is a separate (manual) retrieval check.
"""

import hashlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import settings
from app.database import Base
from app.models.knowledge import KnowledgeEntry


class _FakeEmbedder:
    """Deterministic hash-based embedder of a fixed dimension (no network)."""

    def __init__(self, dim: int):
        self.dim = dim

    def _vec(self, text: str):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Tile the 32-byte digest out to ``dim`` floats in [0, 1).
        return [h[i % len(h)] / 255.0 for i in range(self.dim)]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def fake_embedders(monkeypatch):
    """Stub both embedders (module-level accessors used by ingest + retrieve)."""
    from app.ml import embeddings

    en = _FakeEmbedder(settings.EMBEDDING_DIM)
    rw = _FakeEmbedder(settings.RW_EMBEDDING_DIM)
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: en)
    monkeypatch.setattr(embeddings, "get_rw_embedding_model", lambda: rw)
    return en, rw


def _rw_chunk(cid, text):
    return {
        "id": cid,
        "text": text,
        "metadata": {"topic": "contraception", "language": "rw",
                     "title": None, "source": "rw_test"},
    }


def test_ingest_rw_lands_in_rw_index_only(db, fake_embedders):
    from app.services.ingestion import ingest_rw_chunks
    from app.services.vector_store import get_rw_vector_store, get_vector_store

    report = ingest_rw_chunks(
        [_rw_chunk("rw-a", "kuboneza urubyaro"),
         _rw_chunk("rw-b", "imibonano mpuzabitsina")],
        db,
    )
    assert report["ingested"] == 2

    # RW index holds the vectors; the English (default) index stays empty.
    rw_hits = get_rw_vector_store().similarity_search(
        _FakeEmbedder(settings.RW_EMBEDDING_DIM).embed_query("kuboneza urubyaro"),
        top_k=5,
    )
    assert {h["entry_id"] for h in rw_hits} == {"rw-a", "rw-b"}

    en_hits = get_vector_store().similarity_search(
        _FakeEmbedder(settings.EMBEDDING_DIM).embed_query("anything"), top_k=5
    )
    assert en_hits == []

    # Relational audit row still written.
    assert db.scalar(select(func.count()).select_from(KnowledgeEntry)) == 2


def test_retrieve_context_routes_by_language(db, fake_embedders):
    from app.ml.embeddings import retrieve_context
    from app.services.ingestion import ingest_rw_chunks

    ingest_rw_chunks([_rw_chunk("rw-a", "kuboneza urubyaro")], db)

    rw_hits = retrieve_context("kuboneza urubyaro", lang="rw", top_k=5)
    assert any(h["entry_id"] == "rw-a" for h in rw_hits)

    # English index was never seeded here -> no hits, and no crash from the
    # dimension mismatch (each index/embedder pair is self-consistent).
    en_hits = retrieve_context("family planning", lang="en", top_k=5)
    assert en_hits == []
