"""
health.py — GET /api/v1/health
Liveness and readiness probe for deployment health checks.
"""

from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get(
    "/health",
    summary="Health check",
    description="Returns API status and RAG pipeline readiness. Used by deployment platforms.",
)
async def health_check():
    from app.services.rag_service import rag_service
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "0.1.0",
        "rag_loaded": rag_service._loaded,
        "index_vectors": rag_service.index.ntotal if rag_service.index else 0,
    }