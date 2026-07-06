# RAG Architecture

**Retrieval-Augmented Generation pipeline for the SRH Education Platform backend.**

This document describes the retrieval + LLM layer that powers `POST /api/v1/chat`.
It complements the top-level [README](../README.md); read that first for the API
contract and project context.

> **Design contract:** the RAG layer was added *without changing any existing
> endpoint signature or response schema*. `retrieve_context(...)` and
> `generate_response(...)` keep their original router-facing signatures (plus
> additive optional parameters), so the frontend integration is untouched. The
> `safety_classifier.py` and `topic_classifier.py` stubs are **not** modified by
> this layer.

---

## 1. Request lifecycle

The chat pipeline order is fixed (see [`app/routers/chat.py`](../app/routers/chat.py)):

```
POST /api/v1/chat
   │
   1. classify_safety(message)          ── Model 1 stub (safe/unsafe)
   │
   2. detect_language(message, hint)    ── language ID (proxy stub, en/rw)
   │
   3. log Query row                     ── anonymised audit trail (always)
   │
   ├─ if UNSAFE ─► fallback + referral, STOP (no retrieval, no LLM)
   │
   4. classify_topic(message)           ── Model 3 stub (7-class topic)
   │
   5. retrieve_context()  ──►  generate_response()      ◄── the RAG layer
   │        (embed + vector search)     (build prompt + LLM call)
   │
   6. persist response on the Query row
   │
   7. return ChatResponse
```

Language detection is inserted at **position 2**: the detected language drives
retrieval and generation, while the client-declared `lang` is preserved verbatim
in the response for the API contract.

---

## 2. Components

| Layer | Module | Responsibility |
|---|---|---|
| Embeddings | [`app/ml/embeddings.py`](../app/ml/embeddings.py) | `SRHEmbeddingModel` (384-dim multilingual vectors) + `retrieve_context()` wrapper |
| Vector store | [`app/services/vector_store.py`](../app/services/vector_store.py) | `VectorStoreClient` interface → `PineconeVectorStore` / `ChromaVectorStore` |
| Generation | [`app/ml/conversational_agent.py`](../app/ml/conversational_agent.py) | `SRHConversationalAgent` (prompt build + LLM call) + `generate_response()` wrapper |
| Language ID | [`app/ml/language_classifier.py`](../app/ml/language_classifier.py) | `detect_language()` (en/rw proxy until Model 2 is swapped in) |
| Ingestion | [`app/services/ingestion.py`](../app/services/ingestion.py) | Shared chunk → embed → upsert core |
| Bulk ingest | [`scripts/ingest_knowledge_base.py`](../scripts/ingest_knowledge_base.py) | CLI to build the knowledge base from source docs |

### 2.1 Embeddings

- Model: `paraphrase-multilingual-MiniLM-L12-v2` (**384-dim**), run **locally**
  via `sentence-transformers`. It handles Kinyarwanda through cross-lingual
  transfer (no separate rw model required).
- Loaded once as a thread-safe **singleton** on first use.
- `HF_API_TOKEN` is optional and only consulted if the local load fails and the
  HF Inference API fallback is engaged.

### 2.2 Vector store

A single `VectorStoreClient` interface with two interchangeable backends,
selected by the `VECTOR_STORE_BACKEND` env var:

| Backend | When | Notes |
|---|---|---|
| `pinecone` | deployment | Modern serverless SDK (`pinecone`, not the deprecated `pinecone-client`); index `srh-knowledge-base`, cosine, 384-dim |
| `chroma` | local dev / CI | Embedded, persists to `CHROMA_PERSIST_DIR`; **no API key required** |

Metadata filters (`language`, `topic`) are translated per backend
(`{"$eq": v}` for Pinecone, a `where` clause for Chroma). The router never
imports this module directly — it only calls `retrieve_context`.

**Chunk contracts**

```python
# upsert() accepts:
{"id": str, "embedding": List[float], "text": str,
 "metadata": {"topic": str, "language": "en"|"rw",
              "title": str | None, "source": str | None}}

# similarity_search() returns:
{"entry_id": str, "topic": str, "lang": str,
 "title": str | None, "text": str, "score": float}
```

### 2.3 Retrieval strategy

`retrieve_context(query, lang, top_k=5, topic=None)`:

1. Embed the query with `SRHEmbeddingModel`.
2. Similarity search filtered by **detected language + topic**, `top_k=5`.
3. **Broaden fallback:** if fewer than 3 chunks come back, retry **without** the
   topic filter (language filter retained) so a narrow/mislabelled topic never
   starves the LLM of context.

### 2.4 Conversational agent

`SRHConversationalAgent.generate(...)`:

1. Retrieve context (with the broaden fallback above).
2. Pull up to **5 turns** of prior conversation for the `session_id` (from the
   `queries` table) as chat history.
3. Fill the **safety-constrained system prompt** (see §3) with
   `{language, retrieved_context, chat_history, user_query}`.
4. Call the LLM (`LLM_MODEL`, HF Inference API) with a `LLM_TIMEOUT_SECONDS`
   timeout and `LLM_MAX_NEW_TOKENS` cap.
5. **Post-process:** strip any echoed prompt/context markers so the system
   prompt and raw chunks never leak into the reply.
6. Return `{response_text, retrieved_chunks, confidence_score, language}`, where
   `confidence_score` is the mean retrieval similarity of the used chunks
   (`0.0` when nothing was retrieved).

On any LLM failure or timeout, the bilingual safe fallback from
[`app/services/moderation.py`](../app/services/moderation.py) is returned instead
of an error — the endpoint never surfaces a raw exception to the user.

---

## 3. Safety system prompt

Every generation uses this exact template (see `SYSTEM_PROMPT_TEMPLATE` in
`conversational_agent.py`). It is grounding-constrained (answer *only* from
retrieved context) and hard-codes Rwandan referral pathways:

- Unknown answer → refer to the **Rwanda health hotline 114**.
- Never diagnose / prescribe / give emergency guidance → emergency **112**.
- Abuse / GBV disclosure → **Isange One Stop Centre, +250 788 389 547**.
- Always respond in the detected language (`en` / `rw`), age-appropriately.

This is the platform's second safety layer: the input-side `classify_safety`
gate is the first; grounding + referral constraints in the prompt are the second.

---

## 4. Knowledge base ingestion

Ingestion logic is shared by the bulk CLI and the admin upload endpoint, so both
paths behave identically ([`app/services/ingestion.py`](../app/services/ingestion.py)).

Per document:

1. **Clean** — strip headers/footers/page numbers, normalise whitespace, keep
   English + Kinyarwanda characters.
2. **Chunk** — LangChain `RecursiveCharacterTextSplitter`, `chunk_size=500`,
   `chunk_overlap=50`.
3. **Tag** — per-chunk metadata: language (en/rw), topic (7-class taxonomy),
   source, chunk_id, ingest date, **SHA-256 content hash**.
4. **Embed** — new chunks only (`SRHEmbeddingModel`).
5. **Upsert** — to the active vector store **+** a `KnowledgeEntry` row **+** a
   local JSONL cache under `data/knowledge_base/`.

**Idempotency:** the SHA-256 `chunk_hash` is both the vector id and a unique DB
column (migration `0002`), so re-ingesting identical text upserts the same
vectors and inserts no duplicate rows.

> **No fabricated health content.** Only text sourced from real documents
> (WHO / Rwanda MoH / UNFPA and the reviewed SRH corpus) is chunked and stored.
> Language/topic **tagging** uses lightweight heuristics that can later be
> replaced by the trained classifiers without changing this interface.

### Entry points

```bash
# Bulk build (local dev; Chroma):
VECTOR_STORE_BACKEND=chroma python scripts/ingest_knowledge_base.py

# Post-deployment single upload (admin-only):
POST /api/v1/admin/knowledge/upload   # bearer ADMIN_API_KEY, PDF or text
```

---

## 5. Configuration

All RAG settings live in [`app/config.py`](../app/config.py) and
[`.env.example`](../.env.example):

| Variable | Default | Purpose |
|---|---|---|
| `VECTOR_STORE_BACKEND` | `pinecone` | `pinecone` (cloud) or `chroma` (local/CI) |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | sentence-transformer id |
| `EMBEDDING_DIM` | `384` | vector dimension |
| `PINECONE_API_KEY` | — | required when backend = pinecone |
| `PINECONE_INDEX_NAME` | `srh-knowledge-base` | index name |
| `PINECONE_CLOUD` / `PINECONE_REGION` | `aws` / `us-east-1` | serverless spec |
| `CHROMA_PERSIST_DIR` | `./data/chroma_db` | local Chroma path |
| `HF_API_TOKEN` | — | LLM calls + embedding API fallback |
| `LLM_MODEL` / `DEFAULT_LLM_MODEL` | `mistralai/Mistral-7B-Instruct-v0.3` | generation model (update after the Part 5 benchmark) |
| `LLM_MAX_NEW_TOKENS` | `300` | generation cap |
| `LLM_TIMEOUT_SECONDS` | `30` | per-call timeout |
| `OPENAI_API_KEY` | — | only for the optional GPT-4o benchmark reference |

---

## 6. Testing

RAG tests run **fully offline** against the Chroma backend so CI needs no cloud
keys (`tests/conftest.py` forces `VECTOR_STORE_BACKEND=chroma`, a temp
`CHROMA_PERSIST_DIR`, and a blank `HF_API_TOKEN`):

| File | Covers |
|---|---|
| `tests/test_embeddings.py` | embedding shape/dim, singleton, `retrieve_context` wrapper |
| `tests/test_vector_store.py` | upsert / similarity_search / filter / delete on Chroma |
| `tests/test_rag_pipeline.py` | end-to-end retrieve → generate, fallback behaviour |
| `tests/test_knowledge_ingestion.py` | clean → chunk → tag → idempotent upsert |

Pinecone-specific assertions are gated with `skipif` on `PINECONE_API_KEY`.

```bash
pytest tests/ -v          # all RAG tests pass on Chroma, no keys needed
```

---

## 7. Swapping in the trained models

The RAG layer is deliberately decoupled from the classifier stubs. When the
SRH-ML-MODEL deliverables land:

- **Language (Model 2):** replace the heuristic in `language_classifier.py` with
  `joblib.load(...)` + `predict` — keep the `{label, language, score}` shape.
- **Safety / Topic (Models 1 & 3):** unchanged by this layer; swap per the
  README's "Updating When ML Models Are Ready" section.
- **LLM:** run `notebooks/llm_benchmark.ipynb`, then set the winning id in
  `DEFAULT_LLM_MODEL` / `LLM_MODEL`.

No endpoint signature or response schema changes are required for any of these.
