"""
scripts/ingest_rw_web_sources.py — Ingest 9 authoritative Rwandan SRH web
sources (3 PDFs + 6 HTML articles) into the RAG knowledge base.

These are real, sourced documents (RBC, Haguruka, Rwanda Magazine, Ni Nyampinga /
Girl Effect) — NOT fabricated content. Unlike the cyberrwanda pages, they fetch
programmatically, so this script downloads + extracts + chunks + ingests them.

Chunking: these are prose articles/manuals (not Q&A), so the shared
``chunk_document`` (RecursiveCharacterTextSplitter 500/50) is the right tool —
with per-source ``default_topic`` (the topic keyword heuristic is English-only,
so RW chunks fall back to the source's declared topic) and PER-CHUNK language
auto-detection (RW sources -> rw, the English HIV manual -> en).

Every chunk is tagged (vector metadata) ``approved=false`` /
``review_status="auto_test_unapproved"`` / ``requires_clinical_review=true`` and
carries its ``source_url`` — identical staging convention to
``scripts.dev_seed_vector_store`` and ``scripts.ingest_kinyarwanda_docs``. The
relational row's ``reviewed_by`` stays NULL. This does NOT skip clinical review.

Ingestion only — no retrieval/generation/safety-logic changes.

Usage
-----
    python -m scripts.ingest_rw_web_sources --dry-run   # fetch+chunk+counts only
    python -m scripts.ingest_rw_web_sources             # embed + upsert
    python -m scripts.ingest_rw_web_sources --smoke     # + RW retrieval check

Verify locally without touching the deployed Pinecone index:
    VECTOR_STORE_BACKEND=chroma EMBEDDING_BACKEND=local \
    CHROMA_PERSIST_DIR=./data/chroma_dev \
    DATABASE_URL=sqlite:///./data/kb_dev.sqlite \
    python -m scripts.ingest_rw_web_sources --smoke
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # noqa: BLE001
    pass

from app.services.ingestion import chunk_document, ingest_chunks

# (source_id, url, kind, default_topic, title)
SOURCES: list[tuple[str, str, str, str, str]] = [
    ("rbc_asrhr_15_24", "https://rbc.gov.rw/compass/wp-content/uploads/asrhr_image_box_15-24_yrs.pdf",
     "pdf", "general_srh", "RBC — Adolescent SRH (15–24 yrs) image box"),
    ("haguruka_asrh_oosc",
     "https://haguruka.org.rw/wp-content/uploads/2022/05/Inyoborabiganiro-kubuzima-bwImyororokere-mu-rubyiruko-rutari-mu-mashuri..pdf",
     "pdf", "general_srh", "Haguruka — Inyoborabiganiro ku buzima bw'imyororokere mu rubyiruko rutari mu mashuri"),
    ("rbc_hiv_aids_rh_manual",
     "https://www.rbc.gov.rw/library/sites/default/files/Training%20Manual%20HIV-AIDS-RH%2010-08-10.pdf",
     "pdf", "sti_hiv", "RBC — HIV/AIDS & Reproductive Health Training Manual"),
    ("rwmag_imihango_iminsi_myinshi",
     "https://rwandamagazine.com/ubuzima/article/ni-iki-gitera-imihango-imara-iminsi-myinshi",
     "html", "puberty", "Rwanda Magazine — Ni iki gitera imihango imara iminsi myinshi"),
    ("rwmag_4_new_stis",
     "https://rwandamagazine.com/ubuzima/article/indwara-enye-4-nshya-zandurira-mu-mibonano-mpuzabitsina-zihangayikishije",
     "html", "sti_hiv", "Rwanda Magazine — Indwara enye nshya zandurira mu mibonano mpuzabitsina"),
    ("rwmag_infections_vaginales",
     "https://rwandamagazine.com/ubuzima/article/bimwe-mu-bimenyetso-biranga-indwara-za-infections-vaginales-ku-bagore-9627",
     "html", "sti_hiv", "Rwanda Magazine — Ibimenyetso by'indwara za infections vaginales ku bagore"),
    ("rwmag_uti_prevention",
     "https://rwandamagazine.com/ubuzima/article/uko-wakwirinda-indwara-yo-kokerwa-n-inkari-9441",
     "html", "general_srh", "Rwanda Magazine — Uko wakwirinda indwara yo kokerwa n'inkari (UTI)"),
    ("ninyampinga_imihango_7",
     "https://www.ninyampinga.com/rw/sections/baza-shangazi/ibintu-birindwi-ukeneye-kumenya-ku-byerekeye-imihango/",
     "html", "puberty", "Ni Nyampinga — Ibintu birindwi ukeneye kumenya ku byerekeye imihango"),
    ("ninyampinga_ubugimbi_ipfunwe",
     "https://www.ninyampinga.com/rw/sections/baza-shangazi/kuki-numva-ntewe-ipfunwe-nubugimbi/",
     "html", "puberty", "Ni Nyampinga — Kuki numva ntewe ipfunwe n'ubugimbi"),
]

_UA = "Mozilla/5.0 (srh-kb-ingest/1.0)"

# HTML <p> paragraphs that are site furniture, not article content.
_HTML_SKIP = re.compile(
    r"Photo\s*:|ohereza ikibazo cyawe kuri email|Girl Effect|"
    r"Uburenganzira burihariye|Murakoze kubwikiganiro|©|rights reserved|"
    r"Subscribe|Newsletter|Follow us",
    re.I,
)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _pdf_text(raw: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _html_text(raw: bytes) -> str:
    """Extract readable article text from <p> elements (no HTML parser dep)."""
    doc = raw.decode("utf-8", errors="replace")
    # Drop scripts/styles first so their contents never leak into <p> capture.
    doc = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", doc)
    parts: list[str] = []
    for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", doc):
        txt = html.unescape(re.sub(r"(?s)<[^>]+>", "", p)).strip()
        if len(txt) >= 40 and not _HTML_SKIP.search(txt):
            parts.append(txt)
    return "\n\n".join(parts)


def _extract(source_id: str, url: str, kind: str) -> tuple[str, str | None]:
    """Return (text, error). error is a short string if extraction was thin."""
    try:
        raw = _fetch(url)
    except Exception as exc:  # noqa: BLE001
        return "", f"fetch failed: {exc}"
    try:
        text = _pdf_text(raw) if kind == "pdf" else _html_text(raw)
    except Exception as exc:  # noqa: BLE001
        return "", f"extract failed: {exc}"
    if len(text.strip()) < 200:
        # Image-only/scanned PDFs (e.g. an "image box" poster) yield ~no text.
        return text, f"only {len(text.strip())} chars extracted (scanned/image?)"
    return text, None


def _low_quality(text: str) -> bool:
    """True for table-of-contents / page-number / dot-leader junk chunks.

    PDF ToC lines (e.g. "INTANGIRIRO ……3 GUSHIMIRA ……4") and number tables
    carry no health content and mislead retrieval. Real prose is letter-dense;
    ToC/index lines are dominated by dots, digits and whitespace.
    """
    s = text.strip()
    if len(s) < 40:
        return True
    letters = sum(ch.isalpha() for ch in s)
    if letters / len(s) < 0.60:            # dot-leaders, number tables, indexes
        return True
    if re.search(r"\.{4,}", s) or s.count("…") >= 2:   # ToC dot-leader signature
        return True
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# The two large facilitation manuals — held back from the first production seed
# for clinical review (real SRH content mixed with training scaffolding).
HEAVY_MANUALS = {"haguruka_asrh_oosc", "rbc_hiv_aids_rh_manual"}


def build_all_chunks(
    include: set[str] | None = None, exclude: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Fetch + chunk sources. Optionally restrict via include/exclude source_ids."""
    now = _now()
    all_chunks: list[dict] = []
    notes: list[str] = []
    for source_id, url, kind, topic, title in SOURCES:
        if include and source_id not in include:
            continue
        if exclude and source_id in exclude:
            notes.append(f"[hold] {source_id}: excluded from this run")
            continue
        text, err = _extract(source_id, url, kind)
        if not text.strip():
            notes.append(f"[SKIP] {source_id}: {err}")
            continue
        if err:
            notes.append(f"[WARN] {source_id}: {err}")
        # All 9 sources are Kinyarwanda-language documents, so force lang=rw.
        # (The heuristic detector misfires on chunks dense with French/Latin
        # medical terms — "Prostate", "Épididyme" — or citations, mislabelling
        # genuine Kinyarwanda health content as "en" and hiding it from RW
        # retrieval. Per-source default topic still applies.)
        raw_chunks = chunk_document(
            text, source=source_id, title=title,
            default_topic=topic, default_lang="rw",
        )
        # Drop ToC / page-number / dot-leader junk (common in the PDF manuals).
        chunks = [c for c in raw_chunks if not _low_quality(c["text"])]
        dropped = len(raw_chunks) - len(chunks)
        for c in chunks:
            c["metadata"]["source_url"] = url
            c["metadata"]["date_ingested"] = now
            c["metadata"]["approved"] = False
            c["metadata"]["review_status"] = "auto_test_unapproved"
            c["metadata"]["requires_clinical_review"] = True
        all_chunks.extend(chunks)
        langs = {}
        for c in chunks:
            langs[c["metadata"]["language"]] = langs.get(c["metadata"]["language"], 0) + 1
        notes.append(f"[ok]   {source_id}: {len(chunks)} chunks (dropped {dropped} junk), "
                     f"lang={langs}, topic~={topic}")
    return all_chunks, notes


def _summary(chunks: list[dict]) -> None:
    from collections import Counter
    print("  chunks total :", len(chunks))
    print("  per source   :", dict(Counter(c["metadata"]["source"] for c in chunks)))
    print("  per topic    :", dict(Counter(c["metadata"]["topic"] for c in chunks)))
    print("  per language :", dict(Counter(c["metadata"]["language"] for c in chunks)))


def _smoke(db) -> None:
    from app.ml.embeddings import retrieve_context
    queries = [
        ("Imihango imara iminsi myinshi bitewe n'iki?", "puberty"),
        ("Ni izihe ndwara zandurira mu mibonano mpuzabitsina?", "sti_hiv"),
        ("Nakwirinda nte indwara yo kokerwa n'inkari?", "general_srh"),
        ("Kuki numva ntewe ipfunwe n'ubugimbi?", "puberty"),
    ]
    print("\nRW retrieval smoke test (lang=rw):")
    ok = True
    for q, topic in queries:
        hits = retrieve_context(q, "rw", top_k=3, topic=topic) or retrieve_context(q, "rw", top_k=3)
        ok = ok and bool(hits)
        top = f"{hits[0]['score']:.3f} {str(hits[0].get('title'))[:46]!r}" if hits else "(0)"
        print(f"  {'OK ' if hits else '!! '}[{topic:11}] {q[:44]!r} -> {len(hits)} hit(s); {top}")
    print("SMOKE:", "PASS" if ok else "FAIL")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest 9 Rwandan SRH web sources.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", help="Comma-separated source_ids to include.")
    ap.add_argument("--exclude", help="Comma-separated source_ids to skip.")
    ap.add_argument("--exclude-heavy", action="store_true",
                    help="Skip the two large facilitation manuals (Haguruka + HIV manual).")
    args = ap.parse_args()

    include = set(args.only.split(",")) if args.only else None
    exclude = set(args.exclude.split(",")) if args.exclude else set()
    if args.exclude_heavy:
        exclude |= HEAVY_MANUALS

    print("=" * 64)
    print("RW WEB SOURCES INGESTION — fetch + chunk")
    print("=" * 64)
    chunks, notes = build_all_chunks(include=include, exclude=exclude or None)
    for n in notes:
        print(" ", n)
    print()
    _summary(chunks)

    if args.dry_run:
        print("\ndry-run: nothing embedded or upserted.")
        return

    from app.database import Base, SessionLocal, engine
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        rep = ingest_chunks(chunks, db)
        print("\nINGESTION REPORT")
        print(f"  ingested={rep['ingested']} skipped={rep['skipped']}")
        print(f"  per_topic={rep['per_topic']}")
        print(f"  per_language={rep['per_language']}")
        if args.smoke:
            _smoke(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
