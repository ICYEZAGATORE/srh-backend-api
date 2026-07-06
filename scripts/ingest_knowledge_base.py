"""
scripts/ingest_knowledge_base.py — Build the SRH knowledge base.

Sources (Part 3.1) — all open-access, authoritative or reused-from-project:
  a. WHO SRH guideline PDFs           (best-effort programmatic download)
  b. Rwanda MoH SRH protocols         (manual — no stable programmatic endpoint)
  c. UNFPA SRH resources              (manual / best-effort)
  d. Project SRH Q&A seed text        (reused from the topic-classifier dataset:
                                       AfriMedQA / HealthCareMagic / MedMCQA)

The script:
  * downloads what it can (logs URL, date, license/status),
  * ingests any PDFs found under data/knowledge_base/sources/,
  * always ingests the reused project seed text so the index is non-empty,
  * for anything it cannot fetch, prints a MANUAL-DOWNLOAD manifest telling you
    exactly what to place where — it never fabricates health content,
  * is idempotent (sha-256 chunk hashes; safe to re-run),
  * prints a completion report: total chunks, per-topic, per-language, failures.

Run:
    python -m scripts.ingest_knowledge_base            # all sources
    python -m scripts.ingest_knowledge_base --reset    # wipe + rebuild
    python -m scripts.ingest_knowledge_base --only seed_project_srh
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import sys
import urllib.request

from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401 register tables
from app.services.ingestion import chunk_document, ingest_chunks, KB_CACHE_DIR

SOURCES_DIR = os.path.join(KB_CACHE_DIR, "sources")
TODAY = _dt.date.today().isoformat()

# ── (a) WHO / (c) UNFPA best-effort web PDFs ────────────────────────────────
# Direct PDF links change often; each is attempted and, on failure, reported as
# a manual-download item. License: WHO/UNFPA publications are open-access (CC BY-NC-SA).
WEB_PDFS = [
    {
        "source_id": "who_adolescent_srhr",
        "title": "WHO — Adolescent sexual and reproductive health",
        "url": "https://iris.who.int/bitstream/handle/10665/44174/9789241598842_eng.pdf",
        "default_topic": "general_srh", "default_lang": "en",
        "license": "WHO open-access (CC BY-NC-SA 3.0 IGO)",
    },
    {
        "source_id": "who_contraception",
        "title": "WHO — Family planning / contraception handbook",
        "url": "https://iris.who.int/bitstream/handle/10665/44028/9780978856373_eng.pdf",
        "default_topic": "contraception", "default_lang": "en",
        "license": "WHO open-access (CC BY-NC-SA 3.0 IGO)",
    },
]

# ── (b)(c) Manual-only sources: no stable programmatic endpoint ─────────────
MANUAL_SOURCES = [
    ("Rwanda MoH — Adolescent SRH / Family Planning protocols",
     "https://www.moh.gov.rw/ (search: adolescent health, family planning)",
     "rwanda_moh_srh.pdf"),
    ("UNFPA — SRH for sub-Saharan Africa (adolescents & PWDs)",
     "https://esaro.unfpa.org/en/publications",
     "unfpa_srh_africa.pdf"),
]


def _download(url: str, dest: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "srh-kb-ingest/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data[:4] == b"%PDF":
            return False
        with open(dest, "wb") as fh:
            fh.write(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"    download failed: {exc}")
        return False


def _pdf_text(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _resolve_seed_csv() -> str | None:
    candidates = [
        os.path.join("..", "srh-ml-model", "data", "Topic_Classifier_data",
                     "topic_labels_full.csv"),
        os.path.join(os.path.expanduser("~"), "srh-ml-model", "data",
                     "Topic_Classifier_data", "topic_labels_full.csv"),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def ingest_seed_project_srh(db, limit_per_topic: int = 120) -> dict:
    """Reuse the topic-classifier dataset's English SRH text as seed Q&A content."""
    import pandas as pd

    path = _resolve_seed_csv()
    if not path:
        print("  seed CSV not found (srh-ml-model topic dataset) — skipping seed.")
        return {"ingested": 0, "skipped": 0, "per_topic": {}, "per_language": {}}

    df = pd.read_csv(path)
    total = {"ingested": 0, "skipped": 0, "per_topic": {}, "per_language": {}}
    for topic, group in df.groupby("topic"):
        sample = group["text"].dropna().astype(str).head(limit_per_topic).tolist()
        doc = "\n\n".join(sample)
        chunks = chunk_document(
            doc, source="project_srh_seed", title=f"SRH seed — {topic}",
            default_topic=str(topic), default_lang="en",
        )
        rep = ingest_chunks(chunks, db)
        total["ingested"] += rep["ingested"]
        total["skipped"] += rep["skipped"]
        for k, v in rep["per_topic"].items():
            total["per_topic"][k] = total["per_topic"].get(k, 0) + v
        for k, v in rep["per_language"].items():
            total["per_language"][k] = total["per_language"].get(k, 0) + v
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest the SRH knowledge base.")
    ap.add_argument("--only", help="Ingest only this source_id.")
    ap.add_argument("--reset", action="store_true",
                    help="Delete existing knowledge rows + vectors first.")
    ap.add_argument("--limit-seed", type=int, default=120,
                    help="Max seed rows per topic (default 120).")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)  # dev convenience (sqlite)
    os.makedirs(SOURCES_DIR, exist_ok=True)
    db = SessionLocal()

    if args.reset:
        from app.models.knowledge import KnowledgeEntry
        from app.services.vector_store import get_vector_store
        ids = [e.pinecone_id for e in db.query(KnowledgeEntry).all() if e.pinecone_id]
        if ids:
            try:
                get_vector_store().delete(ids)
            except Exception as exc:  # noqa: BLE001
                print(f"  vector delete warning: {exc}")
        db.query(KnowledgeEntry).delete()
        db.commit()
        print(f"  reset: cleared {len(ids)} vectors + knowledge rows.")

    grand = {"ingested": 0, "skipped": 0, "per_topic": {}, "per_language": {}}
    failures: list[str] = []

    def _merge(rep):
        grand["ingested"] += rep.get("ingested", 0)
        grand["skipped"] += rep.get("skipped", 0)
        for k, v in rep.get("per_topic", {}).items():
            grand["per_topic"][k] = grand["per_topic"].get(k, 0) + v
        for k, v in rep.get("per_language", {}).items():
            grand["per_language"][k] = grand["per_language"].get(k, 0) + v

    # (a)(c) Web PDFs — best-effort download then ingest.
    for src in WEB_PDFS:
        if args.only and src["source_id"] != args.only:
            continue
        dest = os.path.join(SOURCES_DIR, f"{src['source_id']}.pdf")
        print(f"\n[web] {src['title']}\n    url: {src['url']}\n    retrieved: {TODAY} "
              f"| license: {src['license']}")
        if not os.path.exists(dest) and not _download(src["url"], dest):
            failures.append(f"{src['source_id']}: {src['url']}")
            continue
        try:
            text = _pdf_text(dest)
            rep = ingest_chunks(
                chunk_document(text, source=src["source_id"], title=src["title"],
                               default_topic=src["default_topic"],
                               default_lang=src["default_lang"]), db)
            _merge(rep)
            print(f"    ingested {rep['ingested']} chunks (skipped {rep['skipped']}).")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{src['source_id']}: parse error {exc}")

    # Any user-provided PDFs dropped into data/knowledge_base/sources/.
    for pdf in glob.glob(os.path.join(SOURCES_DIR, "*.pdf")):
        sid = os.path.splitext(os.path.basename(pdf))[0]
        if args.only and sid != args.only:
            continue
        if any(s["source_id"] == sid for s in WEB_PDFS):
            continue  # already handled above
        print(f"\n[local] {pdf}")
        try:
            rep = ingest_chunks(
                chunk_document(_pdf_text(pdf), source=sid, title=sid), db)
            _merge(rep)
            print(f"    ingested {rep['ingested']} chunks (skipped {rep['skipped']}).")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{sid}: parse error {exc}")

    # (d) Project seed SRH text — reliable, always available.
    if not args.only or args.only == "seed_project_srh":
        print("\n[seed] project SRH Q&A text (reused topic-classifier dataset)")
        _merge(ingest_seed_project_srh(db, args.limit_seed))

    # ── Report ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("KNOWLEDGE BASE INGESTION — REPORT")
    print("=" * 60)
    print(f"  Total chunks ingested : {grand['ingested']}")
    print(f"  Skipped (duplicates)  : {grand['skipped']}")
    print(f"  Per topic   : {grand['per_topic']}")
    print(f"  Per language: {grand['per_language']}")
    if failures:
        print(f"\n  Failed web downloads ({len(failures)}):")
        for f in failures:
            print(f"    - {f}")
    print("\n  MANUAL sources to add (place the PDF in "
          f"{SOURCES_DIR}/ then re-run):")
    for title, where, fname in MANUAL_SOURCES:
        print(f"    - {title}\n        get from: {where}\n        save as : "
              f"{os.path.join(SOURCES_DIR, fname)}")
    db.close()
    if grand["ingested"] == 0 and not args.only:
        sys.exit("No chunks ingested — check sources.")


if __name__ == "__main__":
    main()
