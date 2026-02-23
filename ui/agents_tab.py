"""
Manage tab — per-agent stats, clear collection, and add new agent form.
"""
from __future__ import annotations

import streamlit as st

from agents.registry import list_agents, get_agent, add_agent, delete_agent
from core.vector_store import get_vsm


def render_agents_tab():
    st.header("⚙️ Manage Agents")
    st.caption(
        "View knowledge base stats for each agency, clear their document collections, "
        "or add a new custom agency."
    )

    vsm = get_vsm()
    agents = list_agents()

    if not agents:
        st.warning("No agents found. Add one below.")
    else:
        st.subheader("Current Agents")
        for org_id, display_name in agents:
            cfg = get_agent(org_id)
            chunk_count = vsm.get_doc_count(org_id)

            with st.expander(f"**{display_name}**", expanded=False):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Role:** {cfg.get('role_title', '—')}")
                    st.markdown(f"**Mandate:** {cfg.get('org_mandate', '—')}")
                    st.markdown(f"**Tone:** {cfg.get('tone', '—')}")
                    st.markdown(f"**Collection ID:** `{org_id}`")
                with col2:
                    st.metric("Chunks indexed", chunk_count)

                st.markdown("---")
                danger_col1, danger_col2 = st.columns(2)

                with danger_col1:
                    if st.button(
                        f"🗑️ Clear Collection",
                        key=f"clear_{org_id}",
                        help="Deletes all indexed chunks for this agency. Cannot be undone.",
                    ):
                        vsm.clear_collection(org_id)
                        st.success(f"Collection cleared for {display_name}.")
                        st.rerun()

    # ── Add New Agent ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("➕ Add New Agent")

    with st.expander("Expand to add a new agency", expanded=False):
        with st.form("add_agent_form"):
            st.markdown("Fill in the details for the new agency. It will appear in all dropdowns immediately.")

            new_id = st.text_input(
                "Agent ID (slug, no spaces)",
                placeholder="prime_ministers_office",
                help="Lowercase letters, numbers, and underscores only. Used as the ChromaDB collection name.",
            )
            new_name = st.text_input(
                "Display name (English)",
                placeholder="Prime Minister's Office",
            )
            new_name_he = st.text_input(
                "Display name (Hebrew)",
                placeholder="משרד ראש הממשלה",
            )
            new_role = st.text_input(
                "Role title",
                placeholder="Senior Policy Advisor / Director General",
            )
            new_mandate = st.text_area(
                "Organization mandate",
                placeholder="Responsible for coordinating government policy and national strategic planning.",
                height=80,
            )
            new_tone = st.text_input(
                "Communication tone",
                placeholder="formal, policy-oriented, strategic",
            )

            submitted = st.form_submit_button("Create Agent", type="primary")

            if submitted:
                if not new_id or not new_name:
                    st.error("Agent ID and Display name are required.")
                elif " " in new_id:
                    st.error("Agent ID cannot contain spaces. Use underscores.")
                else:
                    config = {
                        "name": f"{new_name} ({new_name_he})" if new_name_he else new_name,
                        "name_he": new_name_he,
                        "name_en": new_name,
                        "role_title": new_role,
                        "org_mandate": new_mandate,
                        "tone": new_tone,
                    }
                    ok = add_agent(new_id, config)
                    if ok:
                        st.success(
                            f"✅ Agent **{new_name}** created! "
                            f"Upload documents in the Train Agent tab to give it knowledge."
                        )
                        st.rerun()
                    else:
                        st.error(f"An agent with ID '{new_id}' already exists.")
