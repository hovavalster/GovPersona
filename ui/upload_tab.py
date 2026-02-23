"""
Upload tab — drag & drop files to train an agent's knowledge base.
"""
from __future__ import annotations
import os
import tempfile

import streamlit as st

from agents.registry import list_agents
from core.document_loader import ingest_file
from core.vector_store import get_vsm


def render_upload_tab():
    st.header("📚 Train Agent")
    st.caption(
        "Upload PDF, TXT, or JSON documents to an agency's knowledge base. "
        "The app will chunk and index them so the agent can cite them in answers."
    )

    agents = list_agents()
    if not agents:
        st.warning("No agents found. Check config/agents.json.")
        return

    agent_ids = [a[0] for a in agents]
    agent_names = [a[1] for a in agents]

    selected_idx = st.selectbox(
        "Select Agency to train",
        options=range(len(agent_ids)),
        format_func=lambda i: agent_names[i],
        key="upload_agent_idx",
    )
    org_id = agent_ids[selected_idx]
    vsm = get_vsm()

    col1, col2 = st.columns([2, 1])
    with col2:
        st.metric("Chunks currently indexed", vsm.get_doc_count(org_id))

    uploaded_files = col1.file_uploader(
        "Drop files here (PDF, TXT, JSON)",
        type=["pdf", "txt", "json"],
        accept_multiple_files=True,
        key="uploaded_docs",
    )

    if uploaded_files:
        if st.button("⬆️ Ingest selected files", type="primary"):
            total_added = 0
            total_chunks = 0

            progress = st.progress(0, text="Starting ingestion...")
            for idx, uploaded_file in enumerate(uploaded_files):
                progress.progress(
                    idx / len(uploaded_files),
                    text=f"Processing: {uploaded_file.name}",
                )

                # Save to temp file (needed for PyMuPDF)
                suffix = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix
                ) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                try:
                    added, total, warning = ingest_file(
                        file_path=tmp_path,
                        org_id=org_id,
                        vsm=vsm,
                        doc_type="uploaded_document",
                    )
                    total_added += added
                    total_chunks += total

                    status = f"✅ **{uploaded_file.name}** — {added} new chunks (of {total} total)"
                    if warning:
                        status += f"\n\n{warning}"
                    st.success(status)
                except Exception as e:
                    st.error(f"❌ **{uploaded_file.name}** — Error: {e}")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            progress.progress(1.0, text="Done!")
            st.info(
                f"Ingestion complete: **{total_added}** new chunks added from {len(uploaded_files)} file(s). "
                f"Total indexed for this agency: **{vsm.get_doc_count(org_id)}**"
            )
