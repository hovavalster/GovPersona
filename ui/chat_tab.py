"""
Chat tab — single-agent Q&A with streaming, RTL Hebrew support, and chat history.
"""
from __future__ import annotations
import unicodedata

import streamlit as st

from agents.registry import list_agents
from agents.persona_engine import get_engine
from core.vector_store import get_vsm

_HEBREW_RANGE_START = 0x0590
_HEBREW_RANGE_END = 0x05FF

# ── CSS ───────────────────────────────────────────────────────────────────────
_CHAT_CSS = """
<style>
/* Tighter paragraph spacing inside chat bubbles */
[data-testid="stChatMessage"] p {
    margin-top: 0.2em !important;
    margin-bottom: 0.3em !important;
    line-height: 1.7 !important;
}
[data-testid="stChatMessage"] li {
    margin-bottom: 0.15em !important;
    line-height: 1.6 !important;
}
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol {
    margin-top: 0.25em !important;
    margin-bottom: 0.25em !important;
}
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    margin-top: 0.5em !important;
    margin-bottom: 0.2em !important;
}

/* Clean readable font with Hebrew glyph support */
[data-testid="stChatMessage"],
[data-testid="stChatMessage"] * {
    font-family: 'Segoe UI', 'Arial', 'Helvetica Neue', sans-serif !important;
    font-size: 15px !important;
}

/* RTL text block used for Hebrew responses */
.gov-rtl {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext;
    font-family: 'Segoe UI', 'Arial', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.7 !important;
}
.gov-rtl p   { margin-top: 0.2em !important; margin-bottom: 0.3em !important; }
.gov-rtl li  { margin-bottom: 0.15em !important; }
.gov-rtl ul,
.gov-rtl ol  { margin-top: 0.25em !important; margin-bottom: 0.25em !important; }
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_hebrew_dominant(text: str, threshold: float = 0.30) -> bool:
    alpha = [c for c in text if unicodedata.category(c).startswith("L")]
    if not alpha:
        return False
    heb = sum(1 for c in alpha if _HEBREW_RANGE_START <= ord(c) <= _HEBREW_RANGE_END)
    return (heb / len(alpha)) >= threshold


def _render_bubble(role: str, content: str, is_rtl: bool = False):
    """Render a stored message bubble (history replay)."""
    with st.chat_message(role):
        if is_rtl:
            # Use a div with explicit RTL so every paragraph flows right-to-left
            st.markdown(
                f'<div class="gov-rtl">{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(content)


def _stream_response(stream_gen, is_rtl: bool) -> str:
    """
    Stream the generator into a single st.empty() container.
    For Hebrew (RTL) responses the container is re-rendered on every chunk
    so the text flows right-to-left from the first character.
    Returns the full accumulated text.
    """
    container = st.empty()
    full_text = ""

    for chunk in stream_gen:
        full_text += chunk
        if is_rtl:
            container.markdown(
                f'<div class="gov-rtl">{full_text}▌</div>',
                unsafe_allow_html=True,
            )
        else:
            container.markdown(full_text + "▌")

    # Final render — remove cursor
    if is_rtl:
        container.markdown(
            f'<div class="gov-rtl">{full_text}</div>',
            unsafe_allow_html=True,
        )
    else:
        container.markdown(full_text)

    return full_text


def _on_agent_change():
    st.session_state["chat_history"] = []
    st.session_state["chat_messages"] = []


# ── Main render ───────────────────────────────────────────────────────────────

def render_chat_tab():
    # Inject CSS once per page load
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)

    st.header("🏛️ Agency Chat")
    st.caption("Ask any question — the selected agency will answer in-character, grounded in its uploaded documents.")

    agents = list_agents()
    if not agents:
        st.warning("No agents found. Check config/agents.json.")
        return

    agent_ids = [a[0] for a in agents]
    agent_names = [a[1] for a in agents]

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_idx = st.selectbox(
            "Select Agency",
            options=range(len(agent_ids)),
            format_func=lambda i: agent_names[i],
            key="selected_agent_idx",
            on_change=_on_agent_change,
        )
    org_id = agent_ids[selected_idx]

    vsm = get_vsm()
    doc_count = vsm.get_doc_count(org_id)
    with col2:
        st.metric("Chunks Indexed", doc_count)
        if doc_count == 0:
            st.caption("⚠️ No docs uploaded yet")

    # Initialise session state
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Replay history
    for msg in st.session_state["chat_messages"]:
        _render_bubble(msg["role"], msg["content"], is_rtl=msg.get("rtl", False))

    # Clear button
    if st.session_state["chat_messages"]:
        if st.button("🗑️ Clear conversation", key="clear_chat"):
            st.session_state["chat_history"] = []
            st.session_state["chat_messages"] = []
            st.rerun()

    # Input
    if question := st.chat_input("Ask your question (Hebrew or English)..."):
        q_rtl = _is_hebrew_dominant(question)
        _render_bubble("user", question, is_rtl=q_rtl)
        st.session_state["chat_messages"].append(
            {"role": "user", "content": question, "rtl": q_rtl}
        )

        engine = get_engine()
        try:
            with st.chat_message("assistant"):
                # Detect RTL from the question (agent will respond in same language)
                response = _stream_response(
                    engine.ask_streaming(
                        org_id,
                        question,
                        chat_history=st.session_state["chat_history"],
                    ),
                    is_rtl=q_rtl,
                )

            st.session_state["chat_messages"].append(
                {"role": "assistant", "content": response, "rtl": q_rtl}
            )
            st.session_state["chat_history"].extend([
                {"role": "user",      "content": question},
                {"role": "assistant", "content": response},
            ])

        except Exception as e:
            st.error(f"Error contacting Claude: {e}")
