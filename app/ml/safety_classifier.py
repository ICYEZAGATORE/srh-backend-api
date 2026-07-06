"""
app/ml/safety_classifier.py — Model 1: binary safety classifier (SAFE/UNSAFE).

Two-layer design (mirrors srh-ml-model/src/safety_filter.py — see its header for
the ADR). A text is UNSAFE if EITHER layer flags it:

  1. RULE pre-filter — deterministic, bilingual EN+RW. Catches catastrophic,
     unambiguous phrases (incl. Kinyarwanda, which the ML model does not cover).
     Has precedence and short-circuits: if it matches, we never call the model.
  2. ML classifier — ``models/safety_classifier.pkl`` (word TF-IDF + XGBoost,
     English content), loaded once via the model registry. Runs only when the
     rule layer passes.

The same function guards both the incoming QUERY (chat.py step 1) and the
generated RESPONSE (proposal §3.6 output-side check), so the rule phrase lists
below merge the query and response terms from the rule filter.

label 0 = SAFE, label 1 = UNSAFE. Return shape ``{"label", "score"}`` is stable.
"""

from __future__ import annotations

from app.ml.model_registry import get_safety_model

# Deterministic bilingual guards — mirror of srh-ml-model/src/safety_filter.py
# (BLOCKED_PHRASES_EN + BLOCKED_PHRASES_RW + UNSAFE_RESPONSE_KEYWORDS), so this
# layer catches the same catastrophic content on both queries and responses.
_BLOCKED_PHRASES = (
    # English — query-side
    "have sex with someone who is asleep",
    "force someone to have sex",
    "force them to have sex",
    "drug someone",
    "rape",
    "self harm",
    "kill myself",
    "commit suicide",
    "how to get pregnant without consent",
    # English — response-side keywords
    "murder",
    "force them",
    "drug them",
    "assault them",
    # Kinyarwanda
    "kumvisha umuntu nabi",
    "kwica",
)


def _rule_is_unsafe(text: str) -> bool:
    low = (text or "").lower()
    return any(phrase in low for phrase in _BLOCKED_PHRASES)


def classify_safety(text: str) -> dict:
    """Classify ``text`` (query or response) as SAFE (0) or UNSAFE (1).

    Rule pre-filter first (deterministic, has precedence), then the ML model.
    """
    # Layer 1 — deterministic bilingual rule filter (precedence, short-circuits).
    if _rule_is_unsafe(text):
        return {"label": 1, "score": 1.0}

    # Layer 2 — trained ML classifier (English content).
    model = get_safety_model()
    if model is None:
        # Artifact unavailable: the rule layer already passed, so treat as SAFE.
        # (Rule filter is the deterministic backstop; see module header.)
        return {"label": 0, "score": 0.5}

    label = int(model.predict([text])[0])
    try:
        score = float(model.predict_proba([text])[0].max())
    except Exception:  # pragma: no cover - classifier without predict_proba
        score = 1.0
    return {"label": label, "score": score}
