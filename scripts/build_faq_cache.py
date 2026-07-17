"""
scripts/build_faq_cache.py — Build the Kinyarwanda FAQ cache (offline, one-time).

Parses the curated predefined-question document **directly from the source PDF**
and writes a self-contained JSONL cache (question + pre-approved answer +
precomputed bge-m3 embedding) that ``app/services/faq_cache.py`` loads at
runtime. Precomputing here means the live service never runs a startup embed
storm on the 512 MB free tier.

Source of truth
---------------
``data/Kinyarwanda Q&A.pdf`` — an ``IBIBAZO N'IBISUBIZO:`` (Questions & Answers)
document where each pair is a bullet::

    ● <question ending in '?'> <the pre-approved answer, until the next bullet>

The parser splits on the ``●`` bullet, takes the text up to the first ``?`` as
``question_rw`` and the remainder as ``answer_rw`` — a direct question→answer
mapping with **no fused-text / prefix-strip heuristic**. Text is NFKC-normalised
so PDF ligatures (e.g. ``ﬁ`` → ``fi``) don't leak into the stored answers.

Notes
-----
- The PDF is the source of truth for the Q&A *content and count*. The document
  itself repeats one bullet verbatim, so pairs are de-duplicated by question
  (first occurrence wins); the true unique count is reported.
- ``topic`` is metadata only (returned for analytics; NOT used for matching). It
  is enriched by matching each question against the prior curated topic labels
  in ``--topic-source`` (default: the legacy KB JSONL), falling back to
  ``general_srh``. No Q&A *content* is taken from that file.
- ``approved`` is written as ``false`` for every row (unreviewed), matching the
  current review state. Serving logic ignores this field; it is an honest record
  of review status that a clinician can flip per-row later.
- Malformed segments (no ``?`` or an empty answer) are skipped and logged.

Usage
-----
    # Local build (loads bge-m3 locally; needs sentence-transformers + torch):
    EMBEDDING_BACKEND=local python -m scripts.build_faq_cache

    # Or force the HF Inference API for embeddings (matches the Render runtime):
    EMBEDDING_BACKEND=hf_api HF_API_TOKEN=... python -m scripts.build_faq_cache

    python -m scripts.build_faq_cache --dry-run   # parse + counts only, no embed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

try:  # UTF-8 stdout for Kinyarwanda text on Windows consoles.
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # noqa: BLE001
    pass

from app.config import settings

DEFAULT_SOURCE = "data/Kinyarwanda Q&A.pdf"
DEFAULT_TOPIC_SOURCE = "data/knowledge_base/Kinyarwanda_Q_A.pdf.jsonl"
BULLET = "●"  # ● — the Q&A delimiter in the source document
DEFAULT_TOPIC = "general_srh"
# Leading document heading that precedes the first question.
_HEADING_RE = re.compile(r"^IBIBAZO\s+N['’]IBISUBIZO:?\s*")


def _normalize(text: str) -> str:
    """NFKC-normalise (de-ligature) and collapse all whitespace to single spaces."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def _norm_key(q: str) -> str:
    """Normalised key for de-duplication / topic matching."""
    return _normalize(q).lower()


def _load_topic_map(topic_source: str) -> dict:
    """Best-effort {normalised-question -> topic} from prior curated labels.

    Metadata only; never a source of Q&A content. Missing file -> empty map.
    """
    import os

    if not topic_source or not os.path.exists(topic_source):
        return {}
    tmap: dict = {}
    try:
        with open(topic_source, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                title = row.get("title")
                if title and row.get("topic"):
                    tmap[_norm_key(title)] = row["topic"]
    except Exception as exc:  # noqa: BLE001 - enrichment is optional
        print(f"WARN: could not read topic source {topic_source}: {exc}", file=sys.stderr)
    return tmap


def parse_pdf_pairs(pdf_path: str, topic_source: str = DEFAULT_TOPIC_SOURCE) -> list[dict]:
    """Parse ``● question? answer`` pairs directly from the source PDF.

    Returns de-duplicated (by question) records with topic metadata enriched
    from prior labels. Skips + logs malformed segments.
    """
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    text = _normalize("\n".join((page.extract_text() or "") for page in reader.pages))

    topic_map = _load_topic_map(topic_source)
    segments = [s.strip() for s in text.split(BULLET) if s.strip()]

    pairs: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    for seg in segments:
        qi = seg.find("?")
        if qi == -1:
            # The leading heading segment has no '?'; anything else here is
            # malformed (a stray fragment) — skip and log.
            if not _HEADING_RE.match(seg):
                skipped += 1
                print(f"SKIP (no '?'): {seg[:70]!r}", file=sys.stderr)
            continue
        question = _HEADING_RE.sub("", seg[: qi + 1]).strip()
        answer = seg[qi + 1:].strip()
        if not question or not answer:
            skipped += 1
            print(f"SKIP (empty q/a): {seg[:70]!r}", file=sys.stderr)
            continue
        key = _norm_key(question)
        if key in seen:
            print(f"SKIP (duplicate question in source): {question[:70]!r}",
                  file=sys.stderr)
            continue
        seen.add(key)
        pairs.append({
            "question_rw": question,
            "answer_rw": answer,
            "topic": topic_map.get(key, DEFAULT_TOPIC),
            "approved": False,
        })
    print(f"Parsed {len(pairs)} unique Q&A pairs from {pdf_path} "
          f"({skipped} segment(s) skipped).")
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Kinyarwanda FAQ cache.")
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="input Q&A PDF")
    ap.add_argument("--topic-source", default=DEFAULT_TOPIC_SOURCE,
                    help="optional JSONL of prior topic labels (metadata only)")
    ap.add_argument("--out", default=settings.FAQ_CACHE_PATH, help="output JSONL cache")
    ap.add_argument("--dry-run", action="store_true", help="parse only; no embedding")
    args = ap.parse_args()

    pairs = parse_pdf_pairs(args.source, args.topic_source)
    approved = sum(1 for p in pairs if p["approved"])
    print(f"Unique pairs: {len(pairs)} ({approved} approved, "
          f"{len(pairs) - approved} unreviewed).")
    if not pairs:
        print("No usable pairs found; nothing to build.", file=sys.stderr)
        return 1
    if args.dry_run:
        print("--dry-run: skipping embedding + write.")
        return 0

    # Embed all questions once with the rw model (batched).
    from app.ml.embeddings import get_rw_embedding_model

    model = get_rw_embedding_model()
    print(f"Embedding {len(pairs)} questions with {settings.RW_EMBEDDING_MODEL} "
          f"(backend={model.backend})...")
    vectors = model.embed_documents([p["question_rw"] for p in pairs])

    with open(args.out, "w", encoding="utf-8") as fh:
        for p, vec in zip(pairs, vectors):
            fh.write(json.dumps({**p, "embedding": vec}, ensure_ascii=False) + "\n")

    print(f"Wrote {len(pairs)} rows -> {args.out} (dim={len(vectors[0])}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
