"""
app/main.py — FastAPI application entry point for the SRH Backend API.

Run locally:   uvicorn app.main:app --reload
Swagger UI:    http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, assessment, chat, health, session, tts

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    print("SRH Backend API running")
    yield
    # Shutdown (nothing to clean up yet)


app = FastAPI(
    title="SRH Backend API",
    description=(
        "AI-powered Sexual and Reproductive Health education platform for "
        "Rwandan teenagers and persons with disabilities. Bilingual: "
        "Kinyarwanda and English."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for now; tighten before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers under /api/v1.
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(session.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(tts.router, prefix=API_PREFIX)
app.include_router(assessment.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
