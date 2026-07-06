"""
app/ml/language_classifier.py — Model 2: English vs Kinyarwanda language ID.

Loads ``models/language_classifier.pkl`` (character n-gram TF-IDF + Logistic
Regression, trained from scratch on EN/RW) once via the model registry and uses
it as the primary detector. The previous ``langdetect`` + Kinyarwanda-token
heuristic is retained as a FALLBACK for when the artifact is unavailable.

Label convention matches the trained model: english=0, kinyarwanda=1.
Return shape ``{"label", "language", "score"}`` is stable; ``hint`` (the
client-declared ``lang``) is used only as a tie-breaker in the fallback path.
"""

from __future__ import annotations

import re

from app.ml.model_registry import get_language_model

_LABELS = {0: "en", 1: "rw"}

# High-frequency Kinyarwanda tokens (langdetect has no Kinyarwanda model).
_RW_MARKERS = {
    "mu", "ni", "na", "ku", "ba", "iyo", "ariko", "kandi", "cyangwa", "ubwo",
    "uburyo", "umuntu", "abantu", "kubera", "ubuzima", "indwara", "imibonano",
    "urubyaro", "kuboneza", "nka", "muri", "byose", "cyane", "gukora", "hehe",
    "murakoze", "yego", "oya", "nshobora", "ndashaka",
}


def detect_language(text: str, hint: str | None = None) -> dict:
    """Return the detected language for ``text``.

    Uses the trained char n-gram model when available, else the heuristic below.
    Shape mirrors the other classifiers: ``{"label", "language", "score"}``.
    """
    model = get_language_model()
    if model is not None:
        label = int(model.predict([text])[0])
        try:
            score = float(model.predict_proba([text])[0].max())
        except Exception:  # pragma: no cover - classifier without predict_proba
            score = 1.0
        return {"label": label, "language": _LABELS.get(label, "en"), "score": score}

    return _detect_language_heuristic(text, hint)


def _detect_language_heuristic(text: str, hint: str | None = None) -> dict:
    """Fallback detector: Kinyarwanda-token heuristic + langdetect (no artifact)."""
    tokens = re.findall(r"[a-z']+", (text or "").lower())
    if tokens:
        hits = sum(1 for t in tokens if t in _RW_MARKERS)
        if hits >= 2 or (hits / len(tokens)) > 0.12:
            return {"label": 1, "language": "rw", "score": 0.75}

    try:
        from langdetect import detect

        code = detect(text)
        if code == "en":
            return {"label": 0, "language": "en", "score": 0.7}
    except Exception:
        pass

    # Unsure — fall back to the client hint if it is valid, else English.
    if hint in ("en", "rw"):
        return {"label": 0 if hint == "en" else 1, "language": hint, "score": 0.5}
    return {"label": 0, "language": "en", "score": 0.5}
