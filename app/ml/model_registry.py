"""
app/ml/model_registry.py — central loader/cache for trained ML artifacts.

The classifiers (safety, topic, language) are bare scikit-learn ``Pipeline``
objects trained in the ``srh-ml-model`` repo and copied into ``models/``. They
are loaded **once** (cached) and reused across requests — never re-loaded per
call. ``warmup()`` is invoked from the FastAPI lifespan so the first real
request is not penalised with disk/deserialisation latency; individual getters
also lazy-load, so tests and scripts work without the lifespan running.

If an artifact is missing or fails to deserialise, the getter returns ``None``
and the calling classifier falls back to its safe default (see each module).
This keeps CI green when the (large) ``.pkl`` files are not present.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=None)
def _load(path_str: str) -> Optional[Any]:
    path = Path(path_str)
    if not path.is_file():
        logger.warning("ML artifact not found: %s — using fallback behaviour", path)
        return None
    try:
        import joblib

        model = joblib.load(path)
        logger.info("Loaded ML artifact: %s", path)
        return model
    except Exception as exc:  # pragma: no cover - defensive, exercised only on bad artifacts
        logger.warning("Failed to load ML artifact %s: %s — using fallback", path, exc)
        return None


def get_safety_model() -> Optional[Any]:
    return _load(settings.SAFETY_MODEL_PATH)


def get_topic_model() -> Optional[Any]:
    return _load(settings.TOPIC_MODEL_PATH)


def get_language_model() -> Optional[Any]:
    return _load(settings.LANGUAGE_MODEL_PATH)


def warmup() -> dict[str, bool]:
    """Eagerly load all artifacts (called from lifespan). Returns which loaded."""
    status = {
        "safety": get_safety_model() is not None,
        "topic": get_topic_model() is not None,
        "language": get_language_model() is not None,
    }
    logger.info("ML artifact warmup: %s", status)
    return status
