"""
app/ml/conversational_agent.py — RAG + LLM response generation.

STUB: returns a placeholder while SRH-ML-MODEL is in development. Keep this
signature stable so the real LangChain RAG pipeline can be swapped in without
touching any router code.

To integrate: embed the query (see app/ml/embeddings.py), retrieve top-k
chunks from the vector DB, pass ``context_chunks`` + a safety system prompt to
the chosen LLM, and return its (post-safety-checked) text in ``lang``.
"""


def generate_response(
    query: str, context_chunks: list, lang: str, simplified: bool = False
) -> str:
    # STUB — replace with LangChain RAG + LLM pipeline when model is ready
    if lang == "rw":
        return "Iki ni igisubizo cy'icyitegererezo. Modeli nyayo izashyirwaho vuba."
    return "This is a placeholder response. The real model will be integrated soon."
