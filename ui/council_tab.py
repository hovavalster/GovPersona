"""
Council tab — multi-agent structured debate + synthesis output.
"""
from __future__ import annotations

import streamlit as st

from agents.registry import list_agents
from agents.council_engine import get_council_engine


_OUTPUT_TYPE_OPTIONS = {
    "Policy Report": "policy_report",
    "Legislation Draft": "legislation_draft",
    "Briefing Note": "briefing_note",
}


def render_council_tab():
    st.header("🤝 Agency Council")
    st.caption(
        "Convene multiple agencies for a structured debate. Each agency contributes its "
        "evidence-based position, then a neutral Rapporteur synthesizes a joint document."
    )

    agents = list_agents()
    if len(agents) < 2:
        st.warning("You need at least 2 agents to run a Council session. Add more in the Manage tab.")
        return

    agent_map = {name: oid for oid, name in agents}
    agent_names = [a[1] for a in agents]

    # ── Setup Panel ──────────────────────────────────────────────────────────
    st.subheader("1. Configure Council")

    selected_names = st.multiselect(
        "Select agencies (min 2)",
        options=agent_names,
        default=agent_names[:2],
        key="council_agents",
    )

    topic = st.text_area(
        "Discussion topic",
        placeholder="e.g. Rising inflation and its impact on the 2025 state budget",
        height=90,
        key="council_topic",
    )

    output_label = st.radio(
        "Output type",
        options=list(_OUTPUT_TYPE_OPTIONS.keys()),
        horizontal=True,
        key="council_output_type",
    )
    output_type = _OUTPUT_TYPE_OPTIONS[output_label]

    rounds = st.slider("Dialogue rounds per agent", min_value=1, max_value=3, value=1, key="council_rounds")

    if len(selected_names) < 2:
        st.info("Please select at least 2 agencies.")
        return

    if not topic.strip():
        st.info("Enter a discussion topic above to proceed.")
        return

    # ── Initialize state ────────────────────────────────────────────────────
    if "council_dialogue" not in st.session_state:
        st.session_state["council_dialogue"] = []
    if "council_synthesis" not in st.session_state:
        st.session_state["council_synthesis"] = ""
    if "council_ran" not in st.session_state:
        st.session_state["council_ran"] = False

    # ── Start Council ────────────────────────────────────────────────────────
    st.subheader("2. Run Dialogue")

    if st.button("▶️ Start Council", type="primary"):
        st.session_state["council_dialogue"] = []
        st.session_state["council_synthesis"] = ""
        st.session_state["council_ran"] = False

        engine = get_council_engine()
        selected_orgs = [(agent_map[n], n) for n in selected_names]

        progress = st.progress(0, text="Starting council...")
        total_turns = len(selected_orgs) * rounds
        turn_count = 0

        for round_num in range(1, rounds + 1):
            for org_id, org_name in selected_orgs:
                progress.progress(
                    turn_count / total_turns,
                    text=f"Round {round_num} — {org_name} is preparing its position...",
                )
                try:
                    response = engine.run_turn(
                        org_id=org_id,
                        topic=topic,
                        prior_dialogue=st.session_state["council_dialogue"],
                    )
                    st.session_state["council_dialogue"].append(
                        {
                            "org_id": org_id,
                            "org_name": org_name,
                            "response": response,
                            "round": round_num,
                        }
                    )
                except Exception as e:
                    st.error(f"Error getting response from {org_name}: {e}")
                turn_count += 1

        progress.progress(1.0, text="Council complete!")
        st.session_state["council_ran"] = True

    # ── Dialogue Viewer ──────────────────────────────────────────────────────
    if st.session_state["council_dialogue"]:
        st.subheader("3. Agency Positions")
        for turn in st.session_state["council_dialogue"]:
            with st.expander(
                f"**{turn['org_name']}** — Round {turn.get('round', 1)}",
                expanded=True,
            ):
                st.markdown(turn["response"])

        # ── Synthesis ────────────────────────────────────────────────────────
        st.subheader("4. Synthesis")

        if st.button("📋 Generate Final Report", type="secondary"):
            engine = get_council_engine()
            with st.spinner(f"Synthesizing {output_label}..."):
                try:
                    synthesis = engine.synthesize(
                        topic=topic,
                        dialogue=st.session_state["council_dialogue"],
                        output_type=output_type,
                    )
                    st.session_state["council_synthesis"] = synthesis
                except Exception as e:
                    st.error(f"Synthesis failed: {e}")

        if st.session_state["council_synthesis"]:
            st.markdown("---")
            st.markdown(st.session_state["council_synthesis"])

            st.download_button(
                label="⬇️ Download Report (.md)",
                data=st.session_state["council_synthesis"],
                file_name=f"council_report_{output_type}.md",
                mime="text/markdown",
            )
