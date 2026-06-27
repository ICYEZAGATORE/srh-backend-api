"""
app/ml/safety_classifier.py — Model 1: binary safety classifier.

STUB: returns mock data while SRH-ML-MODEL is in development. Keep this
signature stable so the real model can be swapped in without touching any
router code.

To integrate the real model:
    import joblib
    _model = joblib.load(settings.SAFETY_MODEL_PATH)
    def classify_safety(text: str) -> dict:
        pred = _model.predict([text])[0]
        proba = _model.predict_proba([text])[0].max()
        return {"label": int(pred), "score": float(proba)}
"""


def classify_safety(text: str) -> dict:
    # STUB — replace with joblib.load when model is ready
    return {"label": 0, "score": 0.95}
    # label 0 = SAFE, label 1 = UNSAFE
