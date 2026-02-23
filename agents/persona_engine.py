"""
PersonaEngine — single-agent RAG + Claude streaming.
Each agent answers in-character as a senior spokesperson for its organization,
grounded exclusively in retrieved context.
"""
from __future__ import annotations
import os
from typing import List, Dict, Any, Generator

import anthropic

from agents.registry import get_agent
from core.vector_store import get_vsm

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500
_TEMPERATURE = 0.2
_N_RESULTS = 5
_MAX_HISTORY_TURNS = 6  # 3 user + 3 assistant

_SYSTEM_TEMPLATE = """\
You are an official spokesperson and senior analyst for {org_name}.

PERSONA RULES:
1. Answer ONLY based on the retrieved context provided below.
2. Adopt the formal, professional tone of a senior {role_title} from {org_name}.
3. If the policy is unclear in the context, state: "{org_name} has not issued an official position on this matter."
4. Do NOT speculate beyond the provided context.
5. Respond in the SAME LANGUAGE as the user's question (Hebrew → Hebrew, English → English).
6. Use {org_name}'s official terminology.

MANDATE: {org_mandate}

RETRIEVED CONTEXT:
{context}
"""


class PersonaEngine:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.vsm = get_vsm()

    def _retrieve_context(self, org_id: str, query: str, n_results: int = _N_RESULTS) -> str:
        """Search vector store and format results as numbered source blocks."""
        results = self.vsm.search(org_id, query, n_results=n_results)
        if not results:
            return "[No documents have been uploaded for this agency yet.]"

        parts = []
        for i, r in enumerate(results, 1):
            source = r["metadata"].get("source", "unknown")
            parts.append(f"[Source {i}: {source}]\n{r['text']}")
        return "\n\n---\n\n".join(parts)

    def _build_system_prompt(self, org_id: str, context: str) -> str:
        cfg = get_agent(org_id)
        return _SYSTEM_TEMPLATE.format(
            org_name=cfg["name"],
            role_title=cfg["role_title"],
            org_mandate=cfg["org_mandate"],
            context=context,
        )

    def _build_messages(
        self,
        question: str,
        chat_history: List[Dict[str, str]] | None,
    ) -> List[Dict[str, str]]:
        messages = []
        if chat_history:
            # Keep last N turns (each turn = 1 user + 1 assistant)
            trimmed = chat_history[-_MAX_HISTORY_TURNS:]
            messages.extend(trimmed)
        messages.append({"role": "user", "content": question})
        return messages

    def ask(
        self,
        org_id: str,
        question: str,
        chat_history: List[Dict[str, str]] | None = None,
    ) -> str:
        """Non-streaming call. Returns the full response string."""
        context = self._retrieve_context(org_id, question)
        system_prompt = self._build_system_prompt(org_id, context)
        messages = self._build_messages(question, chat_history)

        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text

    def ask_streaming(
        self,
        org_id: str,
        question: str,
        chat_history: List[Dict[str, str]] | None = None,
    ) -> Generator[str, None, None]:
        """
        Streaming call. Yields text chunks — compatible with st.write_stream().
        """
        context = self._retrieve_context(org_id, question)
        system_prompt = self._build_system_prompt(org_id, context)
        messages = self._build_messages(question, chat_history)

        with self.client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text


_engine_instance: PersonaEngine | None = None


def get_engine() -> PersonaEngine:
    """Module-level singleton."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PersonaEngine()
    return _engine_instance
