# SRH-BACKEND-API

**AI-Powered Sexual & Reproductive Health Education Platform — Backend API**
Rwanda | Kinyarwanda–English | FastAPI + PostgreSQL + Vector DB

---

## 🚀 Submission — quick links

| | |
|---|---|
| **Live app (try it)** | **https://srh-frontend.vercel.app** |
| **Deployed API** | https://srh-backend-api.onrender.com · health: `/api/v1/health` · docs: `/docs` |
| **5-min demo video** (core functionality) | **_add link here_** |
| **Install & run (step by step)** | [see below ↓](#install--run-step-by-step) |
| **Related files / repo map** | [see below ↓](#related-files--repo-map) |
| **Sibling repos** | [SRH-FRONTEND](https://github.com/ICYEZAGATORE/srh-frontend) · [SRH-ML-MODEL](https://github.com/ICYEZAGATORE/srh-ml-model) |
| **Testing & V&V evidence** | [`testing/`](testing/README.md) · **Deployment plan** [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |

> The fastest way to see core functionality is the **live app** above (ask an SRH question in
> English or Kinyarwanda, switch languages, try read-aloud and voice input). To run locally,
> follow [Install & run](#install--run-step-by-step).

---

## Project Context

This is the backend API repository for the inclusive SRH education platform targeting Rwandan teenagers (ages 13–19) and persons with disabilities (PWDs). It acts as the central orchestration layer between the React frontend and the ML models.

Sibling repositories:
- **SRH-FRONTEND** — React PWA (bilingual chat UI, accessibility features)
- **SRH-ML-MODEL** — Safety classifier, topic classifier, and bilingual conversational agent (in development)

> **Current status (deployed & verified):** The platform is **live end-to-end**.
> The RAG layer (retrieval + LLM generation — see
> [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md)) and the three **trained
> classifiers are integrated and running in production** (safety, topic, language;
> loaded from `models/*.pkl`). Kinyarwanda retrieval uses a dedicated bge-m3 index.
> Held-out evaluation, load, bandwidth, e2e and deployment tests are in
> [`testing/`](testing/README.md).
>
> **Live:** frontend → https://srh-frontend.vercel.app · backend →
> https://srh-backend-api.onrender.com/api/v1/health
> · **Demo video:** _add link here_

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | Python, FastAPI |
| Relational DB | PostgreSQL |
| Vector DB | Pinecone (cloud) or Chroma (local / CI) |
| RAG Orchestration | LangChain |
| NLP / Embeddings | Hugging Face Transformers, Mbaza NLP (Kinyarwanda) |
| TTS Microservice | Mozilla TTS (open-source; Kinyarwanda voice model) |
| Containerisation | Docker, Docker Compose |
| Testing | Pytest |
| Version Control | GitHub |

---

## Architecture Overview

```
SRH-BACKEND-API (FastAPI)
│
├── API Layer (Routers)
│   ├── /api/v1/chat         → RAG pipeline + LLM + safety filter
│   ├── /api/v1/tts          → Text-to-speech conversion
│   ├── /api/v1/session      → Anonymous session management
│   ├── /api/v1/assessment   → Pre/post SRH quiz submission
│   ├── /api/v1/admin        → Knowledge base management (admin only)
│   └── /api/v1/health       → Liveness / readiness probe
│
├── ML Integration Layer (trained models, deployed)
│   ├── safety_classifier.py → Model 1 (safe/unsafe binary) + bilingual rule pre-filter
│   ├── topic_classifier.py  → Model 3 (7-class SRH topic)
│   ├── language_classifier.py → Model 2 (KN/EN) → per-language retrieval routing
│   └── conversational_agent.py → RAG retrieval + LLM generation
│
├── Data Layer
│   ├── PostgreSQL           → Users, sessions, queries, assessments
│   └── Vector DB            → SRH knowledge base embeddings (RAG)
│
└── Services
    ├── tts_service.py       → Mozilla TTS wrapper
    ├── session_service.py   → UUID-based anonymous session handling
    └── moderation.py        → Safety threshold logic + fallback routing
```

---

## API Endpoints

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Returns `{ "status": "ok" }` if all services are reachable |

### Session

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/session/start` | Creates an anonymous session; returns `session_id` UUID |

**Response:**
```json
{ "session_id": "550e8400-e29b-41d4-a716-446655440000" }
```

### Chat

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Core endpoint — runs safety check, RAG retrieval, LLM generation |

**Request:**
```json
{
  "session_id": "uuid",
  "message": "How do I protect myself from STIs?",
  "lang": "en",
  "simplified": false
}
```

**Response (safe):**
```json
{
  "response": "Protecting yourself from STIs involves...",
  "safe": true,
  "topic": "sti_hiv",
  "lang": "en",
  "fallback": false
}
```

**Response (unsafe — safety classifier triggered):**
```json
{
  "response": null,
  "safe": false,
  "topic": null,
  "lang": "en",
  "fallback": true,
  "fallback_message": "I can't help with that. If you need support, please contact a health worker.",
  "referral": {
    "text": "Isange Health Centre — 0800 123 456",
    "url": null
  }
}
```

### Text-to-Speech

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/tts` | Converts text to audio (returns audio/mpeg stream) |

**Request:**
```json
{ "text": "Protecting yourself from STIs...", "lang": "en" }
```

**Response:** `audio/mpeg` binary stream (or base64 if needed by client).

### Assessment

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/assessment/submit` | Stores pre/post quiz responses linked to session |

**Request:**
```json
{
  "session_id": "uuid",
  "type": "pre",
  "responses": [
    { "question_id": "q1", "answer": "B" },
    { "question_id": "q2", "answer": "A" }
  ]
}
```

### Admin (protected)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/admin/knowledge/upload` | Upload new SRH content to the knowledge base |
| `GET` | `/api/v1/admin/analytics` | Usage statistics (query counts, topic distribution) |

Admin routes require a bearer token. Use environment variable `ADMIN_API_KEY`.

---

## ML Pipeline Integration

### Current State

The full pipeline is **implemented and deployed**. All three trained classifiers load from
`models/*.pkl` via `app/ml/model_registry.py` and run in production; the RAG layer (retrieval
+ LLM generation, bilingual, Pinecone/Chroma) is live.

```python
# app/ml/safety_classifier.py   — Model 1: bilingual rule pre-filter → XGBoost (safe/unsafe)
# app/ml/topic_classifier.py    — Model 3: 7-class SRH topic (XGBoost)
# app/ml/language_classifier.py — Model 2: KN/EN char-n-gram LogReg (+ heuristic fallback)
# app/ml/embeddings.py          — SRHEmbeddingModel + retrieve_context() (EN MiniLM / RW bge-m3)
# app/ml/conversational_agent.py — SRHConversationalAgent (RAG + Qwen2.5-7B via HF)
```

Each classifier falls back to a safe default only if its `.pkl` is absent (keeps CI green).
Held-out evaluation of these exact artifacts: [`testing/ml-eval/`](testing/ml-eval/results/efficacy_results.md).
See [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md) for the retrieval strategy, safety
system prompt, ingestion pipeline, and configuration.

### Model 1 — Safety Classifier

- **Input:** Raw user query string
- **Output:** `{ "label": 0|1, "score": float }` where `0 = SAFE`, `1 = UNSAFE`
- **Trained on:** BeaverTails, ToxicChat, Anthropic HH-RLHF, NVIDIA AEGIS (see SRH-ML-MODEL)
- **Integration:** Called first on every `/chat` request. If `label == 1`, skip all downstream processing and return `fallback: true`.

### Model 3 — Topic Classifier

- **Input:** Raw user query string
- **Output:** `{ "label": int 0-6, "topic": str, "score": float }`
- **7 classes:** `contraception`, `sti_hiv`, `pregnancy`, `puberty`, `gbv_consent`, `disability_srh`, `general_srh`
- **Integration:** Called after safety check passes. Topic label is included in the response and used for analytics logging.

### Conversational Agent (RAG + LLM)

- **Architecture:** Retrieval-Augmented Generation
- **Retrieval:** User query is embedded → cosine similarity search in vector DB → top-k SRH knowledge chunks retrieved
- **Generation:** Retrieved chunks + system prompt passed to fine-tuned LLM (LLaMA 3 / Mistral 7B / Qwen2 — final selection pending)
- **Language:** Query lang (`rw`/`en`) passed in system prompt; model responds in same language
- **Safety prompt:** System prompt enforces age-appropriate, clinically accurate tone; output also passes back through safety check before delivery

---

## Database Schema

### PostgreSQL Tables

```sql
-- Anonymous sessions
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP DEFAULT NOW(),
    lang VARCHAR(5) DEFAULT 'en',
    accessibility_prefs JSONB
);

-- All queries (safe and unsafe)
CREATE TABLE queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    text TEXT NOT NULL,
    lang VARCHAR(5),
    safe BOOLEAN,
    topic VARCHAR(50),
    response TEXT,
    fallback BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Assessment responses
CREATE TABLE assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    type VARCHAR(10) CHECK (type IN ('pre', 'post')),
    responses JSONB,
    submitted_at TIMESTAMP DEFAULT NOW()
);

-- SRH knowledge base entries (metadata; embeddings in vector DB)
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    content TEXT,
    lang VARCHAR(5),
    topic VARCHAR(50),
    source VARCHAR(255),
    reviewed_by TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Vector Database (Pinecone cloud / Chroma local)

- Backend selected by `VECTOR_STORE_BACKEND`: `pinecone` (cloud) or `chroma`
  (embedded, local dev / CI — no API key required)
- Index name: `srh-knowledge-base`
- Embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (supports Kinyarwanda)
- Dimension: 384
- Metadata stored per vector: `{ "topic", "language", "title", "source" }`

---

## Related files & repo map

**Key files & docs**
- [`app/main.py`](app/main.py) — FastAPI app + router registration · [`app/config.py`](app/config.py) — settings
- [`app/ml/`](app/ml/) — classifiers + RAG agent · [`app/services/`](app/services/) — vector store, ingestion, sessions
- [`models/`](models/) — trained `.pkl` classifiers (+ `*_metadata.json`)
- [`render.yaml`](render.yaml), [`Dockerfile`](Dockerfile) — deployment · [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — deployment plan
- [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md) — RAG design · [`testing/`](testing/README.md) — full V&V suite + evidence
- **Sibling repos:** [SRH-FRONTEND](https://github.com/ICYEZAGATORE/srh-frontend) (PWA) · [SRH-ML-MODEL](https://github.com/ICYEZAGATORE/srh-ml-model) (training + data + proposal)

```
srh-backend-api/
├── app/
│   ├── main.py                # FastAPI app init, router registration
│   ├── config.py              # Settings from environment variables
│   ├── database.py            # SQLAlchemy setup, session factory
│   ├── routers/
│   │   ├── chat.py
│   │   ├── tts.py
│   │   ├── session.py
│   │   ├── assessment.py
│   │   ├── admin.py
│   │   └── health.py
│   ├── ml/
│   │   ├── safety_classifier.py    # Model 1 (rule pre-filter + XGBoost)
│   │   ├── topic_classifier.py     # Model 3 (7-class XGBoost)
│   │   ├── language_classifier.py  # Model 2 (KN/EN LogReg)
│   │   ├── conversational_agent.py # RAG + LLM (Qwen2.5-7B via HF)
│   │   └── embeddings.py           # Vector DB query wrapper (EN MiniLM / RW bge-m3)
│   ├── services/
│   │   ├── tts_service.py
│   │   ├── session_service.py
│   │   └── moderation.py
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── session.py
│   │   ├── query.py
│   │   ├── assessment.py
│   │   └── knowledge.py
│   └── schemas/               # Pydantic request/response schemas
│       ├── chat.py
│       ├── tts.py
│       └── assessment.py
├── tests/
│   ├── test_chat.py
│   ├── test_safety.py
│   └── test_session.py
├── alembic/                   # DB migrations
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/srh_db

# Vector store — "pinecone" (cloud) or "chroma" (local dev / CI, no key needed)
VECTOR_STORE_BACKEND=pinecone
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=srh-knowledge-base
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
CHROMA_PERSIST_DIR=./data/chroma_db

# Embeddings (local sentence-transformers; 384-dim, multilingual)
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIM=384

# LLM generation (HuggingFace Inference API)
HF_API_TOKEN=your-hf-token
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
DEFAULT_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LLM_MAX_NEW_TOKENS=300
LLM_TIMEOUT_SECONDS=30
OPENAI_API_KEY=            # optional — GPT-4o benchmark reference only

# Admin
ADMIN_API_KEY=your-secret-admin-key

# App
ENVIRONMENT=development
LOG_LEVEL=INFO
LOG_UNSAFE_TEXT=false
```

> The canonical, always-current list lives in
> [`.env.example`](.env.example) and [`app/config.py`](app/config.py).

---

## Install & run (step by step)

> Prefer to just **use it**? The live app is at https://srh-frontend.vercel.app — no setup.
> The steps below run the backend API locally.

**Prerequisites:** Python ≥ 3.10, PostgreSQL (local) or SQLite (default), Git. Docker optional.

**Steps:**
```bash
# 1. Clone
git clone https://github.com/ICYEZAGATORE/srh-backend-api.git
cd srh-backend-api

# 2. Create + activate a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (fill in values; SQLite works out of the box for local dev)
cp .env.example .env

# 5. Run database migrations
alembic upgrade head

# 6. Start the API
uvicorn app.main:app --reload     # http://localhost:8000
```
- **7. Verify:** open the interactive API docs at **http://localhost:8000/docs**, or
  `curl http://localhost:8000/api/v1/health` → `{"status":"ok"}`.
- To exercise the full RAG+LLM chat path, set `HF_API_TOKEN` and the vector-store keys in `.env`
  (see [Environment Variables](#environment-variables)); without them the API still runs and
  returns safe fallbacks.

**Run with Docker:**
```bash
docker build -t srh-backend .
docker run -p 8000:8000 --env-file .env srh-backend
```

**Run the tests:**
```bash
pytest tests/ -v                  # backend unit/integration tests
# System-wide V&V (e2e, load, ML eval, bandwidth): see testing/README.md
```

---

## Testing

A full system testing & V&V suite lives in [`testing/`](testing/README.md), organised
modularly by category, run against the **deployed** apps. See
[`testing/README.md`](testing/README.md) for reproduce commands and evidence locations.

| Category | Location | Headline result |
|---|---|---|
| Requirements traceability | [`testing/00-traceability/`](testing/00-traceability/requirements_traceability.md) | proposal ↔ delivered, gaps disclosed |
| Functional / e2e (Playwright) | [`testing/e2e/`](testing/e2e/RESULTS.md) | journeys pass; safety false-positive found |
| Performance vs budgets | [`testing/performance/`](testing/performance/results/perf_api_results.md) | chat p95 4.25 s (pass); health p95 miss |
| Low-bandwidth table | [`testing/network-bandwidth/`](testing/network-bandwidth/results/bandwidth_results.md) | completes 50/10/2 Mbps + Slow 3G |
| Scalability (Locust, ≤10 users) | [`testing/locust/`](testing/locust/RESULTS.md) | 0.00% errors at 10 users |
| ML accuracy + convergence | [`testing/ml-eval/`](testing/ml-eval/results/efficacy_results.md) | baselines reproduce; models converge |
| Usability + accessibility | [`testing/usability/`](testing/usability/RESULTS.md) | jest-axe 0 violations |

Backend unit tests: `pytest tests/`. Frontend: `cd ../srh-frontend && npx vitest run`.

Analysis / Discussion / Recommendations (draft for supervisor sign-off):
[`testing/DRAFT_analysis_discussion_recommendations.md`](testing/DRAFT_analysis_discussion_recommendations.md).

## Deployment

Full plan, tools, environments, and verification evidence:
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

- Backend → **Render** (Docker, `render.yaml` blueprint, auto-deploy on push to `main`).
- Frontend → **Vercel** (`vercel --prod` or Git integration).
- Verified live end-to-end (fresh visit → real chat exchange), not just health checks.

## Security Notes

- No PII is stored. Sessions are UUID-only with no name, email, or device ID.
- All data in transit uses TLS (enforce in production via reverse proxy / load balancer).
- Admin endpoints require `ADMIN_API_KEY` bearer token.
- Sensitive SRH query data is never logged to stdout in production (`LOG_LEVEL=WARNING`).
- UNSAFE queries are stored (label only, not full text) for safety auditing; full text is discarded after classification.

---

## Retraining / Updating ML Models

The three classifiers are **already integrated and deployed** (`models/*.pkl`, loaded via
`app/ml/model_registry.py` and used by `safety_classifier.py`, `topic_classifier.py`,
`language_classifier.py`). To retrain or replace them:

1. Retrain in **SRH-ML-MODEL** (notebooks under `notebooks/`) and export new `.pkl` files.
2. Copy them into `./models/` (keep the same filenames or update the paths in `.env`).
3. Re-run held-out evaluation: `venv/Scripts/python.exe testing/ml-eval/evaluate_efficacy.py`
   and compare against the recorded baselines.
4. Run `pytest tests/` to verify no regressions, then redeploy (push to `main`).

**No endpoint signatures change.** Pin scikit-learn / XGBoost to the training versions to
avoid unpickle drift (see the metadata `*_metadata.json`).

---

## Contributing

