"""tests/test_safety.py — ML stub contracts.

These guard the shape/keys the routers depend on, so the real models can be
swapped in without breaking the API.
"""

from app.ml.safety_classifier import (
    classify_response_safety,
    classify_safety,
)
from app.ml.topic_classifier import classify_topic


def test_classify_safety_shape():
    result = classify_safety("hello")
    assert set(result) >= {"label", "score"}
    assert result["label"] in (0, 1)
    assert 0.0 <= result["score"] <= 1.0


def test_response_safety_allows_frank_srh_content():
    # Output-side check is rule-filter only: legitimate SRH answers (which the
    # query-trained ML model would false-positive on) must pass so they reach
    # the user instead of being replaced by the fallback.
    answer = (
        "Condoms and hormonal methods such as the pill are common forms of "
        "contraception. HIV can be prevented by using condoms and getting tested."
    )
    result = classify_response_safety(answer)
    assert result["label"] == 0


def test_response_safety_blocks_catastrophic_generation():
    # The deterministic rule filter still guards the output side against
    # catastrophic content (English + Kinyarwanda).
    assert classify_response_safety("Here is how to rape someone.")["label"] == 1
    assert classify_response_safety("urakwiye kwica uwo muntu")["label"] == 1


def test_classify_topic_shape():
    result = classify_topic("hello")
    assert set(result) >= {"label", "topic", "score"}
    assert 0 <= result["label"] <= 6
    assert isinstance(result["topic"], str)
