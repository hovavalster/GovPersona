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


def _is_hebrew_dominant(text: str, threshold: float = 0.30) -> bool:
    """Return True if more than threshold fraction of alphabetic chars are Hebrew."""
    alpha_chars = [c for c in text if unicodedata.category(c).startswith("L")]
    if not alpha_chars:
        return False
    hebrew_count = sum(
        1 for c in alpha_chars
        if _HEBREW_RANGE_START <= ord(c) <= _HEBREW_RANGE_END
    )
    return (hebrew_count / len(alpha_chars)) >= threshold


def _render_message(role: str, content: str, is_rtl: bool = False):
    """Render a single chat bubble, with RTL wrapper if Hebrew."""
    with st.chat_message(role):
        if is_rtl:
            st.markdown(
                f'<div dir="rtl" style="text-align: right;">{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(content)


def _on_agent_change():
    """Clear history when the user switches agents."""
    st.session_state["chat_history"] = []
    st.session_state["chat_messages"] = []


def render_chat_tab():
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

    # Show doc count for context
    vsm = get_vsm()
    doc_count = vsm.get_doc_count(org_id)
    with col2:
        st.metric("Chunks Indexed", doc_count)
        if doc_count == 0:
            st.caption("⚠️ No docs uploaded yet")

    # Initialize session state
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Render message history
    for msg in st.session_state["chat_messages"]:
        _render_message(
            msg["role"],
            msg["content"],
            is_rtl=msg.get("rtl", False),
        )

    # Clear button
    if st.session_state["chat_messages"]:
        if st.button("🗑️ Clear conversation", key="clear_chat"):
            st.session_state["chat_history"] = []
            st.session_state["chat_messages"] = []
            st.rerun()

    # Chat input
    if question := st.chat_input("Ask your question (Hebrew or English)..."):
        rtl = _is_hebrew_dominant(question)
        _render_message("user", question, is_rtl=rtl)
        st.session_state["chat_messages"].append(
            {"role": "user", "content": question, "rtl": rtl}
        )

        engine = get_engine()
        try:
            with st.chat_message("assistant"):
                response = st.write_stream(
                    engine.ask_streaming(
                        org_id,
                        question,
                        chat_history=st.session_state["chat_history"],
                    )
                )

            response_rtl = _is_hebrew_dominant(response)
            st.session_state["chat_messages"].append(
                {"role": "assistant", "content": response, "rtl": response_rtl}
            )

            # Update LangChain-style history for multi-turn context
            st.session_state["chat_history"].append(
                {"role": "user", "content": question}
            )
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": response}
            )

        except Exception as e:
            st.error(f"Error contacting Claude: {e}")
