"""
main.py — FastAPI application entry point for the SRH AI Platform.

Auto-generated Swagger UI available at:
  http://localhost:8000/docs       (Swagger UI)
  http://localhost:8000/redoc      (ReDoc)
"""

import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ask, auth, assess, health
from app.services.rag_service import rag_service
from app.config import settings


# ── Lifespan: load ML models once at startup ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the FAISS index and embedding model on startup; release on shutdown."""
    print("Starting up — loading ML pipeline...")
    await rag_service.load()
    print(f"RAG service ready. Index vectors: {rag_service.index.ntotal}")
    yield
    print("Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SRH AI Platform API",
    description=(
        "AI-powered sexual and reproductive health education platform "
        "for Rwandan teenagers and persons with disabilities. "
        "Supports bilingual interaction in English and Kinyarwanda."
    ),
    version="0.1.0",
    contact={
        "name": "ALU Capstone — BSc. Software Engineering",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router,  prefix="/api/v1",  tags=["Health"])
app.include_router(auth.router,    prefix="/api/v1",  tags=["Auth"])
app.include_router(ask.router,     prefix="/api/v1",  tags=["SRH Chat"])
app.include_router(assess.router,  prefix="/api/v1",  tags=["Assessment"])


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "SRH AI Platform API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }