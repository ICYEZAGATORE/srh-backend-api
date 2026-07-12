# Step 0 — Requirements Traceability (Proposal → Built → Verified)

**Purpose.** Cross-check every functional claim in the capstone proposal
(`srh-ml-model/ICYEZAGATORE_Capstone_Proposal_.md`) against what is actually
implemented and working today, so no gap surfaces for the first time in front of
the panel. This feeds the "Analysis of results" rubric criterion.

**Deployed instances under test**
- Frontend (PWA): https://srh-frontend.vercel.app
- Backend API: https://srh-backend-api.onrender.com (base path `/api/v1`)

**Legend** — Delivered: ✅ full · 🟡 partial / dormant · ❌ not delivered · ➕ delivered beyond proposal.
Verified column reflects evidence gathered in *this* test session.

---

## A. Platform / system features (proposal §3.4 architecture, §3.9 tools, §1.5 scope)

| # | Proposed feature (source) | Delivered | Verified working | Evidence location |
|---|---|---|---|---|
| A1 | Mobile-first PWA in React (§3.4) | ✅ | Yes — loads, installable manifest + `sw.js` registered in prod | `testing/e2e/` (mobile-viewport journey), `srh-frontend/public/{manifest.json,sw.js}` |
| A2 | ARIA screen-reader compatibility (§3.4) | ✅ | Yes — 0 `jest-axe` violations across routes; manual audit doc exists | `testing/usability/`, `srh-frontend/src/test/*.a11y*`, `srh-frontend/docs/ACCESSIBILITY_MANUAL_AUDIT.md` |
| A3 | Adjustable text size (§3.4) | ✅ | Yes — `FontSizeControl`, settings test | `srh-frontend/src/test/settings.test.jsx` |
| A4 | High-contrast mode (§3.4) | ✅ | Yes — `ContrastToggle` + high-contrast token set in `index.css` | `srh-frontend/src/index.css` (`:root[data-theme]` HC block) |
| A5 | TTS audio output, English (§3.4/§3.9 Mozilla TTS) | 🟡 | Partial — **works via browser Web Speech API fallback**; the proposed Mozilla/Coqui TTS microservice is NOT wired in prod (`VITE_ACCESSIBILITY_API_URL` unset) | `srh-frontend/src/hooks/useTTS.js`, `testing/e2e/` |
| A6 | Bilingual KN/EN conversational AI (§1.5, §3.4) | 🟡 | Partial — EN end-to-end good; RW **retrieval** fixed (bge-m3 dedicated index), RW **generation** still weak (Qwen mangles Kinyarwanda) | `testing/e2e/`, `testing/performance/`, prior RW work |
| A7 | RAG chatbot over curated SRH KB (§3.4) | ✅ | Yes — Pinecone retrieval returns grounded chunks | `testing/e2e/`, `docs/RAG_ARCHITECTURE.md` |
| A8 | Safety layer filters responses (§3.4, §3.6) | ✅ | Yes — unsafe queries short-circuit to fallback + referral | `testing/e2e/` (unsafe cases), `testing/ml-eval/` |
| A9 | FastAPI backend, session mgmt, logging (§3.4) | ✅ | Yes — `/session/start`, `/chat`, query logging | `testing/performance/`, `testing/locust/` |
| A10 | PostgreSQL relational store (§3.4/§3.9) | ✅ | Yes — health reports `database: ok` | `testing/e2e/` health check, `/api/v1/health` |
| A11 | Vector DB for embeddings (Pinecone) (§3.4/§3.9) | ✅ | Yes — EN `srh-knowledge-base`, RW `srh-knowledge-base-rw` | prior seeding evidence |
| A12 | TLS in transit (§3.4) | ✅ | Yes — HTTPS enforced on Vercel + Render | any request URL |
| A13 | Low-bandwidth-tolerant deployment (§3.4) | ✅ | Measured — see bandwidth table (completes down to Slow 3G) | `testing/network-bandwidth/` |
| A14 | Docker / Docker Compose (§3.9) | ✅ | Yes — backend `Dockerfile` deploys on Render | `srh-backend-api/Dockerfile`, `render.yaml` |
| A15 | Android / mobile-common-device optimization (§1.5) | ✅ | Yes — responsive; low-end profile tested | `testing/performance/` (CPU-throttled profile) |

## B. Accessibility Services microservice (proposal §3.4 "Accessibility Services Layer")

| # | Proposed feature | Delivered | Verified working | Evidence / note |
|---|---|---|---|---|
| B1 | TTS (English) microservice `/v1/tts` (Mozilla/Coqui) | 🟡 | Code present, **dormant in prod** — frontend uses Web Speech fallback because `VITE_ACCESSIBILITY_API_URL` is unset | `srh-frontend/accessibility-service/app/tts.py` |
| B2 | Automatic alt-text generation `/v1/alt-text` | 🟡 | Code present, **dormant in prod** — app uses authored alt text | `srh-frontend/accessibility-service/app/alt_text.py` |
| B3 | Simplified-language mode `/v1/simplify` (cognitive access) | 🟡 | UI toggle wired (`settings_simplified` → `useChat` → `simplifyText`), but **no-op in prod** (service unconfigured returns text unchanged) | `srh-frontend/src/hooks/useChat.js:71`, `accessibilityClient.js:41` |

> **Panel-facing note:** the Accessibility Services layer is **built and unit-tested but not deployed/wired into production**. The proposal presents it as an active layer; in the live product these features degrade gracefully (Web Speech TTS, authored alt text, passthrough text). This is a *promised-vs-delivered gap to disclose*, not to hide.

## C. Machine-learning pipeline (proposal §3.6, §3.7)

| # | Proposed (source) | Delivered | Note / divergence |
|---|---|---|---|
| C1 | Topic/intent classifier (§3.6 Model 1) | ✅ | Delivered (7-class). |
| C2 | Safety classifier (§3.6 Model 2) | ✅ (divergent) | Proposed **4-class response-side** (safe / unsafe-harmful / unsafe-explicit / out-of-scope); delivered **binary query-side** (safe/unsafe) + a response-side re-check in `chat.py`. Divergence is documented in the model metadata. |
| C3 | Language-ID classifier | ➕ | **Not in the proposal** — added (KN vs EN) to route retrieval/generation. Over-delivery. |
| C4 | Encoder = XLM-RoBERTa-base (278M), fine-tuned (§3.7) | ❌ (re-architected) | Delivered models are **TF-IDF + XGBoost / Logistic Regression**, not a fine-tuned transformer. A deliberate engineering pivot (fits free-tier CPU/512 MB, fast inference) but a **material divergence from the proposed method** — must be stated to the panel. |
| C5 | Held-out evaluation: accuracy, macro-F1, per-class P/R, confusion (§3.6) | ✅ | Reproduced this session — see `testing/ml-eval/`. |
| C6 | End-to-end pipeline vs no-classifier baseline (§3.6) | 🟡 | Partial — safety short-circuit verified functionally in e2e; a formal "unsafe-reaching-user rate with/without classifiers" ablation is **not** built. Noted as a recommended addition. |

## D. Research objectives (proposal §1.3.1) — NOT system features

| # | Objective | In scope for a *system* test suite? | Status |
|---|---|---|---|
| D1 | Obj 1: assess baseline SRH knowledge (survey) | No — field research | Out of scope for V&V of the software. |
| D2 | Obj 2: identify access barriers (survey + FGD) | No — field research | Out of scope for V&V of the software. |
| D3 | Obj 3: pre/post-intervention knowledge-gain assessment | Partial — needs an **in-app assessment module** | ❌ **Assessment module is a placeholder** ("coming soon"); the platform cannot yet run the pre/post assessment. Gap. |
| D4 | Obj 4: inclusive, evidence-based platform design framework | Yes — this is the delivered software | ✅ Delivered (rows A/B/C above). |

## E. Explicit gaps promised in the proposal but NOT delivered

| Gap | Proposal source | Reality | Recommendation |
|---|---|---|---|
| **Sign-language integration** | §1.5 Technological Scope ("sign language integration") | ❌ Not implemented anywhere | Disclose as out-of-scope-for-this-iteration; large lift (video/avatar). |
| **In-app pre/post assessment module** | §1.3.1 Obj 3, `Assessment.jsx` | ❌ Placeholder only | Either build a minimal quiz flow or reframe Obj 3 as future work. |
| **Accessibility microservice active in prod** | §3.4 Accessibility Services Layer | 🟡 Built, not wired (env unset) | Deploy the service + set `VITE_ACCESSIBILITY_API_URL`, or state Web Speech fallback is the shipped path. |
| **Transformer (XLM-RoBERTa) classifiers** | §3.7 | ❌ Replaced by TF-IDF+XGBoost | Justify the pivot on cost/latency grounds in Discussion. |
| **Full 4-class safety scheme** | §3.6 Model 2 | 🟡 Binary + output re-check | Justify; note the response-side re-check preserves intent. |

## F. Over-deliveries (built beyond the proposal — worth crediting)

| Item | Note |
|---|---|
| ➕ Language-ID classifier | Enables per-language retrieval/generation routing. |
| ➕ Kinyarwanda dedicated embedding index (bge-m3, 1024-d) | Materially improved RW retrieval quality vs the single MiniLM index. |
| ➕ Optional **voice input** (speech-to-text, English) | Input-side accessibility, added alongside TTS; honest KN-unavailable handling. |
| ➕ PWA offline shell (service worker) | Not explicitly required; aids low-connectivity use. |

---

### Summary of Step 0
- **Delivered as promised:** the core platform — PWA, ARIA a11y, bilingual RAG chat, safety filtering, FastAPI+Postgres+Pinecone, Docker, TLS.
- **Partial / dormant:** the Accessibility Services microservice (TTS/alt-text/simplify) is built but not wired in prod; Kinyarwanda answer *generation* quality is weak (retrieval is fixed).
- **Not delivered (must disclose):** sign-language integration; in-app pre/post assessment module; the transformer-based classifier method (replaced by TF-IDF+XGBoost); the full 4-class safety scheme (reduced to binary + output re-check).
- **Over-delivered:** language-ID model, RW dedicated index, voice input, PWA offline shell.

These divergences are engineering-defensible, but the panel reads the proposal first — each row above is a place a "promised vs delivered" question could land, now answered on the record.
