"""
app/routers/admin.py — Protected admin endpoints.

Every route requires a bearer token equal to the ADMIN_API_KEY env var. The
token is verified (via the ``require_admin`` dependency) BEFORE any handler
logic runs.
"""

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SASession

from app.config import settings
from app.database import get_db
from app.models.query import Query
from app.services.ingestion import ingest_text_document

router = APIRouter(prefix="/admin", tags=["Admin"])

_bearer = HTTPBearer(auto_error=True)


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """Reject the request unless the bearer token matches ADMIN_API_KEY."""
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )


@router.get("/analytics", dependencies=[Depends(require_admin)])
def analytics(db: SASession = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(Query)) or 0
    safe = db.scalar(
        select(func.count()).select_from(Query).where(Query.safe.is_(True))
    ) or 0
    unsafe = db.scalar(
        select(func.count()).select_from(Query).where(Query.safe.is_(False))
    ) or 0
    return {
        "total_queries": total,
        "safe_queries": safe,
        "unsafe_queries": unsafe,
    }


def _extract_text(filename: str, raw: bytes) -> str:
    """Return plain text from an uploaded PDF or text/markdown file."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or raw[:4] == b"%PDF":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    # Text / markdown
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


@router.post("/knowledge/upload", dependencies=[Depends(require_admin)])
async def upload_knowledge(
    file: UploadFile = File(...),
    db: SASession = Depends(get_db),
) -> dict:
    """Ingest an uploaded PDF/text file into the knowledge base.

    Runs the same chunk -> embed -> vector-store-upsert pipeline as the bulk
    ingestion script, so new SRH content can be added post-deployment without a
    code change. Returns a summary (chunk count, topic tags, language split).
    Requires the ADMIN_API_KEY bearer token (enforced by ``require_admin``).
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file."
        )
    try:
        text = _extract_text(file.filename, raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {exc}",
        )
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text in the uploaded file.",
        )

    source = f"upload:{file.filename}"
    try:
        report = ingest_text_document(text, source=source, db=db, title=file.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ingestion failed: {exc}",
        )
    return {
        "status": "ingested",
        "source": source,
        "chunks_ingested": report.get("ingested", 0),
        "chunks_skipped_duplicate": report.get("skipped", 0),
        "total_chunks": report.get("total_chunks", 0),
        "topics": report.get("per_topic", {}),
        "languages": report.get("per_language", {}),
    }
