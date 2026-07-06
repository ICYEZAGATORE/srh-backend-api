"""tests/test_knowledge_ingestion.py — chunk → embed → upsert (Chroma, offline).

Builds a tiny in-memory PDF (no extra deps) and runs it through the real
ingestion pipeline against the keyless Chroma backend + in-memory SQLite.
"""

import io

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database import Base
from app.models.knowledge import KnowledgeEntry
from app.services.ingestion import ingest_text_document


def _make_pdf(text: str) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = ("BT /F1 12 Tf 72 720 Td (" + text + ") Tj ET").encode("latin-1")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(str(i).encode() + b" 0 obj\n" + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n")
    for off in offsets:
        out.write(("%010d 00000 n \n" % off).encode())
    out.write(b"trailer\n<< /Size " + str(len(objs) + 1).encode()
              + b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF")
    return out.getvalue()


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


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


SAMPLE = (
    "Contraception and condoms help prevent pregnancy and STIs. "
    "HIV testing is free at health centres. Family planning options include "
    "the pill, the implant, and the IUD. Consent is essential in relationships."
)


def test_ingest_single_pdf_chunk_count(db):
    text = _pdf_text(_make_pdf(SAMPLE))
    report = ingest_text_document(text, source="test.pdf", db=db, title="test.pdf")
    assert report["total_chunks"] >= 1
    assert report["ingested"] == report["total_chunks"]
    rows = db.scalar(select(func.count()).select_from(KnowledgeEntry))
    assert rows == report["ingested"]


def test_ingestion_is_idempotent(db):
    text = _pdf_text(_make_pdf(SAMPLE))
    first = ingest_text_document(text, source="test.pdf", db=db)
    second = ingest_text_document(text, source="test.pdf", db=db)
    # Second run finds every chunk already present -> nothing new inserted.
    assert second["ingested"] == 0
    assert second["skipped"] == second["total_chunks"] == first["total_chunks"]
    rows = db.scalar(select(func.count()).select_from(KnowledgeEntry))
    assert rows == first["ingested"]
