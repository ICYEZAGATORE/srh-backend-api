"""tests/test_embeddings.py — SRHEmbeddingModel contract (local, no network)."""

from app.ml.embeddings import get_embedding_model

EXPECTED_DIM = 384


def test_embed_query_returns_correct_dimension():
    model = get_embedding_model()
    vec = model.embed_query("Where can I get contraception in Rwanda?")
    assert isinstance(vec, list)
    assert len(vec) == EXPECTED_DIM
    assert all(isinstance(x, float) for x in vec)


def test_embed_query_same_text_returns_same_vector():
    model = get_embedding_model()
    text = "What are the symptoms of an STI?"
    v1 = model.embed_query(text)
    v2 = model.embed_query(text)
    assert v1 == v2  # deterministic for identical input


def test_embed_documents_batch_shape():
    model = get_embedding_model()
    vecs = model.embed_documents(["hello", "muraho neza"])
    assert len(vecs) == 2
    assert all(len(v) == EXPECTED_DIM for v in vecs)
