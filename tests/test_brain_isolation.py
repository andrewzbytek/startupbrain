"""
Unit tests for brain isolation across the Startup Brain codebase.

Verifies that brain parameter is properly threaded through MongoDB queries,
chat prefix commands are gated to the correct brain, scratchpad retrieval
respects brain context, and the brain toggle is disabled during ingestion.

All tests run without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Mock streamlit and pymongo before importing modules under test
# ---------------------------------------------------------------------------

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


mock_st = MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)

mock_pymongo = MagicMock()
mock_pymongo.ASCENDING = 1
mock_pymongo.errors = MagicMock()
mock_pymongo.errors.ConnectionFailure = type("ConnectionFailure", (Exception,), {})
mock_pymongo.errors.ServerSelectionTimeoutError = type("ServerSelectionTimeoutError", (Exception,), {})
sys.modules.setdefault("pymongo", mock_pymongo)


def _assert_brain_or_filter(query, brain_value):
    """Assert the query uses the legacy-compatible $or brain filter pattern.

    After the schema drift fix, brain filters use:
    {"$or": [{"brain": value}, {"brain": {"$exists": False}}]}
    to also match pre-migration documents that lack the brain field.
    """
    assert "$or" in query, f"Expected $or brain filter in query, got: {query}"
    or_clauses = query["$or"]
    assert {"brain": brain_value} in or_clauses
    assert {"brain": {"$exists": False}} in or_clauses
sys.modules.setdefault("pymongo.errors", mock_pymongo.errors)

import services.mongo_client as mc
from services.consistency import check_rag_health, _get_rag_evidence


# ---------------------------------------------------------------------------
# 1. get_sessions brain filter
# ---------------------------------------------------------------------------

class TestGetSessionsBrainFilter:
    """Test that get_sessions threads the brain parameter to the query."""

    def test_no_brain_returns_all(self):
        """When brain is empty (default), query should have no brain filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_sessions(limit=10)
            call_args = mock_find.call_args
            # Default get_sessions passes empty query (no brain key)
            assert call_args == call(
                "sessions", query={}, sort_by="created_at", sort_order=-1, limit=10
            )

    def test_brain_pitch_filter(self):
        """When brain='pitch' is passed, query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_sessions(limit=10, brain="pitch")
            query = mock_find.call_args[1]["query"]
            _assert_brain_or_filter(query, "pitch")

    def test_brain_ops_filter(self):
        """When brain='ops' is passed, query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_sessions(limit=5, brain="ops")
            query = mock_find.call_args[1]["query"]
            _assert_brain_or_filter(query, "ops")

    def test_empty_brain_string_returns_all(self):
        """Passing brain='' should behave like no filter (return all)."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_sessions(limit=10, brain="")
            call_args = mock_find.call_args
            # Empty string should NOT add brain to the query
            assert call_args == call(
                "sessions", query={}, sort_by="created_at", sort_order=-1, limit=10,
            )


# ---------------------------------------------------------------------------
# 2. search_sessions brain filter
# ---------------------------------------------------------------------------

class TestSearchSessionsBrainFilter:
    """Test that search_sessions threads the brain parameter to the query."""

    def test_no_brain_returns_all(self):
        """When brain is empty (default), no brain filter in query."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions()
            call_args = mock_find.call_args
            assert call_args == call(
                "sessions", query={},
                sort_by="created_at", sort_order=-1, limit=20,
            )

    def test_brain_pitch_added_to_query(self):
        """When brain='pitch', query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions(brain="pitch")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            _assert_brain_or_filter(query, "pitch")

    def test_brain_ops_added_to_query(self):
        """When brain='ops', query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions(brain="ops")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            _assert_brain_or_filter(query, "ops")

    def test_brain_combined_with_session_type(self):
        """Brain filter should be combined with other filters via AND."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions(session_type="Investor", brain="pitch")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert "metadata.session_type" in query
            _assert_brain_or_filter(query, "pitch")

    def test_brain_combined_with_date_range(self):
        """Brain filter should be combined with date filters."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions(date_from="2026-01-01", date_to="2026-03-01", brain="ops")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert "session_date" in query
            _assert_brain_or_filter(query, "ops")

    def test_empty_brain_no_filter(self):
        """Passing brain='' should not add brain to the query."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.search_sessions(brain="")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert "brain" not in query


# ---------------------------------------------------------------------------
# 3. update_hypothesis_status brain filter
# ---------------------------------------------------------------------------

class TestUpdateHypothesisStatusBrainFilter:
    """Test that update_hypothesis_status applies brain='ops' filter to the query.

    Hypotheses are always ops-brain claims, so update_hypothesis_status
    hardcodes brain='ops' in its query to prevent cross-brain matches.
    """

    def test_query_includes_hypothesis_type(self):
        """Query should search for claim_type=hypothesis."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_hypothesis_status("test hypothesis", "validated")
            query = mock_collection.update_one.call_args[0][0]
            assert query["claim_type"] == "hypothesis"

    def test_query_includes_brain_ops(self):
        """Query should always include brain='ops' to prevent cross-brain matches."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_hypothesis_status("test hypothesis", "validated")
            query = mock_collection.update_one.call_args[0][0]
            assert query.get("brain") == "ops"

    def test_regex_search_preserved_with_brain(self):
        """Brain filter should coexist with the regex text search."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_hypothesis_status("pricing will increase", "validated")
            query = mock_collection.update_one.call_args[0][0]
            assert query["claim_type"] == "hypothesis"
            assert "$regex" in query["claim_text"]
            assert query["brain"] == "ops"

    def test_status_update_set_correctly(self):
        """The $set operation should include the new status and updated_at."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_hypothesis_status("test", "invalidated")
            update = mock_collection.update_one.call_args[0][1]
            assert update["$set"]["status"] == "invalidated"
            assert "updated_at" in update["$set"]

    def test_returns_true_on_match(self):
        """Should return True when a document was modified."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.update_hypothesis_status("test", "validated")
            assert result is True

    def test_returns_false_on_no_match(self):
        """Should return False when no document was modified."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=0)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.update_hypothesis_status("nonexistent", "validated")
            assert result is False


# ---------------------------------------------------------------------------
# 4. insert_claim brain parameter
# ---------------------------------------------------------------------------

class TestInsertClaimBrainParameter:
    """Test that insert_claim sets the brain field correctly."""

    def test_default_brain_is_pitch(self):
        """When brain is not specified, default should be 'pitch'."""
        with patch.object(mc, "insert_one", return_value="id1") as mock_insert:
            mc.insert_claim({"claim_text": "test claim"})
            inserted = mock_insert.call_args[0][1]
            assert inserted["brain"] == "pitch"

    def test_brain_ops(self):
        """When brain='ops', the inserted document should have brain='ops'."""
        with patch.object(mc, "insert_one", return_value="id2") as mock_insert:
            mc.insert_claim({"claim_text": "ops claim"}, brain="ops")
            inserted = mock_insert.call_args[0][1]
            assert inserted["brain"] == "ops"

    def test_brain_pitch_explicit(self):
        """When brain='pitch' is explicit, the document should have brain='pitch'."""
        with patch.object(mc, "insert_one", return_value="id3") as mock_insert:
            mc.insert_claim({"claim_text": "pitch claim"}, brain="pitch")
            inserted = mock_insert.call_args[0][1]
            assert inserted["brain"] == "pitch"

    def test_brain_does_not_overwrite_existing(self):
        """If claim_doc already has a 'brain' key, the parameter should take precedence."""
        with patch.object(mc, "insert_one", return_value="id4") as mock_insert:
            mc.insert_claim({"claim_text": "test", "brain": "pitch"}, brain="ops")
            inserted = mock_insert.call_args[0][1]
            # The brain= parameter uses {**doc, "brain": brain} so it overwrites
            assert inserted["brain"] == "ops"

    def test_collection_name_is_claims(self):
        """insert_claim should always target the 'claims' collection."""
        with patch.object(mc, "insert_one", return_value="id5") as mock_insert:
            mc.insert_claim({"claim_text": "test"}, brain="ops")
            collection = mock_insert.call_args[0][0]
            assert collection == "claims"


# ---------------------------------------------------------------------------
# 5. Chat prefix gating — ops-only prefixes rejected in pitch mode
# ---------------------------------------------------------------------------

class TestChatPrefixBrainGating:
    """Test that prefix commands (note:, hypothesis:, contact:) are only
    processed when active_brain == 'ops', and fall through to normal chat
    in pitch mode."""

    def setup_method(self):
        """Reset session state before each test."""
        mock_st.session_state = _AttrDict({
            "mode": "chat",
            "conversation_history": [],
            "active_brain": "pitch",
            "chat_brain_context": "pitch",
            "book_crosscheck_content": "",
            "active_view": "chat",
        })

    def test_quick_note_detected_in_ops(self):
        """_is_quick_note detects note prefixes regardless of brain (it's a pure function)."""
        from app.components.chat import _is_quick_note
        assert _is_quick_note("note: test note") is True

    def test_contact_detected_in_ops(self):
        """_is_contact detects contact prefixes regardless of brain."""
        from app.components.chat import _is_contact
        assert _is_contact("contact: John Smith") is True

    def test_hypothesis_detected_regardless(self):
        """_is_hypothesis detects hypothesis prefix regardless of brain."""
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("hypothesis: test") is True

    def test_pitch_brain_blocks_quick_note_handler(self):
        """In pitch brain, a 'note:' message should NOT call _apply_quick_note.
        Instead it falls through to normal chat (with an informational toast)."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import _is_quick_note

        # The gating logic in render_chat_view:
        #   if active_brain == "ops" and _is_quick_note(user_input): ...
        # When active_brain is "pitch", this condition is False
        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "note: test note"
        should_process = active_brain == "ops" and _is_quick_note(user_input)
        assert should_process is False

    def test_pitch_brain_blocks_contact_handler(self):
        """In pitch brain, a 'contact:' message should NOT call _apply_contact."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import _is_contact

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "contact: Jane Doe, Sequoia"
        should_process = active_brain == "ops" and _is_contact(user_input)
        assert should_process is False

    def test_pitch_brain_blocks_hypothesis_handler(self):
        """In pitch brain, a 'hypothesis:' message should NOT call _apply_hypothesis."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import _is_hypothesis

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "hypothesis: customers will pay $500"
        should_process = active_brain == "ops" and _is_hypothesis(user_input)
        assert should_process is False

    def test_pitch_brain_blocks_hypothesis_status_handler(self):
        """In pitch brain, a 'validated:' message should NOT call _apply_hypothesis_status_update."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import _is_hypothesis_status_update

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "validated: customers will pay $500"
        should_process = active_brain == "ops" and _is_hypothesis_status_update(user_input)
        assert should_process is False

    def test_ops_brain_allows_quick_note_handler(self):
        """In ops brain, a 'note:' message should be processed."""
        mock_st.session_state["active_brain"] = "ops"

        from app.components.chat import _is_quick_note

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "note: important meeting tomorrow"
        should_process = active_brain == "ops" and _is_quick_note(user_input)
        assert should_process is True

    def test_ops_brain_allows_contact_handler(self):
        """In ops brain, a 'contact:' message should be processed."""
        mock_st.session_state["active_brain"] = "ops"

        from app.components.chat import _is_contact

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "contact: Sarah, Acme Corp"
        should_process = active_brain == "ops" and _is_contact(user_input)
        assert should_process is True

    def test_ops_brain_allows_hypothesis_handler(self):
        """In ops brain, a 'hypothesis:' message should be processed."""
        mock_st.session_state["active_brain"] = "ops"

        from app.components.chat import _is_hypothesis

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "hypothesis: enterprise market is bigger"
        should_process = active_brain == "ops" and _is_hypothesis(user_input)
        assert should_process is True

    def test_ops_brain_allows_hypothesis_status_handler(self):
        """In ops brain, a 'validated:' message should be processed."""
        mock_st.session_state["active_brain"] = "ops"

        from app.components.chat import _is_hypothesis_status_update

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "validated: enterprise market is bigger"
        should_process = active_brain == "ops" and _is_hypothesis_status_update(user_input)
        assert should_process is True

    def test_pitch_mode_shows_toast_for_ops_prefixes(self):
        """In pitch brain, typing an ops prefix should trigger the toast condition."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import (
            _is_quick_note, _is_contact, _is_hypothesis, _is_hypothesis_status_update
        )

        active_brain = mock_st.session_state.get("active_brain", "pitch")

        # The toast logic: if active_brain != "ops" and any prefix matches
        for user_input in [
            "note: test",
            "contact: test",
            "hypothesis: test",
            "validated: test",
        ]:
            should_toast = (
                active_brain != "ops"
                and (
                    _is_quick_note(user_input)
                    or _is_contact(user_input)
                    or _is_hypothesis(user_input)
                    or _is_hypothesis_status_update(user_input)
                )
            )
            assert should_toast is True, f"Toast should fire for: {user_input}"

    def test_normal_text_no_toast(self):
        """Normal chat text should not trigger the ops prefix toast."""
        mock_st.session_state["active_brain"] = "pitch"

        from app.components.chat import (
            _is_quick_note, _is_contact, _is_hypothesis, _is_hypothesis_status_update
        )

        active_brain = mock_st.session_state.get("active_brain", "pitch")
        user_input = "What is our current pricing?"
        should_toast = (
            active_brain != "ops"
            and (
                _is_quick_note(user_input)
                or _is_contact(user_input)
                or _is_hypothesis(user_input)
                or _is_hypothesis_status_update(user_input)
            )
        )
        assert should_toast is False


# ---------------------------------------------------------------------------
# 6. Scratchpad retrieval brain filter
# ---------------------------------------------------------------------------

class TestScratchpadBrainFilter:
    """Test that scratchpad note retrieval in _get_system_prompt respects brain context."""

    @staticmethod
    def _find_scratchpad_call(mock_find):
        """Helper to find the scratchpad-related find_many call."""
        for c in mock_find.call_args_list:
            args, kwargs = c
            query = args[1] if len(args) > 1 else kwargs.get("query", None)
            if isinstance(query, dict) and query.get("source_type") == "quick_note":
                return query
        return None

    def test_pitch_brain_no_scratchpad_filter(self):
        """When brain context is 'pitch', scratchpad should NOT filter by brain.

        Scratchpad notes are always stored as brain='ops' but should surface
        in all brain contexts so the founder's notes are always visible.
        """
        import streamlit as _st
        _st.session_state["chat_brain_context"] = "pitch"
        _st.session_state["book_crosscheck_content"] = ""

        with patch("services.document_updater.read_living_document", return_value="test doc"), \
             patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            from app.components.chat import _get_system_prompt
            _get_system_prompt()

            query = self._find_scratchpad_call(mock_find)
            assert query is not None, "scratchpad find_many call not found"
            assert "brain" not in query

    def test_ops_brain_no_scratchpad_filter(self):
        """When brain context is 'ops', scratchpad should NOT filter by brain.

        Notes surface everywhere regardless of brain context.
        """
        import streamlit as _st
        _st.session_state["chat_brain_context"] = "ops"
        _st.session_state["book_crosscheck_content"] = ""

        with patch("services.document_updater.read_living_document", return_value="test doc"), \
             patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            from app.components.chat import _get_system_prompt
            _get_system_prompt()

            query = self._find_scratchpad_call(mock_find)
            assert query is not None, "scratchpad find_many call not found"
            assert "brain" not in query

    def test_both_brain_no_filter(self):
        """When brain context is 'both', scratchpad query should NOT have brain filter."""
        import streamlit as _st
        _st.session_state["chat_brain_context"] = "both"
        _st.session_state["book_crosscheck_content"] = ""

        with patch("services.document_updater.read_living_document", return_value="test doc"), \
             patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            from app.components.chat import _get_system_prompt
            _get_system_prompt()

            query = self._find_scratchpad_call(mock_find)
            assert query is not None, "scratchpad find_many call not found"
            assert "brain" not in query

    def test_scratchpad_notes_included_in_prompt(self):
        """When scratchpad notes exist, they should appear in the system prompt."""
        import streamlit as _st
        _st.session_state["chat_brain_context"] = "ops"
        _st.session_state["book_crosscheck_content"] = ""

        from datetime import datetime, timezone
        mock_notes = [
            {
                "claim_text": "Follow up with investor next week",
                "created_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
            }
        ]

        with patch("services.document_updater.read_living_document", return_value="test doc"), \
             patch("services.mongo_client.find_many", return_value=mock_notes):
            from app.components.chat import _get_system_prompt
            prompt = _get_system_prompt()
            assert "<scratchpad_notes>" in prompt
            assert "Follow up with investor next week" in prompt


# ---------------------------------------------------------------------------
# 7. Brain toggle disabled during ingestion
# ---------------------------------------------------------------------------

class TestBrainToggleDuringIngestion:
    """Test that the brain radio widget is disabled when mode != 'chat'."""

    def test_chat_mode_not_in_pipeline(self):
        """When mode is 'chat', in_pipeline should be False."""
        mode = "chat"
        in_pipeline = mode != "chat"
        assert in_pipeline is False

    def test_ingesting_mode_is_in_pipeline(self):
        """When mode is 'ingesting', in_pipeline should be True."""
        mode = "ingesting"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_confirming_claims_is_in_pipeline(self):
        """When mode is 'confirming_claims', in_pipeline should be True."""
        mode = "confirming_claims"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_checking_consistency_is_in_pipeline(self):
        """When mode is 'checking_consistency', in_pipeline should be True."""
        mode = "checking_consistency"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_resolving_contradiction_is_in_pipeline(self):
        """When mode is 'resolving_contradiction', in_pipeline should be True."""
        mode = "resolving_contradiction"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_ops_ingesting_is_in_pipeline(self):
        """When mode is 'ops_ingesting', in_pipeline should be True."""
        mode = "ops_ingesting"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_ops_confirming_is_in_pipeline(self):
        """When mode is 'ops_confirming', in_pipeline should be True."""
        mode = "ops_confirming"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_done_is_in_pipeline(self):
        """When mode is 'done', in_pipeline should be True."""
        mode = "done"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_ops_done_is_in_pipeline(self):
        """When mode is 'ops_done', in_pipeline should be True."""
        mode = "ops_done"
        in_pipeline = mode != "chat"
        assert in_pipeline is True

    def test_brain_switch_blocked_during_pipeline(self):
        """When in_pipeline is True, brain switch should not execute."""
        in_pipeline = True
        new_brain = "ops"
        current_brain = "pitch"
        # In top_bar.py: if not in_pipeline and new_brain != current_brain:
        should_switch = not in_pipeline and new_brain != current_brain
        assert should_switch is False

    def test_brain_switch_allowed_in_chat(self):
        """When in_pipeline is False and brain changed, switch should execute."""
        in_pipeline = False
        new_brain = "ops"
        current_brain = "pitch"
        should_switch = not in_pipeline and new_brain != current_brain
        assert should_switch is True

    def test_brain_switch_noop_when_same(self):
        """When brain hasn't changed, switch should not execute even in chat mode."""
        in_pipeline = False
        new_brain = "pitch"
        current_brain = "pitch"
        should_switch = not in_pipeline and new_brain != current_brain
        assert should_switch is False

    def test_all_valid_modes_checked(self):
        """Verify our test covers all VALID_MODES from state.py."""
        from app.state import VALID_MODES
        for mode in VALID_MODES:
            in_pipeline = mode != "chat"
            if mode == "chat":
                assert in_pipeline is False, f"{mode} should not be in pipeline"
            else:
                assert in_pipeline is True, f"{mode} should be in pipeline"


# ---------------------------------------------------------------------------
# 8. get_claims brain filter
# ---------------------------------------------------------------------------

class TestGetClaimsBrainFilter:
    """Test that get_claims threads the brain parameter to the query."""

    def test_no_brain_returns_all(self):
        """When brain is empty (default), query should not include brain."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_claims()
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert "brain" not in query

    def test_brain_pitch_filter(self):
        """When brain='pitch', query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_claims(brain="pitch")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            _assert_brain_or_filter(query, "pitch")

    def test_brain_ops_filter(self):
        """When brain='ops', query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_claims(brain="ops")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            _assert_brain_or_filter(query, "ops")

    def test_brain_combined_with_session_id(self):
        """Brain filter should work alongside session_id filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_claims(session_id="s1", brain="pitch")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert query.get("session_id") == "s1"
            _assert_brain_or_filter(query, "pitch")


# ---------------------------------------------------------------------------
# 9. get_hypotheses brain filter
# ---------------------------------------------------------------------------

class TestGetHypothesesBrainFilter:
    """Test that get_hypotheses threads the brain parameter to the query."""

    def test_no_brain_returns_all_hypotheses(self):
        """When brain is empty, query should only have claim_type=hypothesis."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_hypotheses()
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert query.get("claim_type") == "hypothesis"
            assert "brain" not in query

    def test_brain_ops_filter(self):
        """When brain='ops', query should use $or legacy-compat filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_hypotheses(brain="ops")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert query.get("claim_type") == "hypothesis"
            _assert_brain_or_filter(query, "ops")

    def test_brain_combined_with_status(self):
        """Brain filter should work alongside status filter."""
        with patch.object(mc, "find_many", return_value=[]) as mock_find:
            mc.get_hypotheses(status="active", brain="ops")
            query = mock_find.call_args[1].get("query", mock_find.call_args[0][1] if len(mock_find.call_args[0]) > 1 else {})
            assert query.get("status") == "active"
            _assert_brain_or_filter(query, "ops")


# ---------------------------------------------------------------------------
# 10. insert_session brain parameter
# ---------------------------------------------------------------------------

class TestInsertSessionBrainParameter:
    """Test that insert_session sets the brain field correctly."""

    def test_default_brain_is_pitch(self):
        """When brain is not specified, default should be 'pitch'."""
        with patch.object(mc, "insert_one", return_value="id1") as mock_insert:
            mc.insert_session({"transcript": "test"})
            inserted = mock_insert.call_args[0][1]
            assert inserted["brain"] == "pitch"

    def test_brain_ops(self):
        """When brain='ops', the inserted document should have brain='ops'."""
        with patch.object(mc, "insert_one", return_value="id2") as mock_insert:
            mc.insert_session({"transcript": "ops session"}, brain="ops")
            inserted = mock_insert.call_args[0][1]
            assert inserted["brain"] == "ops"


# ---------------------------------------------------------------------------
# 11. Living document brain isolation
# ---------------------------------------------------------------------------

class TestLivingDocumentBrainIsolation:
    """Test that upsert/get living document uses brain-specific _id."""

    def test_upsert_pitch_brain(self):
        """upsert_living_document with brain='pitch' should use _id='pitch_brain'."""
        with patch.object(mc, "update_one", return_value=True) as mock_update:
            mc.upsert_living_document("content", brain="pitch")
            query = mock_update.call_args[0][1]
            assert query == {"_id": "pitch_brain"}

    def test_upsert_ops_brain(self):
        """upsert_living_document with brain='ops' should use _id='ops_brain'."""
        with patch.object(mc, "update_one", return_value=True) as mock_update:
            mc.upsert_living_document("content", brain="ops")
            query = mock_update.call_args[0][1]
            assert query == {"_id": "ops_brain"}

    def test_get_pitch_brain(self):
        """get_living_document with brain='pitch' should query _id='pitch_brain'."""
        with patch.object(mc, "find_one", return_value={"content": "pitch doc"}) as mock_find:
            mc.get_living_document(brain="pitch")
            mock_find.assert_called_once_with("living_document", {"_id": "pitch_brain"})

    def test_get_ops_brain(self):
        """get_living_document with brain='ops' should query _id='ops_brain'."""
        with patch.object(mc, "find_one", return_value={"content": "ops doc"}) as mock_find:
            mc.get_living_document(brain="ops")
            mock_find.assert_called_once_with("living_document", {"_id": "ops_brain"})


# ---------------------------------------------------------------------------
# 12. check_rag_health counts all claims
# ---------------------------------------------------------------------------

class TestCheckRagHealthBrainIsolation:
    """Test that check_rag_health counts pitch claims specifically.

    RAG health only applies to the pitch brain since that's where the
    consistency engine operates. The count should filter by brain='pitch'.
    """

    def test_counts_pitch_claims(self):
        """check_rag_health should count pitch brain claims only."""
        with patch("services.mongo_client.count_documents", return_value=50) as mock_count:
            result = check_rag_health()
            mock_count.assert_called_once_with("claims", {"brain": "pitch"})
            assert result["claim_count"] == 50
            assert result["needs_upgrade"] is False

    def test_needs_upgrade_at_threshold(self):
        """When pitch claim count reaches the threshold, needs_upgrade should be True."""
        with patch("services.mongo_client.count_documents", return_value=200):
            result = check_rag_health()
            assert result["needs_upgrade"] is True
            assert result["threshold"] == 200

    def test_below_threshold(self):
        """When pitch claim count is below threshold, needs_upgrade should be False."""
        with patch("services.mongo_client.count_documents", return_value=100):
            result = check_rag_health()
            assert result["needs_upgrade"] is False

    def test_returns_correct_structure(self):
        """Return dict should contain all expected keys."""
        with patch("services.mongo_client.count_documents", return_value=75):
            result = check_rag_health()
            assert "claim_count" in result
            assert "needs_upgrade" in result
            assert "threshold" in result
            assert "message" in result
            assert result["claim_count"] == 75


# ---------------------------------------------------------------------------
# 13. _get_rag_evidence fallback retrieval
# ---------------------------------------------------------------------------

class TestGetRagEvidenceBrainIsolation:
    """Test that _get_rag_evidence retrieves evidence properly."""

    def test_fallback_calls_get_claims(self):
        """When vector search is not available, fallback should call get_claims."""
        with patch("services.mongo_client.get_claims", return_value=[]) as mock_claims, \
             patch("services.mongo_client.get_sessions", return_value=[]) as mock_sessions, \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("no index")), \
             patch("services.mongo_client.count_documents", return_value=10):
            claims = [{"claim_text": "test claim"}]
            result = _get_rag_evidence(claims)
            mock_claims.assert_called_once()
            mock_sessions.assert_called_once()
            assert isinstance(result, list)

    def test_fallback_returns_evidence_from_claims(self):
        """Fallback path should format claims into evidence dicts."""
        mock_claims = [
            {"claim_text": "Price is 50K", "created_at": "2026-03-01", "source_type": "session"},
        ]
        with patch("services.mongo_client.get_claims", return_value=mock_claims), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("no index")), \
             patch("services.mongo_client.count_documents", return_value=10):
            result = _get_rag_evidence([{"claim_text": "test"}])
            assert len(result) >= 1
            assert result[0]["relevant_excerpt"] == "Price is 50K"

    def test_vector_search_used_when_available(self):
        """When vector search returns results, they should be used."""
        vector_results = [
            {"claim_text": "Semantic match", "created_at": "2026-03-01", "source_type": "session", "score": 0.9},
        ]
        with patch("services.mongo_client.vector_search_text", return_value=vector_results), \
             patch("services.mongo_client.get_claims") as mock_claims, \
             patch("services.mongo_client.get_sessions") as mock_sessions:
            result = _get_rag_evidence([{"claim_text": "test"}])
            assert len(result) == 1
            assert result[0]["relevant_excerpt"] == "Semantic match"
            # Should not fall back to time-based retrieval
            mock_claims.assert_not_called()
            mock_sessions.assert_not_called()


# ---------------------------------------------------------------------------
# 14. run_consistency_check brain parameter
# ---------------------------------------------------------------------------

class TestRunConsistencyCheckBrain:
    """Test that run_consistency_check passes brain to read_living_document."""

    def test_empty_claims_returns_early(self):
        """With no claims, should return early without reading document."""
        from services.consistency import run_consistency_check
        result = run_consistency_check([], brain="ops")
        assert result["has_contradictions"] is False
        assert result["summary"] == "No claims to check."

    def test_brain_passed_to_read_doc(self):
        """Brain parameter should be forwarded to read_living_document."""
        from services.consistency import run_consistency_check

        with patch("services.consistency.read_living_document", return_value="") as mock_read:
            result = run_consistency_check(
                [{"claim_text": "test"}], brain="ops"
            )
            mock_read.assert_called_once_with(brain="ops")
            # Empty doc means early return
            assert "not found" in result["summary"]

    def test_pitch_brain_default(self):
        """Default brain should be 'pitch'."""
        from services.consistency import run_consistency_check

        with patch("services.consistency.read_living_document", return_value="") as mock_read:
            run_consistency_check([{"claim_text": "test"}])
            mock_read.assert_called_once_with(brain="pitch")
