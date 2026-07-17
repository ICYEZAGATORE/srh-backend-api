"""
scripts/build_faq_cache.py — Build the Kinyarwanda FAQ cache (offline, one-time).

Reads the curated predefined-question dataset and writes a self-contained JSONL
cache (question + pre-approved answer + precomputed bge-m3 embedding) that
``app/services/faq_cache.py`` loads at runtime. Precomputing here means the live
service never runs a startup embed storm on the 512 MB free tier.

Source
------
``data/knowledge_base/Kinyarwanda_Q_A.pdf.jsonl`` — one record per Q&A pair:
    ``title`` = the question (rw); ``text`` = question + answer fused (rw).
The answer is derived by stripping the ``title`` prefix from ``text`` (falling
back to the full ``text`` if the prefix does not match). ``approved`` is carried
through verbatim — every row is currently ``approved=false`` (unreviewed), which
the runtime surfaces as an ``unreviewed`` flag in the logs.

Embeddings use the SAME rw model as retrieval (bge-m3, via
``get_rw_embedding_model``) so query/cache vectors are comparable.

Usage
-----
    # Local build (loads bge-m3 locally; needs sentence-transformers + torch):
    EMBEDDING_BACKEND=local python -m scripts.build_faq_cache

    # Or force the HF Inference API for embeddings (needs HF_API_TOKEN):
    EMBEDDING_BACKEND=hf_api HF_API_TOKEN=... python -m scripts.build_faq_cache

    python -m scripts.build_faq_cache --dry-run   # parse + counts only, no embed
"""

from __future__ import annotations

import argparse
import json
import sys

try:  # UTF-8 stdout for Kinyarwanda text on Windows consoles.
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # noqa: BLE001
    pass

from app.config import settings

DEFAULT_SOURCE = "data/knowledge_base/Kinyarwanda_Q_A.pdf.jsonl"


def _derive_answer(title: str, text: str) -> str:
    """Return the answer portion of ``text`` (question + answer fused).

    Strips the leading question (``title``) and a following ``?``/whitespace.
    Falls back to the full ``text`` if the title is not a clean prefix.
    """
    title = (title or "").strip()
    text = (text or "").strip()
    if title and text.startswith(title):
        answer = text[len(title):].lstrip(" ?؟\t\n").strip()
        if answer:
            return answer
    return text


def load_pairs(source: str) -> list[dict]:
    pairs = []
    with open(source, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if (row.get("language") or "rw") != "rw":
                continue
            question = (row.get("title") or "").strip()
            answer = _derive_answer(question, row.get("text", ""))
            if not question or not answer:
                continue
            pairs.append(
                {
                    "question_rw": question,
                    "answer_rw": answer,
                    "topic": row.get("topic"),
                    "approved": bool(row.get("approved", False)),
                }
            )
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Kinyarwanda FAQ cache.")
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="input JSONL (rw Q&A)")
    ap.add_argument("--out", default=settings.FAQ_CACHE_PATH, help="output JSONL cache")
    ap.add_argument("--dry-run", action="store_true", help="parse only; no embedding")
    args = ap.parse_args()

    pairs = load_pairs(args.source)
    approved = sum(1 for p in pairs if p["approved"])
    print(f"Parsed {len(pairs)} rw Q&A pairs from {args.source} "
          f"({approved} approved, {len(pairs) - approved} unreviewed).")
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
