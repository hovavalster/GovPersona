"""
GovPersona — Government Agency AI Personas
Streamlit app on port 8502.
"""
from dotenv import load_dotenv

load_dotenv()  # MUST be first — loads ANTHROPIC_API_KEY before any SDK imports

import streamlit as st

st.set_page_config(
    page_title="GovPersona",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Pre-warm embeddings on first run (downloads ~120 MB once, then cached)
if "embeddings_loaded" not in st.session_state:
    with st.spinner("Loading Hebrew language model (first run only, ~120 MB)..."):
        from core.embeddings import get_embeddings
        get_embeddings()
    st.session_state["embeddings_loaded"] = True

from ui.chat_tab import render_chat_tab
from ui.council_tab import render_council_tab
from ui.upload_tab import render_upload_tab
from ui.agents_tab import render_agents_tab

st.title("🏛️ GovPersona")
st.caption("Ask government agencies questions — grounded in their own documents.")

tab1, tab2, tab3, tab4 = st.tabs(["💬 Chat", "🤝 Council", "📚 Train Agent", "⚙️ Manage"])

with tab1:
    render_chat_tab()

with tab2:
    render_council_tab()

with tab3:
    render_upload_tab()

with tab4:
    render_agents_tab()
