"""tests/test_safety.py — ML stub contracts.

These guard the shape/keys the routers depend on, so the real models can be
swapped in without breaking the API.
"""

from app.ml.safety_classifier import classify_safety
from app.ml.topic_classifier import classify_topic


def test_classify_safety_shape():
    result = classify_safety("hello")
    assert set(result) >= {"label", "score"}
    assert result["label"] in (0, 1)
    assert 0.0 <= result["score"] <= 1.0


def test_classify_topic_shape():
    result = classify_topic("hello")
    assert set(result) >= {"label", "topic", "score"}
    assert 0 <= result["label"] <= 6
    assert isinstance(result["topic"], str)
