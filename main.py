"""
main.py
────────
FastAPI application entry point.
Runs the SRH Platform backend.

Start locally:
    uvicorn main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.init_db import create_tables, seed_first_admin
from app.db.session import SessionLocal

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="SRH AI Platform API",
    description=(
        "Backend API for the AI-Powered Sexual and Reproductive Health Education Platform "
        "for Rwandan Teenagers and Persons with Disabilities."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ── Startup event ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting SRH Platform API...")
    create_tables()
    db = SessionLocal()
    try:
        seed_first_admin(db)
    finally:
        db.close()
    logger.info("Startup complete.")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "ok", "service": "SRH Platform API", "version": "1.0.0"}
