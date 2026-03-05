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
    "ops_ingesting",
    "ops_confirming",
    "ops_done",
}

SESSION_TYPES = [
    "Co-founder discussion",
    "Investor meeting",
    "Investor email/feedback",
    "Customer interview",
    "Advisor session",
    "Internal notes",
    "Other",
]


def init_session_state():
    """Initialize ALL session_state keys with defaults. Safe to call on every rerun."""
    defaults = {
        "mode": "chat",
        "active_view": "chat",
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
        "ingestion_session_type": "",
        "ingestion_session_date": None,
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
        # Book cross-check (temporary .md upload)
        "book_crosscheck_content": "",
        "book_crosscheck_filename": "",
        "show_hypothesis_form": False,
        # Pipeline result for done screen
        "pipeline_result": {},
        # Deferred writes / crash recovery
        "deferred_writer": None,
        "_batch_committed": False,
        "_consistency_checked": False,
        "_has_pending_ingestion": False,
        "_active_quick_cmd": None,
        "active_brain": "pitch",
        "chat_brain_context": "pitch",
        "_quick_cmd_pending": None,
        "_lock_session_id": None,
        "_lock_acquired": False,
        "_ops_confirmed_claims": [],
        "_ops_committed": False,
        "_ops_result": {},
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
    # Release ingestion lock if held
    if st.session_state.get("_lock_acquired"):
        try:
            from services.ingestion_lock import release_lock
            release_lock(session_id=st.session_state.get("_lock_session_id"))
        except Exception:
            pass
        st.session_state._lock_acquired = False
        st.session_state._lock_session_id = None

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
    st.session_state.ingestion_session_type = ""
    st.session_state.ingestion_session_date = None
    st.session_state.active_view = "chat"
    st.session_state.pipeline_result = {}
    st.session_state.deferred_writer = None
    st.session_state._batch_committed = False
    st.session_state._consistency_checked = False
    st.session_state._has_pending_ingestion = False
    st.session_state._ops_confirmed_claims = []
    st.session_state._ops_committed = False
    st.session_state._ops_result = {}
