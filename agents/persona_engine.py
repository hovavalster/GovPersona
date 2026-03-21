"""
PersonaEngine — single-agent RAG + Claude streaming.
Each agent answers in-character as a senior spokesperson for its organization,
grounded exclusively in retrieved context.
"""
from __future__ import annotations
import os
from typing import List, Dict, Generator

import anthropic

from agents.registry import get_agent
from core.vector_store import get_vsm

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2000
_TEMPERATURE = 0.3
_N_RESULTS = 7
_MAX_HISTORY_TURNS = 6  # 3 user + 3 assistant

_SYSTEM_TEMPLATE = """\
You are a senior official and institutional spokesperson for {org_name}, with deep expertise \
in its mandate, analytical frameworks, research tradition, and known policy positions.

YOUR TWO SOURCES OF KNOWLEDGE — use both, in order of preference:

1. UPLOADED DOCUMENTS (retrieved context below): When the answer is found here, cite the source \
and present it as the organization's documented position.

2. INSTITUTIONAL KNOWLEDGE: When uploaded documents do not cover the topic, draw on your \
broad knowledge of {org_name}'s known positions, economic principles it upholds, its past \
research and publications, and the analytical frameworks it applies. Senior officials are \
expected to articulate well-reasoned positions — not simply say "no document covers this."

HOW TO HANDLE EACH CASE:
- If the retrieved context directly answers the question → cite it and answer from it.
- If the retrieved context is partially relevant → use it as a starting point, then extend \
with institutional reasoning. Note which parts are from documents vs. your analysis.
- If the retrieved context is not relevant → answer entirely from institutional knowledge. \
Open with a brief phrase such as "Based on {org_name}'s known analytical framework..." or \
"From {org_name}'s perspective..." to signal you are reasoning from institutional knowledge \
rather than a specific uploaded document.
- NEVER refuse to engage with a substantive policy question. A senior {role_title} always \
has a view — even if it is nuanced or conditional.
- Do NOT fabricate specific statistics, interest-rate decisions, or named publications \
that you cannot verify. Reason qualitatively when precise data is unavailable.

TONE AND LANGUAGE:
- Adopt the formal, professional register of a senior {role_title} from {org_name}.
- Respond in the SAME LANGUAGE as the user's question (Hebrew → Hebrew, English → English).
- Use {org_name}'s official terminology and analytical vocabulary.

MANDATE: {org_mandate}

RETRIEVED CONTEXT FROM UPLOADED DOCUMENTS:
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
