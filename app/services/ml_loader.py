"""
ml_loader.py — Loads all trained ML classifiers at app startup.

Replaces the hardcoded keyword rules in rag_service.py with the trained models
from notebooks 04 / 05 / 06.

Bundle structure for every classifier:
    {
        'classifier':    fitted sklearn or xgboost model
        'vectorizer':    fitted feature extractor
        'threshold':     decision threshold (safety only)
        'classes':       label list
        'label_encoder': LabelEncoder (topic only)
        'model_name':    str
    }
"""

import joblib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.config import settings


# Paths to trained model files — these are produced by notebooks 04 / 05 / 06
MODELS_DIR = Path(settings.ML_SRC_PATH).parent / 'models_trained'

SAFETY_PATH = MODELS_DIR / 'safety_classifier.joblib'
LANGUAGE_PATH = MODELS_DIR / 'language_detector.joblib'
TOPIC_PATH = MODELS_DIR / 'topic_classifier.joblib'


@dataclass
class TrainedModels:
    """Container for all trained classifiers. Singleton, loaded once at startup."""
    safety_bundle: Optional[dict] = None
    language_bundle: Optional[dict] = None
    topic_bundle: Optional[dict] = None
    loaded: bool = False

    def load(self):
        """Load all bundles. Skip silently if a file is missing
        (allows the backend to start before notebooks have been run)."""
        if self.loaded:
            return

        if SAFETY_PATH.exists():
            self.safety_bundle = joblib.load(SAFETY_PATH)
            print(f"  Safety classifier:   {self.safety_bundle.get('model_name')} "
                  f"(threshold={self.safety_bundle.get('threshold')})")
        else:
            print(f"  Safety classifier:   NOT FOUND at {SAFETY_PATH}")

        if LANGUAGE_PATH.exists():
            self.language_bundle = joblib.load(LANGUAGE_PATH)
            print(f"  Language detector:   {self.language_bundle.get('model_name')}")
        else:
            print(f"  Language detector:   NOT FOUND at {LANGUAGE_PATH}")

        if TOPIC_PATH.exists():
            self.topic_bundle = joblib.load(TOPIC_PATH)
            print(f"  Topic classifier:    {self.topic_bundle.get('model_name')}")
        else:
            print(f"  Topic classifier:    NOT FOUND at {TOPIC_PATH}")

        self.loaded = True

    # ── Inference helpers ─────────────────────────────────────────────────────

    def is_safe(self, query: str) -> dict:
        """
        Returns: {'is_safe': bool, 'unsafe_probability': float, 'fallback': bool}
        If safety bundle is missing, falls back to allowing everything (logs warning).
        """
        if self.safety_bundle is None:
            return {'is_safe': True, 'unsafe_probability': 0.0, 'fallback': True}
        X = self.safety_bundle['vectorizer'].transform([query])
        proba = self.safety_bundle['classifier'].predict_proba(X)[0, 1]
        threshold = self.safety_bundle.get('threshold', 0.5)
        return {
            'is_safe': proba < threshold,
            'unsafe_probability': round(float(proba), 4),
            'fallback': False,
        }

    def detect_language(self, text: str) -> str:
        """
        Returns: 'en' or 'rw'. Falls back to 'en' if model not loaded.
        """
        if self.language_bundle is None:
            return 'en'
        X = self.language_bundle['vectorizer'].transform([text])
        pred = self.language_bundle['classifier'].predict(X)[0]
        classes = self.language_bundle.get('classes', ['en', 'rw'])
        return classes[int(pred)]

    def predict_topic(self, query: str) -> dict:
        """
        Returns: {'topic': str, 'confidence': float or None}
        """
        if self.topic_bundle is None:
            return {'topic': 'unknown', 'confidence': None}
        X = self.topic_bundle['vectorizer'].transform([query])
        pred_idx = self.topic_bundle['classifier'].predict(X)[0]
        topic = self.topic_bundle['classes'][int(pred_idx)]

        # Confidence if the classifier supports predict_proba
        confidence = None
        if hasattr(self.topic_bundle['classifier'], 'predict_proba'):
            proba = self.topic_bundle['classifier'].predict_proba(X)[0]
            confidence = round(float(max(proba)), 4)
        return {'topic': topic, 'confidence': confidence}


# Module-level singleton
trained_models = TrainedModels()
