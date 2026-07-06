"""
scripts/dev_seed_vector_store.py — DEV/TEST ONLY vector-store seeding.

Populates the active vector store from the srh-ml-model *staged* knowledge base
so end-to-end RAG retrieval can be exercised BEFORE the human review/approval
pass has run. Every vector is tagged ``approved=false`` /
``review_status="auto_test_unapproved"`` so this content is unmistakably
provisional and can be deleted/replaced once real approval happens.

It embeds with the backend's OWN SRHEmbeddingModel and upserts via the backend
VectorStoreClient, so document vectors live in the same space the query path
uses (paraphrase-multilingual-MiniLM-L12-v2, 384-dim).

NOT a substitute for the review gate. Do not treat seeded content as approved.

Usage:
    python -m scripts.dev_seed_vector_store            # seed (idempotent)
    python -m scripts.dev_seed_vector_store --dry-run  # count only, no upsert
    python -m scripts.dev_seed_vector_store --purge    # delete only seeded ids
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.config import settings
from app.ml.embeddings import get_embedding_model
from app.services.vector_store import get_vector_store

# Staged JSONL produced by the ingestion pipeline (unreviewed).
STAGED = Path(
    r"C:/Users/USER/srh-ml-model/data/knowledge_base/knowledge_base_staging.jsonl"
)

# Drop obvious non-content (site nav, licensing, reference boilerplate). This is
# a light hygiene filter for test signal, NOT the clinical review.
_BOILERPLATE = re.compile(
    r"\.gov means|Browse Titles|Advanced Help|NCBI Bookshelf|Skip to|"
    r"Some rights reserved|Creative Commons|Sales, rights and licensing|"
    r"All references were accessed|Turn recording|newsletter",
    re.I,
)


def _load_chunks() -> list[dict]:
    records = [json.loads(line) for line in STAGED.open(encoding="utf-8")]
    chunks = []
    for r in records:
        text = (r.get("text") or "").strip()
        if len(text) < 150 or _BOILERPLATE.search(text):
            continue
        tags = r.get("topic_tags") or []
        if not isinstance(tags, list):
            tags = str(tags).split(";")
        topic = (tags[0] if tags else "general_srh") or "general_srh"
        chunks.append(
            {
                "id": r["chunk_id"],
                "text": text,
                "metadata": {
                    "topic": topic,
                    "language": r.get("language", "en"),
                    "title": r.get("doc_title"),
                    "section": r.get("section"),
                    "source": r.get("source"),
                    "source_org": r.get("source_org"),
                    "source_url": r.get("source_url"),
                    # provenance flags — this content is NOT approved.
                    "approved": False,
                    "review_status": "auto_test_unapproved",
                    "requires_clinical_review": True,
                },
            }
        )
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--purge", action="store_true")
    args = ap.parse_args()

    chunks = _load_chunks()
    store = get_vector_store()
    print(f"backend={settings.VECTOR_STORE_BACKEND} "
          f"index={settings.PINECONE_INDEX_NAME} candidate_chunks={len(chunks)}")

    if args.purge:
        store.delete([c["id"] for c in chunks])
        print(f"purged {len(chunks)} seeded ids")
        return

    if args.dry_run:
        print("dry-run: nothing upserted")
        return

    emb = get_embedding_model()
    vectors = emb.embed_documents([c["text"] for c in chunks])
    for c, v in zip(chunks, vectors):
        c["embedding"] = v
    store.upsert(chunks)
    print(f"upserted {len(chunks)} chunks (approved=false, auto_test_unapproved)")


if __name__ == "__main__":
    main()
