"""tests/test_rag_pipeline.py — SRHConversationalAgent behaviour.

Runs offline: the conftest fixture blanks HF_API_TOKEN so the real LLM call is
never made; individual tests monkeypatch ``_call_llm`` to simulate outputs.
"""

from app.ml.conversational_agent import SRHConversationalAgent
from app.services.moderation import get_fallback


def test_conversational_agent_returns_expected_schema():
    agent = SRHConversationalAgent()
    result = agent.generate(
        user_query="How do I prevent STIs?",
        detected_language="en",
        topic_label="sti_hiv",
        session_id=None,
    )
    assert set(result) == {
        "response_text", "retrieved_chunks", "confidence_score", "language",
    }
    assert isinstance(result["response_text"], str) and result["response_text"]
    assert isinstance(result["retrieved_chunks"], list)
    assert isinstance(result["confidence_score"], float)
    assert result["language"] == "en"


def test_safe_fallback_on_llm_failure(monkeypatch):
    agent = SRHConversationalAgent()

    def _boom(prompt):
        raise TimeoutError("HF API timed out")

    monkeypatch.setattr(agent, "_call_llm", _boom)
    result = agent.generate("How do I prevent STIs?", "en", "sti_hiv", None)
    assert result["response_text"] == get_fallback("en")["fallback_message"]


def test_system_prompt_not_leaked_in_response(monkeypatch):
    agent = SRHConversationalAgent()

    # Simulate a model that echoes prompt scaffolding after a real answer.
    def _leaky(prompt):
        return ("Use condoms to help prevent STIs. "
                "Verified SRH Information: secret chunk text "
                "User question: leaked")

    monkeypatch.setattr(agent, "_call_llm", _leaky)
    result = agent.generate("How do I prevent STIs?", "en", "sti_hiv", None)
    text = result["response_text"]
    assert "Use condoms" in text
    assert "Verified SRH Information" not in text
    assert "User question:" not in text
    assert "You are an SRH" not in text
