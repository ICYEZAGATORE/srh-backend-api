"""
app/ml/topic_classifier.py — Model 3: 7-class SRH topic classifier.

STUB: returns mock data while SRH-ML-MODEL is in development. Keep this
signature stable so the real model can be swapped in without touching any
router code.
"""

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
    # STUB — replace with joblib.load when model is ready
    return {"label": 6, "topic": "general_srh", "score": 0.80}
    # 7 classes: contraception(0), sti_hiv(1), pregnancy(2), puberty(3),
    #            gbv_consent(4), disability_srh(5), general_srh(6)
