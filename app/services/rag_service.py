"""
rag_service.py — RAG pipeline using trained classifiers + unified LLM client.
"""

import sys
import time
from pathlib import Path
from typing import Optional

import faiss
import pandas as pd

from app.config import settings
from app.services.ml_loader import trained_models
from app.services.llm_client import llm_client


# Allow importing the embedder from srh-ml-model/src
ML_SRC = Path(settings.ML_SRC_PATH).resolve()
if str(ML_SRC) not in sys.path:
    sys.path.insert(0, str(ML_SRC))


SYSTEM_PROMPT_EN = (
    "You are a knowledgeable, non-judgmental SRH health educator for Rwandan "
    "teenagers and persons with disabilities. Use ONLY the provided context to "
    "answer. Keep answers clear, factual, and age-appropriate (suitable for ages "
    "13 and above). If the context does not contain enough information, say so "
    "clearly. Never shame the user. Always encourage consulting a health worker "
    "for personal medical decisions."
)
SYSTEM_PROMPT_RW = (
    "Uri umujyanama w'ubuzima bw'imororokano, udafata umuntu nabi, ukorera "
    "urubyiruko rw'u Rwanda n'abantu bafite ubumuga. Koreshanya GUSA amakuru "
    "atanzwe kugira ngo usubize. Subiza neza, ukuri, kandi mu buryo bufite "
    "akamaro. Niba amakuru atanzwe arimo ubushobozi buke, bivuge bisobanutse."
)
FALLBACK_EN = (
    "I'm not able to answer that question here. Please speak to a trusted "
    "health worker or contact Isange One Stop Centres for support."
)
FALLBACK_RW = (
    "Ntashobora gusubiza icyo kibazo hano. Baza umujyanama w'ubuzima ukenya "
    "cyangwa hamagara Isange One Stop Centres."
)


class RAGService:
    def __init__(self):
        self.index: Optional[faiss.Index] = None
        self.chunks_df: Optional[pd.DataFrame] = None
        self._embedder = None
        self._loaded = False

    async def load(self):
        if self._loaded:
            return

        print("Loading trained ML classifiers...")
        trained_models.load()

        index_path = Path(settings.FAISS_INDEX_PATH).resolve()
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index missing at {index_path}")
        self.index = faiss.read_index(str(index_path))

        chunks_path = Path(settings.CHUNKS_CSV_PATH).resolve()
        self.chunks_df = pd.read_csv(chunks_path)

        try:
            from embedder import get_embedder
            self._embedder = get_embedder()
        except ImportError:
            print("WARNING: embedder not found.")

        self._loaded = True
        print(f"  FAISS index:   {self.index.ntotal} vectors")
        print(f"  Chunks loaded: {len(self.chunks_df)} rows")
        print(f"  LLM provider:  {llm_client.provider} ({llm_client.model_name})")

    def _retrieve(self, query: str, lang: str, topic: str = None, top_k: int = 3):
        if self._embedder is None or self.index is None:
            return []
        q_vec = self._embedder.embed_query(query)
        scores, indices = self.index.search(q_vec, top_k * 5)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks_df):
                continue
            chunk = self.chunks_df.iloc[idx]
            if chunk["language"] != lang:
                continue
            results.append({
                "text": chunk["text"], "topic": chunk["topic"],
                "score": round(float(score), 4),
                "topic_match": chunk["topic"] == topic if topic else None,
            })
            if len(results) >= top_k * 2:
                break

        if topic:
            matched = [r for r in results if r['topic_match']]
            unmatched = [r for r in results if not r['topic_match']]
            return (matched + unmatched)[:top_k]
        return results[:top_k]

    async def _generate(self, query: str, context: list, lang: str) -> dict:
        if llm_client.provider == 'none':
            best = context[0]['text'] if context else FALLBACK_EN
            return {'text': best, 'latency_ms': 0, 'tokens_used': 0, 'model': 'retrieval-only'}

        context_text = "\n\n".join(f"[{c['topic']}] {c['text']}" for c in context)
        system = SYSTEM_PROMPT_EN if lang == "en" else SYSTEM_PROMPT_RW
        user_msg = f"Context:\n{context_text}\n\nQuestion: {query}"

        start = time.time()
        try:
            response_text = await llm_client.chat(system, user_msg, max_tokens=400, temperature=0.3)
        except Exception as e:
            return {'text': f"Generation error: {e}", 'latency_ms': 0,
                    'tokens_used': 0, 'model': llm_client.model_name}
        latency_ms = round((time.time() - start) * 1000)
        return {"text": response_text, "latency_ms": latency_ms,
                "tokens_used": 0, "model": llm_client.model_name}

    async def query(self, user_query: str) -> dict:
        if not self._loaded:
            await self.load()

        lang = trained_models.detect_language(user_query)

        safety = trained_models.is_safe(user_query)
        if not safety['is_safe']:
            return {"response": FALLBACK_RW if lang == "rw" else FALLBACK_EN,
                    "language": lang, "safe": False,
                    "unsafe_probability": safety['unsafe_probability'],
                    "blocked_at": "query", "latency_ms": 0,
                    "topics": [], "retrieval_scores": []}

        topic_pred = trained_models.predict_topic(user_query)
        context = self._retrieve(user_query, lang, topic=topic_pred['topic'], top_k=3)
        if not context:
            return {"response": FALLBACK_RW if lang == "rw" else FALLBACK_EN,
                    "language": lang, "safe": True, "blocked_at": "no_context",
                    "latency_ms": 0, "topics": [], "retrieval_scores": [],
                    "predicted_topic": topic_pred['topic']}

        gen = await self._generate(user_query, context, lang)

        resp_safety = trained_models.is_safe(gen["text"])
        if not resp_safety['is_safe']:
            return {"response": FALLBACK_RW if lang == "rw" else FALLBACK_EN,
                    "language": lang, "safe": False, "blocked_at": "response",
                    "latency_ms": gen["latency_ms"], "topics": [],
                    "retrieval_scores": [], "predicted_topic": topic_pred['topic']}

        return {
            "response": gen["text"], "language": lang, "safe": True,
            "latency_ms": gen["latency_ms"], "tokens_used": gen.get("tokens_used", 0),
            "model": gen["model"], "topics": [c["topic"] for c in context],
            "retrieval_scores": [c["score"] for c in context],
            "predicted_topic": topic_pred['topic'],
            "topic_confidence": topic_pred['confidence'],
        }


rag_service = RAGService()