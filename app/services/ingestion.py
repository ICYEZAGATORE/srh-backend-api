"""
app/services/ingestion.py — Knowledge-base ingestion core (chunk → embed → upsert).

Role in the RAG pipeline
------------------------
Shared, idempotent ingestion logic used by BOTH:
  - ``scripts/ingest_knowledge_base.py`` (bulk build from source documents), and
  - ``POST /admin/knowledge/upload`` (add one file post-deployment).

Pipeline per document:
  1. clean text (strip headers/footers/page numbers, normalise whitespace,
     keep English + Kinyarwanda characters),
  2. chunk with LangChain ``RecursiveCharacterTextSplitter`` (500 / 50),
  3. per-chunk metadata: language (en/rw), topic (7-class taxonomy),
     source, chunk_id, date_ingested, sha-256 content hash,
  4. embed new chunks (``SRHEmbeddingModel``),
  5. upsert to the active vector store + insert a ``KnowledgeEntry`` row +
     append to the local JSONL cache.

Idempotency: the sha-256 ``chunk_hash`` is the vector id and a unique DB column,
so re-ingesting the same text upserts the same vectors and inserts no duplicate
rows.

NOTE ON HEURISTICS: language and topic tagging here are lightweight heuristics
(``langdetect`` has no Kinyarwanda model, so a token heuristic is used for rw).
They can be replaced by the trained language/topic classifiers later without
changing this interface. No health facts are generated — only sourced text is
chunked and stored.

Runtime dependencies: ``langchain-text-splitters``, ``langdetect``, the embedding
model, and a vector store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from app.models.knowledge import KnowledgeEntry

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
KB_CACHE_DIR = os.path.join("data", "knowledge_base")

# 7-class taxonomy (matches app/ml/topic_classifier.py).
TOPICS = [
    "contraception", "sti_hiv", "pregnancy", "puberty",
    "gbv_consent", "disability_srh", "general_srh",
]

# Compact word-boundary keyword map for tagging chunk topics (heuristic).
_TOPIC_KEYWORDS = {
    "contraception": ["contracept", "birth control", "condom", "family planning",
                      "iud", "implant", "morning after", "plan b"],
    "sti_hiv": ["hiv", "aids", "sti", "std", "sexually transmitted", "chlamydia",
                "gonorrh", "syphilis", "herpes", "hpv", "prep", "condom"],
    "pregnancy": ["pregnan", "antenatal", "prenatal", "childbirth", "miscarriage",
                  "abortion", "maternal", "trimester", "ovulation"],
    "puberty": ["puberty", "menstru", "adolescen", "period", "menarche"],
    "gbv_consent": ["consent", "sexual violence", "rape", "assault",
                    "gender-based violence", "gender based violence", "abuse",
                    "coercion"],
    "disability_srh": ["disability", "disabled", "wheelchair", "visual impairment",
                       "hearing impairment", "blind", "deaf"],
}
_TOPIC_RE = {
    t: re.compile(r"\b(" + "|".join(re.escape(k) for k in kws) + r")", re.IGNORECASE)
    for t, kws in _TOPIC_KEYWORDS.items()
}

# High-frequency Kinyarwanda tokens (langdetect has no rw model).
_RW_MARKERS = {
    "mu", "ni", "na", "ku", "ba", "iyo", "ariko", "kandi", "cyangwa", "ubwo",
    "uburyo", "umuntu", "abantu", "kubera", "ubuzima", "indwara", "imibonano",
    "urubyaro", "kuboneza", "nka", "muri", "ubwoba", "byose", "cyane", "gukora",
}


def clean_text(text: str) -> str:
    """Strip page furniture / control chars; keep EN + RW characters."""
    if not isinstance(text, str):
        return ""
    # Drop common PDF page furniture: "Page 3", "3 of 12", bare page numbers, form feeds.
    text = re.sub(r"\f", "\n", text)
    text = re.sub(r"(?im)^\s*page\s+\d+(\s+of\s+\d+)?\s*$", " ", text)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", " ", text)
    text = text.replace("�", "'")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language(text: str, default: str = "en") -> str:
    """Return 'rw' or 'en' for a chunk (heuristic; langdetect has no rw)."""
    tokens = re.findall(r"[a-z']+", text.lower())
    if tokens:
        hits = sum(1 for t in tokens if t in _RW_MARKERS)
        if hits >= 2 or (hits / len(tokens)) > 0.12:
            return "rw"
    try:
        from langdetect import detect

        code = detect(text)
        return "en" if code == "en" else default
    except Exception:
        return default


def assign_topic(text: str, default: str = "general_srh") -> str:
    """Tag a chunk with the best-matching SRH topic (keyword heuristic)."""
    best, best_n = None, 0
    for topic, rx in _TOPIC_RE.items():
        n = len(rx.findall(text))
        if n > best_n:
            best, best_n = topic, n
    return best or default


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def chunk_document(
    text: str,
    source: str,
    title: Optional[str] = None,
    default_topic: str = "general_srh",
    default_lang: Optional[str] = None,
) -> List[dict]:
    """Clean + split a document into metadata-tagged chunk dicts (no embedding)."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    cleaned = clean_text(text)
    if not cleaned:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    now = datetime.now(timezone.utc).isoformat()
    chunks = []
    for i, piece in enumerate(splitter.split_text(cleaned)):
        piece = piece.strip()
        if len(piece) < 20:
            continue
        h = _hash(piece)
        lang = default_lang or detect_language(piece)
        topic = assign_topic(piece, default_topic)
        chunks.append({
            "id": h,
            "text": piece,
            "metadata": {
                "source": source,
                "title": title,
                "topic": topic,
                "language": lang,
                "chunk_id": f"{source}:{i}",
                "date_ingested": now,
            },
        })
    return chunks


def _cache_path(source: str) -> str:
    os.makedirs(KB_CACHE_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", source)[:80]
    return os.path.join(KB_CACHE_DIR, f"{safe}.jsonl")


def ingest_chunks(
    chunks: List[dict],
    db: SASession,
    embedder=None,
    store=None,
) -> dict:
    """Embed + upsert + persist new chunks. Idempotent by chunk hash.

    ``embedder`` / ``store`` default to the English (MiniLM / default index)
    singletons. Kinyarwanda seed scripts pass ``get_rw_embedding_model()`` +
    ``get_rw_vector_store()`` (bge-m3, 1024-d, ``srh-knowledge-base-rw``) so the
    English embedder and index are never touched.

    Returns a report: {ingested, skipped, per_topic, per_language, source}.
    """
    from app.ml.embeddings import get_embedding_model
    from app.services.vector_store import get_vector_store

    if embedder is None:
        embedder = get_embedding_model()
    if store is None:
        store = get_vector_store()

    report = {"ingested": 0, "skipped": 0, "per_topic": {}, "per_language": {}}
    if not chunks:
        return report

    # Idempotency: drop chunks whose hash already exists (in this batch or DB).
    seen, unique = set(), []
    for c in chunks:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        unique.append(c)
    existing = set(
        db.scalars(
            select(KnowledgeEntry.chunk_hash).where(
                KnowledgeEntry.chunk_hash.in_([c["id"] for c in unique])
            )
        ).all()
    )
    new = [c for c in unique if c["id"] not in existing]
    report["skipped"] = len(chunks) - len(new)
    if not new:
        return report

    # Embed + upsert to the vector store.
    embeddings = embedder.embed_documents([c["text"] for c in new])
    for c, emb in zip(new, embeddings):
        c["embedding"] = emb
    store.upsert(new)

    # Persist relational rows + JSONL cache.
    cache_lines = []
    for c in new:
        meta = c["metadata"]
        db.add(KnowledgeEntry(
            title=meta.get("title"),
            content=c["text"],
            lang=meta.get("language"),
            topic=meta.get("topic"),
            source=meta.get("source"),
            pinecone_id=c["id"],
            chunk_hash=c["id"],
        ))
        report["ingested"] += 1
        report["per_topic"][meta["topic"]] = report["per_topic"].get(meta["topic"], 0) + 1
        report["per_language"][meta["language"]] = (
            report["per_language"].get(meta["language"], 0) + 1
        )
        cache_lines.append(json.dumps(
            {"id": c["id"], "text": c["text"], **meta}, ensure_ascii=False
        ))
    db.commit()

    if new:
        src = new[0]["metadata"]["source"]
        with open(_cache_path(src), "a", encoding="utf-8") as fh:
            fh.write("\n".join(cache_lines) + "\n")
        report["source"] = src
    return report


def ingest_rw_chunks(chunks: List[dict], db: SASession) -> dict:
    """Ingest Kinyarwanda chunks with the bge-m3 embedder + the RW index.

    Thin wrapper over ``ingest_chunks`` that wires the Kinyarwanda embedder and
    vector store, so RW seed scripts never risk hitting the English index.
    """
    from app.ml.embeddings import get_rw_embedding_model
    from app.services.vector_store import get_rw_vector_store

    return ingest_chunks(
        chunks, db, embedder=get_rw_embedding_model(), store=get_rw_vector_store()
    )


def ingest_text_document(
    text: str, source: str, db: SASession, title: Optional[str] = None,
    default_topic: str = "general_srh", default_lang: Optional[str] = None,
    embedder=None, store=None,
) -> dict:
    """Convenience: chunk a raw text document and ingest it in one call."""
    chunks = chunk_document(text, source, title, default_topic, default_lang)
    report = ingest_chunks(chunks, db, embedder=embedder, store=store)
    report["total_chunks"] = len(chunks)
    return report
