# DRAFT — Analysis, Discussion & Recommendations

> ⚠️ **DRAFT for supervisor review.** The assignment specifies these sections are
> finalised *with the supervisor*. Numbers below are measured (see each
> `RESULTS.md`); framing/wording is provisional.

## 1. Analysis of results (what the evidence shows)

**Functional correctness.** All scripted user journeys pass end-to-end on the deployed
app, including the continuous flow (land → consent → chat EN → switch language → chat RW),
edge cases (empty, ~5.5k-char, special/injection-looking, mixed-language), safety blocking,
and off-topic handling. The safety layer correctly redirects a self-harm query to a 114
referral, and an off-topic (car-repair) query is declined rather than answered with
fabricated SRH content.

**Performance.** Against pre-declared budgets: chat p95 = 4.25 s single-user / 2.8 s at 10
concurrent users (budget 15 s → **met**, 0% errors); health p95 = 2.13 s (budget 1 s →
**missed**). Frontend LCP is "good" on a modern device (landing 2.11 s, chat 1.42 s) and the
SPA stays interactive (domInteractive ≤ 1.3 s) even at 6× CPU throttling.

**Low-bandwidth.** The core journey completes at **all four** tested bandwidths
(50/10/2 Mbps + Slow 3G); shell load rises from ~3.0 s to ~5.1 s at Slow 3G while answer
time stays low (small JSON payloads). A persistent loading indicator keeps the ~62 s cold
start distinguishable from a hang.

**Scalability.** Stable at the 10-user cap: 300 requests, **0.00% error rate**, chat p95
2.8 s. No breaking point was sought against production (deliberate).

**ML accuracy.** On held-out test sets the deployed models reproduce their recorded
baselines: safety accuracy 0.7867 / macro-F1 0.7847 and language 1.0/1.0 match **exactly**
(confirming no regression after the sklearn/XGBoost version-pin fix); topic accuracy 0.9688
matches, with the macro-F1 dip (0.879 vs 0.963) fully explained by n=7 minority-class support
in this file. Loss curves show all three models converge (safety validation-min at round 145
with mild post-min overfit; topic still improving to round 300; language by ~40 lbfgs iters).

### 1a. Linkage to proposal objectives & scope (how results map to what was promised)

| Proposal item | Measured result | Achieved / missed — *how* |
|---|---|---|
| **Obj 4** — inclusive bilingual (KN/EN) AI SRH platform | e2e EN→RW journey passes; bilingual RAG live | **Achieved** via RAG + per-language embedding routing; RW quality bounded by LLM generation, not retrieval. |
| **RQ4** — accessibility features essential for inclusion | jest-axe 0 violations; TTS, text-size, contrast, voice input present | **Achieved (partial)** — screen-reader/keyboard/contrast verified; **sign-language missed**; a11y microservice **dormant** in prod. |
| **§3.4** — safety layer filters responses | unsafe→114 referral; valid condom question over-blocked | **Achieved with caveat** — blocks harmful content; binary classifier over-blocks some valid SRH questions (quantified, not hidden). |
| **§3.4** — low-bandwidth, Android-first | completes at 50/10/2 Mbps + Slow 3G; interactive ≤1.3 s at 6× CPU | **Achieved** — small bundle + PWA shell; min-spec measured, not asserted. |
| **§3.6/§3.7** — trained classifiers + held-out eval | safety/lang F1 match baselines; topic acc 0.969; convergence shown | **Achieved, method-divergent** — metrics reproduce, but classifiers are **TF-IDF+XGBoost/LogReg, not XLM-RoBERTa**. |
| **Obj 3** — pre/post knowledge-gain assessment | assessment page = placeholder | **Missed** — in-app assessment not built. |
| **§1.5** — sign-language integration | absent | **Missed** — out of scope this iteration. |

*Mechanisms (how, not just what):* passing journeys come from the safety→language→topic→
retrieve→LLM→output-safety pipeline; the RW gain from a **dedicated bge-m3 1024-d index routed
by detected language**; the 0%-error load result from a stateless FastAPI with externalised
vector/LLM services; the exact metric reproduction from the **version-pin fix**. Each miss is
traced to a concrete cause (classifier precision, unbuilt module, method pivot) in §2.

## 2. Discussion (what it means, incl. proposal vs delivered)

- **Promised-vs-delivered gaps (from Step 0), to disclose proactively:** sign-language
  integration was proposed (§1.5) but **not built**; the pre/post **assessment module is a
  placeholder**; the classifier method **pivoted from XLM-RoBERTa fine-tuning to
  TF-IDF+XGBoost** (defensible on free-tier cost/latency, but a material method change); the
  **4-class safety scheme was reduced to binary** + an output-side re-check; the
  **accessibility microservice** (TTS/alt-text/simplify) is **built but dormant in prod**
  (TTS runs on the Web Speech fallback). None of these are fatal, but the panel reads the
  proposal first — each is answered on the record in `00-traceability/`.
- **A real quality issue surfaced by testing:** the binary safety classifier **over-blocks**
  some valid SRH questions (reproducibly, "How do I use a condom correctly?" → safety
  fallback). This is consistent with its measured `precision_unsafe ≈ 0.85`. It trades false
  positives for safety — appropriate directionally for a health tool, but the specific
  over-block is a fixable UX cost.
- **Kinyarwanda:** retrieval is now correct (dedicated bge-m3 index), so the remaining RW
  weakness is **generation** (the LLM), not retrieval — an important distinction for scoping
  future work.
- **Health-endpoint budget miss** is environmental (free-tier RTT + DB round-trip in the
  health check), not a code defect; it does not affect user-facing chat.

## 3. Recommendations (provisional)

1. **Reduce safety false-positives:** raise the unsafe decision threshold and/or add an
   SRH-safe allowlist ahead of the classifier; re-measure precision/recall and re-run the
   e2e over-block case.
2. **Close or reframe proposal gaps:** either build a minimal in-app assessment (Objective 3)
   and wire/deploy the accessibility microservice, or explicitly reframe sign-language and
   the transformer classifiers as documented future work in the thesis.
3. **Improve Kinyarwanda generation** (the real bottleneck): a stronger multilingual LLM or
   RW-specific prompting/post-editing; retrieval needs no further work.
4. **Lighten the health check** (skip or cache the DB round-trip) to meet the health budget,
   and/or add a warm-ping to mask the free-tier cold start.
5. **Add a response/semantic cache** before scaling beyond a small pilot (identical questions
   currently re-run the full RAG+LLM path).
6. **Finish the human-in-the-loop usability + accessibility passes** (moderated 3–5 user
   session and NVDA/TalkBack audit — instruments are ready).
7. **Breaking-point load test on a staging replica** (25/50/100 users) to locate the latency
   knee without risking production.
