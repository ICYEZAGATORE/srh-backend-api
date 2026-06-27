"""
app/ml/embeddings.py — Vector DB query wrapper.

STUB: returns no context chunks while the vector DB and embedding model are
not yet wired up. Keep this signature stable so the real retrieval pipeline
can be swapped in without touching the conversational agent or routers.

Target setup (see README):
    - Embedding model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    - Dimension: 384
    - Index: srh-knowledge-base (Pinecone or Milvus)
"""


def retrieve_context(query: str, lang: str = "en", top_k: int = 5) -> list[dict]:
    """Return the top-k SRH knowledge chunks most relevant to ``query``.

    STUB — replace with embed(query) + similarity search in the vector DB.
    Each chunk dict is expected to look like:
        {"entry_id": ..., "topic": ..., "lang": ..., "title": ..., "text": ...}
    """
    return []
