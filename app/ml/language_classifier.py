"""
app/ml/language_classifier.py — Model 2: English vs Kinyarwanda language ID.

STUB (proxy): the trained character-n-gram classifier is not swapped in yet, so
this uses a lightweight ``langdetect`` + Kinyarwanda-token heuristic as a proxy
(see requirements: langdetect). Keep this signature stable so the real model
(``language_classifier.pkl``) can be dropped in without touching the router.

To integrate the real model:
    import joblib
    _model = joblib.load(settings.LANGUAGE_MODEL_PATH)
    def detect_language(text, hint=None):
        pred = _model.predict([text])[0]
        return {"label": int(pred), "language": {0: "en", 1: "rw"}[int(pred)], ...}

Label convention matches the trained model: english=0, kinyarwanda=1.
"""

from __future__ import annotations

import re

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

    Shape mirrors the other classifiers: ``{"label", "language", "score"}``.
    ``hint`` (e.g. the client-declared ``lang``) is used only as a tie-breaker.
    """
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
