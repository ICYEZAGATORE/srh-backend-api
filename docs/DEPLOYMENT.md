# Deployment Plan & Execution — SRH Education Platform

End-to-end plan for deploying the platform, the tools/environments used, and the
verification evidence proving it runs in the target environment. Executed and verified
2026-07-12 (see `testing/`).

## 1. Environments & tooling

| Component | Environment | Tool / platform | Live URL |
|---|---|---|---|
| Frontend (PWA) | Production | **Vercel** (Vite build, CDN, SPA rewrites) | https://srh-frontend.vercel.app |
| Backend API | Production | **Render** (Docker web service, free tier, 512 MB) | https://srh-backend-api.onrender.com |
| Relational DB | Production | **Render PostgreSQL** (free, shared) | internal connection string |
| Vector DB | Production | **Pinecone** (serverless) — `srh-knowledge-base` (EN, 384-d), `srh-knowledge-base-rw` (RW, 1024-d) | Pinecone cloud |
| LLM + embeddings | Production | **Hugging Face Inference API** (Qwen2.5-7B-Instruct; MiniLM/bge-m3 embeddings) | HF cloud |
| Accessibility svc | Built, **not deployed** | FastAPI microservice (`srh-frontend/accessibility-service/`, Docker) | dormant — Web Speech fallback used |
| CI/local test | Dev | Pytest, Vitest, Playwright, Locust | — |

**Source control:** GitHub (`ICYEZAGATORE/srh-backend-api`, `.../srh-frontend`). `main` is the
production branch for both.

## 2. Backend deployment (Render, Docker)

**Plan (Blueprint-driven, reproducible via `render.yaml`):**
1. Provision a Render Web Service from `render.yaml` (runtime: docker, `Dockerfile`, region
   `virginia` to match the DB).
2. Reuse the existing free PostgreSQL DB; set `DATABASE_URL` manually (secret; internal URL).
3. Set environment variables (secrets marked `sync:false` in `render.yaml`):
   - `DATABASE_URL`, `ADMIN_API_KEY` (generated), `HF_API_TOKEN`, `PINECONE_API_KEY` — secrets.
   - `EMBEDDING_BACKEND=hf_api` (avoids loading torch on 512 MB), `LLM_MODEL=Qwen/Qwen2.5-7B-Instruct`,
     `VECTOR_STORE_BACKEND=pinecone`, `PINECONE_INDEX_NAME=srh-knowledge-base`,
     `RW_EMBEDDING_MODEL=BAAI/bge-m3`, `RW_EMBEDDING_DIM=1024`,
     `RW_PINECONE_INDEX_NAME=srh-knowledge-base-rw`, `CORS_ALLOW_ORIGINS=https://srh-frontend.vercel.app`.
4. Startup: `entrypoint.sh` runs DB migrations then serves (free tier has no pre-deploy hook).
5. Health check path `/api/v1/health`. **Auto-deploy** on push to `main`.
6. Seed Pinecone indexes before first use (EN KB; RW via the seed scripts, bge-m3).

**Known operational constraint:** free tier **cold-starts (~62 s)** after idle; first request
is slow (a loading indicator distinguishes this from a hang — verified in `testing/network-bandwidth/`).

## 3. Frontend deployment (Vercel, Vite PWA)

**Plan:**
1. Project linked to Vercel (`vercel.json`: framework `vite`, `buildCommand npm run build`,
   `outputDirectory dist`, SPA rewrite to `/index.html`).
2. Env vars: `VITE_API_BASE_URL` → backend; `VITE_ACCESSIBILITY_API_URL` → **unset**
   (accessibility microservice not deployed → graceful Web Speech / authored-alt fallback).
3. Deploy: **`vercel --prod`** (CLI) or push to `main` (Git integration). PWA service worker
   (`public/sw.js`) registered in production for offline shell caching.
4. Verify the production alias `https://srh-frontend.vercel.app` serves the new build (HTTP 200).

## 4. Deployment verification (executed — evidence)

| Check | Method | Result | Evidence |
|---|---|---|---|
| Backend health | `GET /api/v1/health` | `status: ok`, db + models ok | `testing/e2e` |
| Frontend live | `GET /` | HTTP 200, PWA loads | `testing/e2e/results/evidence/01-landing.png` |
| **Real end-to-end exchange** | Playwright: fresh visit → consent → chat → answer | ✅ passes (not just health) | `testing/e2e/RESULTS.md`, `deployment_evidence.json` |
| Bilingual path | e2e EN→switch→RW | ✅ RW routed to bge-m3 index | `05-answer-rw.png` |
| Load @ 10 users | Locust | 0.00% errors, p95 2.8 s | `testing/locust/RESULTS.md` |
| Low bandwidth | Playwright throttling | completes 50/10/2 Mbps + Slow 3G | `testing/network-bandwidth/RESULTS...md` |
| Reproducibility | `render.yaml` + `vercel.json` in repo | blueprint-driven redeploy | this doc |

## 5. Rollback & redeploy
- Backend: revert the commit on `main` (Render auto-redeploys) or redeploy a previous Render
  deploy from the dashboard.
- Frontend: `vercel rollback` or redeploy a previous Vercel deployment (immutable URLs).

## 6. Residual deployment gaps (disclosed)
- **Accessibility microservice not deployed** — TTS/alt-text/simplify run on fallbacks in
  prod. To fully match the proposal: deploy the service (Docker) and set
  `VITE_ACCESSIBILITY_API_URL`.
- **Health-check latency** exceeds its 1 s budget (free-tier RTT + DB round-trip) — consider a
  lighter health probe or a warm-ping to mask cold starts.
