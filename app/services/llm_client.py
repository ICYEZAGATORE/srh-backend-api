"""
llm_client.py — Unified LLM interface that works with Gemini, Groq, or OpenAI.

The frontend doesn't need to know which provider is being used.
Adding a new provider only requires editing this file.
"""

import os
import asyncio
from typing import Optional
from app.config import settings


class UnifiedLLMClient:
    """Picks the first available provider and exposes a single chat() method."""

    def __init__(self):
        self.provider: Optional[str] = None
        self.model_name: Optional[str] = None
        self._client = None
        self._init()

    def _init(self):
        # Priority order: OpenAI (paid, best quality) → Gemini (free) → Groq (free)
        if getattr(settings, 'OPENAI_API_KEY', '').strip():
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY.strip())
            self.provider, self.model_name = 'openai', 'gpt-4o'

        elif getattr(settings, 'GOOGLE_API_KEY', '').strip():
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY.strip())
            self._client = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.provider, self.model_name = 'gemini', 'gemini-2.0-flash'

        elif getattr(settings, 'GROQ_API_KEY', '').strip():
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=settings.GROQ_API_KEY.strip())
            self.provider, self.model_name = 'groq', 'llama-3.3-70b-versatile'

        else:
            self.provider, self.model_name = 'none', 'retrieval-only'
            print("  WARNING: no LLM API key found — generation will return raw retrieved chunks.")

    async def chat(self, system_prompt: str, user_prompt: str,
                   max_tokens: int = 400, temperature: float = 0.3) -> str:
        """Single entry-point. Returns the assistant's reply string."""
        if self.provider == 'openai':
            resp = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{'role': 'system', 'content': system_prompt},
                          {'role': 'user', 'content': user_prompt}],
                max_tokens=max_tokens, temperature=temperature,
            )
            return resp.choices[0].message.content.strip()

        elif self.provider == 'groq':
            resp = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{'role': 'system', 'content': system_prompt},
                          {'role': 'user', 'content': user_prompt}],
                max_tokens=max_tokens, temperature=temperature,
            )
            return resp.choices[0].message.content.strip()

        elif self.provider == 'gemini':
            # Gemini doesn't have a native async client — run in thread
            full = f"{system_prompt}\n\n{user_prompt}"
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self._client.generate_content(
                    full,
                    generation_config={'temperature': temperature, 'max_output_tokens': max_tokens},
                )
            )
            return resp.text.strip()

        else:
            return "(LLM not configured — please set GOOGLE_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY.)"


# Module-level singleton
llm_client = UnifiedLLMClient()
