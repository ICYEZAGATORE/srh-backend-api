"""
app/ml/topic_classifier.py — Model 3: 7-class SRH topic classifier.

Loads ``models/topic_classifier_B.pkl`` (word TF-IDF + XGBoost, approach B —
augmented minority) once via the model registry. The model's integer labels
match the TOPICS map below (verified against the training label map).

NOTE: the topic model is trained on English vocabulary; Kinyarwanda queries get
a low-confidence guess. That is acceptable here — topic is used for retrieval
routing/analytics, and retrieval is additionally filtered by detected language.

If the artifact is missing, falls back to the previous default (general_srh).
Return shape ``{"label", "topic", "score"}`` is stable.
"""

from __future__ import annotations

from app.ml.model_registry import get_topic_model

# Index -> human-readable topic, for mapping the model's label to a string.
TOPICS = {
    0: "contraception",
    1: "sti_hiv",
    2: "pregnancy",
    3: "puberty",
    4: "gbv_consent",
    5: "disability_srh",
    6: "general_srh",
}


def classify_topic(text: str) -> dict:
    model = get_topic_model()
    if model is None:
        return {"label": 6, "topic": "general_srh", "score": 0.80}

    label = int(model.predict([text])[0])
    try:
        score = float(model.predict_proba([text])[0].max())
    except Exception:  # pragma: no cover - classifier without predict_proba
        score = 1.0
    return {"label": label, "topic": TOPICS.get(label, "general_srh"), "score": score}
