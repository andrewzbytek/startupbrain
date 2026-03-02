"""
Unit tests for app/state.py — session state management and state machine.
All tests run without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class _AttrDict(dict):
    """A dict that supports attribute-style access, mimicking Streamlit's SessionState."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)


# Mock streamlit before importing app modules
mock_st = MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)
# If streamlit was already mocked by another test file, grab that reference instead
mock_st = sys.modules["streamlit"]
# Ensure session_state is an _AttrDict on whatever mock is active
if not isinstance(getattr(mock_st, 'session_state', None), _AttrDict):
    mock_st.session_state = _AttrDict()

# Now import the module under test — it will bind to our mock_st
import app.state as state_module
from app.state import (
    VALID_MODES,
    init_session_state,
    set_mode,
    get_mode,
    add_message,
    invalidate_sidebar,
    reset_ingestion,
)


@pytest.fixture(autouse=True)
def fresh_session_state():
    """Reset mock session_state to an AttrDict before each test.
    Also re-bind the module's st reference so attribute writes work."""
    new_state = _AttrDict()
    mock_st.session_state = new_state
    # The module captured `st` at import time; ensure it points to our mock
    state_module.st = mock_st
    yield
    mock_st.session_state = _AttrDict()


# ---------------------------------------------------------------------------
# init_session_state
# ---------------------------------------------------------------------------

class TestInitSessionState:
    def test_initializes_all_expected_keys(self):
        init_session_state()
        expected_keys = {
            "mode", "conversation_history", "pending_claims", "contradictions",
            "current_session_id", "current_transcript", "ingestion_status",
            "sidebar_data", "ingestion_participants", "ingestion_topic",
            "ingestion_session_summary", "ingestion_topic_tags",
            "consistency_results", "contradiction_index", "whiteboard_text",
            "evolution_result", "ingestion_session_type", "ingestion_session_date",
            "book_crosscheck_content", "book_crosscheck_filename",
            "show_hypothesis_form",
            "deferred_writer", "_batch_committed", "_has_pending_ingestion",
        }
        assert expected_keys == set(mock_st.session_state.keys())

    def test_default_mode_is_chat(self):
        init_session_state()
        assert mock_st.session_state["mode"] == "chat"

    def test_default_conversation_history_is_empty_list(self):
        init_session_state()
        assert mock_st.session_state["conversation_history"] == []

    def test_does_not_overwrite_existing_values(self):
        mock_st.session_state["mode"] = "ingesting"
        mock_st.session_state["conversation_history"] = [{"role": "user", "content": "hi"}]
        init_session_state()
        assert mock_st.session_state["mode"] == "ingesting"
        assert len(mock_st.session_state["conversation_history"]) == 1

    def test_fills_in_missing_keys_without_touching_existing(self):
        mock_st.session_state["mode"] = "done"
        init_session_state()
        assert mock_st.session_state["mode"] == "done"
        assert "sidebar_data" in mock_st.session_state


# ---------------------------------------------------------------------------
# set_mode
# ---------------------------------------------------------------------------

class TestSetMode:
    @pytest.mark.parametrize("mode", list(VALID_MODES))
    def test_accepts_all_valid_modes(self, mode):
        init_session_state()
        set_mode(mode)
        assert mock_st.session_state.mode == mode

    def test_invalid_mode_raises_value_error(self):
        init_session_state()
        with pytest.raises(ValueError, match="Invalid mode"):
            set_mode("nonexistent_mode")

    def test_empty_string_raises_value_error(self):
        init_session_state()
        with pytest.raises(ValueError, match="Invalid mode"):
            set_mode("")


# ---------------------------------------------------------------------------
# get_mode
# ---------------------------------------------------------------------------

class TestGetMode:
    def test_returns_current_mode(self):
        mock_st.session_state["mode"] = "ingesting"
        assert get_mode() == "ingesting"

    def test_returns_chat_as_default_when_mode_not_set(self):
        # session_state is empty, get_mode should return "chat"
        assert get_mode() == "chat"


# ---------------------------------------------------------------------------
# add_message
# ---------------------------------------------------------------------------

class TestAddMessage:
    def test_appends_message_dict_with_role_and_content(self):
        mock_st.session_state["conversation_history"] = []
        add_message("user", "hello")
        assert mock_st.session_state.conversation_history[-1] == {
            "role": "user",
            "content": "hello",
        }

    def test_creates_conversation_history_if_missing(self):
        # conversation_history not in session_state
        assert "conversation_history" not in mock_st.session_state
        add_message("assistant", "welcome")
        assert mock_st.session_state.conversation_history[-1] == {
            "role": "assistant",
            "content": "welcome",
        }

    def test_preserves_order_of_multiple_messages(self):
        mock_st.session_state["conversation_history"] = []
        add_message("user", "first")
        add_message("assistant", "second")
        add_message("user", "third")
        history = mock_st.session_state.conversation_history
        assert len(history) == 3
        assert history[0]["content"] == "first"
        assert history[1]["content"] == "second"
        assert history[2]["content"] == "third"


# ---------------------------------------------------------------------------
# invalidate_sidebar
# ---------------------------------------------------------------------------

class TestInvalidateSidebar:
    def test_sets_sidebar_data_to_empty_dict(self):
        mock_st.session_state.sidebar_data = {"doc": "some content"}
        invalidate_sidebar()
        assert mock_st.session_state.sidebar_data == {}


# ---------------------------------------------------------------------------
# reset_ingestion
# ---------------------------------------------------------------------------

class TestResetIngestion:
    def test_resets_mode_to_chat(self):
        init_session_state()
        mock_st.session_state.mode = "ingesting"
        reset_ingestion()
        assert mock_st.session_state.mode == "chat"

    def test_clears_pending_claims(self):
        init_session_state()
        mock_st.session_state.pending_claims = [{"claim": "test"}]
        reset_ingestion()
        assert mock_st.session_state.pending_claims == []

    def test_clears_contradictions(self):
        init_session_state()
        mock_st.session_state.contradictions = [{"id": "1"}]
        reset_ingestion()
        assert mock_st.session_state.contradictions == []

    def test_clears_current_session_id(self):
        init_session_state()
        mock_st.session_state.current_session_id = "session_123"
        reset_ingestion()
        assert mock_st.session_state.current_session_id is None

    def test_clears_current_transcript(self):
        init_session_state()
        mock_st.session_state.current_transcript = "some transcript text"
        reset_ingestion()
        assert mock_st.session_state.current_transcript is None

    def test_clears_ingestion_metadata_fields(self):
        init_session_state()
        mock_st.session_state.ingestion_participants = "Alex, Jordan"
        mock_st.session_state.ingestion_topic = "Pricing"
        mock_st.session_state.ingestion_session_summary = "Some summary"
        mock_st.session_state.ingestion_topic_tags = ["pricing"]
        reset_ingestion()
        assert mock_st.session_state.ingestion_participants == ""
        assert mock_st.session_state.ingestion_topic == ""
        assert mock_st.session_state.ingestion_session_summary == ""
        assert mock_st.session_state.ingestion_topic_tags == []

    def test_resets_contradiction_index_to_zero(self):
        init_session_state()
        mock_st.session_state.contradiction_index = 5
        reset_ingestion()
        assert mock_st.session_state.contradiction_index == 0

    def test_clears_whiteboard_text(self):
        init_session_state()
        mock_st.session_state.whiteboard_text = "diagram notes"
        reset_ingestion()
        assert mock_st.session_state.whiteboard_text == ""
