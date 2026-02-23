"""
CouncilEngine — multi-agent structured debate + synthesis.
Orchestrates 2+ agents in a round-robin dialogue, then produces a joint output
via a neutral Rapporteur synthesis step.
"""
from __future__ import annotations
import os
from typing import List, Dict, Any

import anthropic

from agents.registry import get_agent
from core.vector_store import get_vsm

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2000
_TEMPERATURE = 0.3

_TURN_SYSTEM_TEMPLATE = """\
You are a senior official and institutional spokesperson for {org_name}, participating \
in a structured inter-agency policy discussion.

YOUR TWO SOURCES OF KNOWLEDGE — use both, in order of preference:

1. UPLOADED DOCUMENTS (retrieved context below): Cite these when they are relevant.
2. INSTITUTIONAL KNOWLEDGE: When documents do not cover the topic, draw on {org_name}'s \
known positions, analytical frameworks, and policy tradition. Senior officials always \
have a view — do not stay silent because a specific document is absent.

DISCUSSION RULES:
- Be substantive and concise — you are one participant in a multi-agency dialogue.
- You may respectfully reference or push back on positions raised by other agencies.
- Signal your source: "Our published analysis shows..." (document) vs. \
"From {org_name}'s analytical perspective..." (institutional reasoning).
- Do NOT fabricate specific statistics or named publications you cannot verify.
- Respond in the SAME LANGUAGE as the topic statement.
- Speak with the authority and tone of a senior {role_title}.

MANDATE: {org_mandate}

YOUR ORGANIZATION'S RETRIEVED CONTEXT:
{context}
"""

_SYNTHESIS_SYSTEM_TEMPLATE = """\
You are a neutral government Rapporteur. Your task is to synthesize the positions of
multiple government agencies into a single coherent {output_type}.

You must:
1. Represent each agency's view accurately and fairly.
2. Identify areas of agreement and conflict.
3. Propose a unified recommendation that balances all positions.
4. Write in formal government language.
5. Use the same language as the topic statement.

Structure the {output_type} as follows:
{structure_guide}

TOPIC: {topic}

AGENCY DIALOGUE:
{formatted_dialogue}

Produce the final {output_type} now.
"""

_OUTPUT_STRUCTURES = {
    "policy_report": """\
# Policy Report: {topic}

## Executive Summary
[2-3 paragraph overview]

## Agency Positions
[One section per agency with their documented stance]

## Areas of Agreement
[Common ground across agencies]

## Points of Divergence
[Where agencies differ and why]

## Unified Recommendations
[Numbered list of actionable recommendations]

## Conclusion
""",
    "legislation_draft": """\
# Draft Legislation: {topic}

## Preamble
[Purpose and background]

## Article 1 — Definitions
## Article 2 — Scope and Application
## Article 3 — Key Provisions
[Derived from agency positions]
## Article 4 — Implementation
## Article 5 — Enforcement and Oversight
## Article 6 — Entry into Force
""",
    "briefing_note": """\
# Ministerial Briefing Note

**Subject:** {topic}
**Prepared by:** Inter-Agency Council
**Classification:** Internal

## Key Points (3-5 bullets)
## Agency Positions (one line each)
## Recommended Action
## Next Steps
""",
}


class CouncilEngine:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.vsm = get_vsm()

    def _retrieve_context(self, org_id: str, query: str, n_results: int = 4) -> str:
        results = self.vsm.search(org_id, query, n_results=n_results)
        if not results:
            return "[No documents uploaded for this agency yet.]"
        parts = []
        for i, r in enumerate(results, 1):
            source = r["metadata"].get("source", "unknown")
            parts.append(f"[Source {i}: {source}]\n{r['text']}")
        return "\n\n---\n\n".join(parts)

    def run_turn(
        self,
        org_id: str,
        topic: str,
        prior_dialogue: List[Dict[str, Any]],
    ) -> str:
        """
        Single agent's turn in the dialogue.
        prior_dialogue: list of {"org_id", "org_name", "response"} dicts from earlier turns.
        The agent's own previous turns are excluded to prevent repetition.
        """
        cfg = get_agent(org_id)
        context = self._retrieve_context(org_id, topic)

        system = _TURN_SYSTEM_TEMPLATE.format(
            org_name=cfg["name"],
            role_title=cfg["role_title"],
            org_mandate=cfg["org_mandate"],
            context=context,
        )

        # Build user message with topic + prior turns from OTHER agents
        other_turns = [
            t for t in prior_dialogue if t["org_id"] != org_id
        ]

        user_content = f"DISCUSSION TOPIC: {topic}\n\n"
        if other_turns:
            user_content += "PRIOR CONTRIBUTIONS FROM OTHER AGENCIES:\n\n"
            for turn in other_turns:
                user_content += f"**{turn['org_name']}:**\n{turn['response']}\n\n"
            user_content += "---\n\nPlease provide your organization's position on this topic."
        else:
            user_content += "Please provide your organization's position on this topic."

        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    def synthesize(
        self,
        topic: str,
        dialogue: List[Dict[str, Any]],
        output_type: str = "policy_report",
    ) -> str:
        """
        Neutral synthesis step — combines all agent positions into a final document.
        output_type: "policy_report" | "legislation_draft" | "briefing_note"
        """
        structure = _OUTPUT_STRUCTURES.get(output_type, _OUTPUT_STRUCTURES["policy_report"])
        structure_guide = structure.format(topic=topic)

        formatted_dialogue = ""
        for turn in dialogue:
            formatted_dialogue += f"**{turn['org_name']}** (Round {turn.get('round', 1)}):\n"
            formatted_dialogue += turn["response"] + "\n\n---\n\n"

        output_type_label = output_type.replace("_", " ").title()

        system = _SYNTHESIS_SYSTEM_TEMPLATE.format(
            output_type=output_type_label,
            structure_guide=structure_guide,
            topic=topic,
            formatted_dialogue=formatted_dialogue,
        )

        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=3000,
            temperature=0.2,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Synthesize the agency dialogue into a {output_type_label}. "
                        f"Topic: {topic}"
                    ),
                }
            ],
        )
        return response.content[0].text


_council_instance: CouncilEngine | None = None


def get_council_engine() -> CouncilEngine:
    """Module-level singleton."""
    global _council_instance
    if _council_instance is None:
        _council_instance = CouncilEngine()
    return _council_instance
