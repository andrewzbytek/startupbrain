"""
Session state management and state machine for Startup Brain.
All Streamlit session state initialization and transitions.
"""

import streamlit as st

# Valid modes for the state machine
VALID_MODES = {
    "chat",
    "ingesting",
    "confirming_claims",
    "checking_consistency",
    "resolving_contradiction",
    "done",
}


def init_session_state():
    """Initialize ALL session_state keys with defaults. Safe to call on every rerun."""
    defaults = {
        "mode": "chat",
        "conversation_history": [],
        "pending_claims": [],
        "contradictions": [],
        "current_session_id": None,
        "current_transcript": None,
        "ingestion_status": {},
        "sidebar_data": {},
        # Ingestion metadata
        "ingestion_participants": "",
        "ingestion_topic": "",
        "ingestion_session_summary": "",
        "ingestion_topic_tags": [],
        # Consistency check results
        "consistency_results": None,
        # Current contradiction index (for resolving one at a time)
        "contradiction_index": 0,
        # Whiteboard context for current ingestion
        "whiteboard_text": "",
        # Evolution narrative result
        "evolution_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_mode(mode: str):
    """Transition to a new mode with validation."""
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")
    st.session_state.mode = mode


def get_mode() -> str:
    """Return current mode."""
    return st.session_state.get("mode", "chat")


def add_message(role: str, content: str):
    """Append a message to conversation history."""
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []
    st.session_state.conversation_history.append({"role": role, "content": content})


def invalidate_sidebar():
    """Clear sidebar cache so it refreshes on next rerun."""
    st.session_state.sidebar_data = {}


def reset_ingestion():
    """Clear all ingestion-related state and return to chat mode."""
    st.session_state.mode = "chat"
    st.session_state.pending_claims = []
    st.session_state.contradictions = []
    st.session_state.current_session_id = None
    st.session_state.current_transcript = None
    st.session_state.ingestion_status = {}
    st.session_state.ingestion_participants = ""
    st.session_state.ingestion_topic = ""
    st.session_state.ingestion_session_summary = ""
    st.session_state.ingestion_topic_tags = []
    st.session_state.consistency_results = None
    st.session_state.contradiction_index = 0
    st.session_state.whiteboard_text = ""
