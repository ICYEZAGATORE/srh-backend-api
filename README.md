# SRH-BACKEND-API

**AI-Powered Sexual & Reproductive Health Education Platform — Backend API**
Rwanda | Kinyarwanda–English | FastAPI + PostgreSQL + Vector DB

---

## Project Context

This is the backend API repository for the inclusive SRH education platform targeting Rwandan teenagers (ages 13–19) and persons with disabilities (PWDs). It acts as the central orchestration layer between the React frontend and the ML models.

Sibling repositories:
- **SRH-FRONTEND** — React PWA (bilingual chat UI, accessibility features)
- **SRH-ML-MODEL** — Safety classifier, topic classifier, and bilingual conversational agent (in development)

> **Current status:** The full API structure is built and the RAG layer
> (retrieval + LLM generation) is **implemented** — see
> [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md). The `safety_classifier`
> and `topic_classifier` remain stubbed/mock so the frontend can integrate
> immediately; when **SRH-ML-MODEL** delivers those trained models, swap the
> stubs for real calls — no endpoint signatures change.

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
├── ML Integration Layer (stubs → real models)
│   ├── safety_classifier.py → Calls Model 1 (safe/unsafe binary)
│   ├── topic_classifier.py  → Calls Model 3 (7-class SRH topic)
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

The **RAG layer is implemented** (retrieval + LLM generation, bilingual, with a
Pinecone/Chroma vector store and the multilingual embedding model). The two
input classifiers still return mock data until **SRH-ML-MODEL** delivers them:

```python
# app/ml/safety_classifier.py  — STUB (Model 1)
def classify_safety(text: str) -> dict:
    # TODO: replace with real model call
    return {"label": 0, "score": 0.95}  # 0 = SAFE

# app/ml/topic_classifier.py   — STUB (Model 3)
def classify_topic(text: str) -> dict:
    # TODO: replace with real model call
    return {"label": 1, "topic": "sti_hiv", "score": 0.88}

# app/ml/language_classifier.py — proxy (Model 2): langdetect + rw heuristic
# app/ml/embeddings.py          — IMPLEMENTED: SRHEmbeddingModel + retrieve_context()
# app/ml/conversational_agent.py — IMPLEMENTED: SRHConversationalAgent (RAG + LLM)
```

See [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md) for the retrieval
strategy, safety system prompt, ingestion pipeline, and configuration.

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

## Folder Structure (Suggested)

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
│   │   ├── safety_classifier.py    # Stub → real model
│   │   ├── topic_classifier.py     # Stub → real model
│   │   ├── conversational_agent.py # Stub → RAG + LLM
│   │   └── embeddings.py           # Vector DB query wrapper
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
LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
DEFAULT_LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
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

## Getting Started

### Prerequisites
- Python >= 3.10
- PostgreSQL running locally
- Docker (recommended)

### Local Development

```bash
git clone https://github.com/<your-org>/SRH-BACKEND-API.git
cd SRH-BACKEND-API
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Fill in your values
alembic upgrade head             # Run DB migrations
uvicorn app.main:app --reload    # Runs on http://localhost:8000
```

Swagger UI available at: `http://localhost:8000/docs`

### Running with Docker

```bash
docker build -t srh-backend .
docker run -p 8000:8000 --env-file .env srh-backend
```

### Running Tests

```bash
pytest tests/ -v
```

---

## Security Notes

- No PII is stored. Sessions are UUID-only with no name, email, or device ID.
- All data in transit uses TLS (enforce in production via reverse proxy / load balancer).
- Admin endpoints require `ADMIN_API_KEY` bearer token.
- Sensitive SRH query data is never logged to stdout in production (`LOG_LEVEL=WARNING`).
- UNSAFE queries are stored (label only, not full text) for safety auditing; full text is discarded after classification.

---

## Updating When ML Models Are Ready

The RAG layer (embeddings, vector store, conversational agent) is already wired
— see [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md). What remains is
swapping the three classifier stubs for trained models:

1. Copy `.pkl` files or model directories into `./models/`
2. Add the model path(s) to `.env`
3. Replace the stub bodies in `app/ml/safety_classifier.py`,
   `app/ml/topic_classifier.py`, and `app/ml/language_classifier.py` with real
   `joblib.load()` + `model.predict()` calls (keep the return shapes)
4. Pick the LLM: run `notebooks/llm_benchmark.ipynb` and set the winner in
   `DEFAULT_LLM_MODEL` / `LLM_MODEL`
5. Run `pytest tests/` to verify no regressions
6. Redeploy

**No endpoint signatures need to change.** The frontend integration remains intact.

---

## Contributing

This project is part of an ALU BSc Software Engineering capstone. Open a PR with a description. Backend PRs must include passing Pytest tests. For DB schema changes, include an Alembic migration file.