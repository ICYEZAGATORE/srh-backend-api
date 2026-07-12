"""
app/services/vector_store.py — Vector store abstraction (Pinecone + Chroma).

Role in the RAG pipeline
------------------------
Provides a single ``VectorStoreClient`` interface so the rest of the app
(ingestion, ``retrieve_context``) never knows or cares which backend is active:

  - ``PineconeVectorStore`` — cloud, used in deployment (modern serverless SDK).
  - ``ChromaVectorStore``   — local, embedded; used for development and CI
                              (no API key required).

``get_vector_store()`` picks the backend from ``VECTOR_STORE_BACKEND`` and caches
a singleton. The router layer only ever calls ``retrieve_context`` (in
``app/ml/embeddings.py``) — it never imports this module directly.

Chunk contract
--------------
``upsert`` accepts dicts shaped as::

    {"id": str, "embedding": List[float], "text": str,
     "metadata": {"topic": str, "language": "en"|"rw",
                  "title": str | None, "source": str | None}}

``similarity_search`` returns dicts shaped as::

    {"entry_id": str, "topic": str, "lang": str,
     "title": str | None, "text": str, "score": float}

Runtime dependencies
--------------------
- ``chromadb`` (local backend; embedded, persists to ``CHROMA_PERSIST_DIR``).
- ``pinecone`` + ``PINECONE_API_KEY`` (cloud backend).
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _result(entry_id, meta: dict, text: str, score: float) -> dict:
    """Normalise a backend hit into the router-facing chunk shape."""
    return {
        "entry_id": str(entry_id),
        "topic": meta.get("topic"),
        "lang": meta.get("language") or meta.get("lang"),
        "title": meta.get("title"),
        "text": text or meta.get("text", ""),
        "score": float(score),
    }


class VectorStoreClient(ABC):
    """Common interface for all vector store backends."""

    @abstractmethod
    def upsert(self, chunks: List[dict]) -> None: ...

    @abstractmethod
    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> List[dict]: ...

    @abstractmethod
    def delete(self, ids: List[str]) -> None: ...


# ── Pinecone (cloud) ────────────────────────────────────────────────────────
class PineconeVectorStore(VectorStoreClient):
    """Serverless Pinecone backend (modern ``pinecone`` SDK, v3+)."""

    def __init__(self, index_name: str | None = None, dim: int | None = None) -> None:
        from pinecone import Pinecone, ServerlessSpec

        if not settings.PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is not set.")
        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self._index_name = index_name or settings.PINECONE_INDEX_NAME
        dim = dim or settings.EMBEDDING_DIM

        existing = {i["name"] for i in self._pc.list_indexes()}
        if self._index_name not in existing:
            logger.info("Creating Pinecone index '%s' (dim=%s, cosine).",
                        self._index_name, dim)
            self._pc.create_index(
                name=self._index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=settings.PINECONE_CLOUD, region=settings.PINECONE_REGION
                ),
            )
        self._index = self._pc.Index(self._index_name)

    @staticmethod
    def _to_filter(filter: Optional[dict]) -> Optional[dict]:
        if not filter:
            return None
        return {k: {"$eq": v} for k, v in filter.items() if v is not None} or None

    def upsert(self, chunks: List[dict]) -> None:
        vectors = []
        for c in chunks:
            meta = dict(c.get("metadata", {}))
            meta["text"] = c.get("text", "")  # keep text in metadata for retrieval
            vectors.append({"id": c["id"], "values": c["embedding"], "metadata": meta})
        # Pinecone caps batch size; upsert in chunks of 100.
        for i in range(0, len(vectors), 100):
            self._index.upsert(vectors=vectors[i : i + 100])

    def similarity_search(self, query_embedding, top_k=5, filter=None) -> List[dict]:
        res = self._index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=self._to_filter(filter),
        )
        out = []
        for m in res.get("matches", []):
            meta = m.get("metadata", {}) or {}
            out.append(_result(m["id"], meta, meta.get("text", ""), m.get("score", 0.0)))
        return out

    def delete(self, ids: List[str]) -> None:
        if ids:
            self._index.delete(ids=ids)


# ── Chroma (local / CI) ─────────────────────────────────────────────────────
class ChromaVectorStore(VectorStoreClient):
    """Embedded ChromaDB backend, persisted to ``CHROMA_PERSIST_DIR``."""

    def __init__(self, persist_dir: Optional[str] = None,
                 collection_name: Optional[str] = None) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(
            path=persist_dir or settings.CHROMA_PERSIST_DIR
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name or settings.PINECONE_INDEX_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _to_where(filter: Optional[dict]) -> Optional[dict]:
        clean = {k: v for k, v in (filter or {}).items() if v is not None}
        if not clean:
            return None
        if len(clean) == 1:
            return clean
        return {"$and": [{k: v} for k, v in clean.items()]}

    def upsert(self, chunks: List[dict]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c["id"] for c in chunks],
            embeddings=[c["embedding"] for c in chunks],
            documents=[c.get("text", "") for c in chunks],
            metadatas=[dict(c.get("metadata", {})) for c in chunks],
        )

    def similarity_search(self, query_embedding, top_k=5, filter=None) -> List[dict]:
        res = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=self._to_where(filter),
            include=["metadatas", "documents", "distances"],
        )
        out = []
        ids = (res.get("ids") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, _id in enumerate(ids):
            meta = metas[i] or {}
            # cosine distance -> similarity score
            score = 1.0 - float(dists[i]) if i < len(dists) else 0.0
            out.append(_result(_id, meta, docs[i] if i < len(docs) else "", score))
        return out

    def delete(self, ids: List[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)


# ── Factory / singleton ─────────────────────────────────────────────────────
_stores: "dict[str, VectorStoreClient]" = {}
_lock = threading.Lock()


def _make_store(index_name: str, dim: int) -> VectorStoreClient:
    backend = (settings.VECTOR_STORE_BACKEND or "chroma").lower()
    if backend == "pinecone":
        return PineconeVectorStore(index_name=index_name, dim=dim)
    return ChromaVectorStore(collection_name=index_name)


def get_vector_store(
    index_name: str | None = None, dim: int | None = None
) -> VectorStoreClient:
    """Return the vector store for an index (English default), cached per index.

    Different indexes (English 384-d, Kinyarwanda 1024-d) get independent
    singletons keyed by index name.
    """
    key = index_name or settings.PINECONE_INDEX_NAME
    store = _stores.get(key)
    if store is None:
        with _lock:
            store = _stores.get(key)
            if store is None:
                store = _make_store(key, dim or settings.EMBEDDING_DIM)
                _stores[key] = store
                logger.info("Vector store backend=%s index=%s",
                            settings.VECTOR_STORE_BACKEND, key)
    return store


def get_rw_vector_store() -> VectorStoreClient:
    """Vector store for the Kinyarwanda index (bge-m3, 1024-d)."""
    return get_vector_store(settings.RW_PINECONE_INDEX_NAME, settings.RW_EMBEDDING_DIM)


def reset_vector_store() -> None:
    """Drop cached store singletons (used by tests to switch backends)."""
    _stores.clear()
