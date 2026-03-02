"""
Unit tests for Phase 2 features:
  Feature 1: Book Framework .md Upload Cross-Check
  Feature 2: MongoDB Atlas Vector Search with Voyage AI
  Feature 3: Direct Corrections with Consistency Check
  Feature 4: Dismissed Contradictions + Decision Log Entries

All tests run without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

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
_own_mock_st = MagicMock()
_own_mock_st.session_state = _AttrDict()
_own_mock_st.cache_resource = lambda f: f
sys.modules.setdefault("streamlit", _own_mock_st)

# Mock pymongo
mock_pymongo = MagicMock()
mock_pymongo.ASCENDING = 1
mock_pymongo.errors = MagicMock()
mock_pymongo.errors.ConnectionFailure = type("ConnectionFailure", (Exception,), {})
mock_pymongo.errors.ServerSelectionTimeoutError = type("ServerSelectionTimeoutError", (Exception,), {})
sys.modules.setdefault("pymongo", mock_pymongo)
sys.modules.setdefault("pymongo.errors", mock_pymongo.errors)

# Get the ACTUAL streamlit mock that all modules use (first-registered wins with setdefault)
import streamlit as st_mock
mock_st = st_mock


# ===========================================================================
# Feature 1: Book Framework .md Upload Cross-Check
# ===========================================================================


class TestBookUploadSystemPrompt:
    """Feature 1: Verify book content is injected into system prompt."""

    def setup_method(self):
        """Reset session state before each test."""
        mock_st.session_state.pop("book_crosscheck_content", None)
        mock_st.session_state.pop("book_crosscheck_filename", None)

    def test_system_prompt_includes_book_framework_when_loaded(self):
        """_get_system_prompt() should include <book_framework> tag when content is in session state."""
        mock_st.session_state["book_crosscheck_content"] = "# The Mom Test\n\nKey principle: Talk about their life, not your idea."
        mock_st.session_state["book_crosscheck_filename"] = "mom_test.md"

        with patch("services.document_updater.read_living_document", return_value="# Living Doc"):
            from app.components.chat import _get_system_prompt
            prompt = _get_system_prompt()

        assert "<book_framework>" in prompt
        assert "The Mom Test" in prompt
        assert "Talk about their life" in prompt

    def test_system_prompt_excludes_book_framework_when_empty(self):
        """_get_system_prompt() should NOT include <book_framework> when no content loaded."""
        mock_st.session_state["book_crosscheck_content"] = ""
        mock_st.session_state["book_crosscheck_filename"] = ""

        with patch("services.document_updater.read_living_document", return_value="# Living Doc"):
            from app.components.chat import _get_system_prompt
            prompt = _get_system_prompt()

        assert "<book_framework>" not in prompt

    def test_system_prompt_excludes_book_framework_when_not_set(self):
        """_get_system_prompt() should handle missing key gracefully."""
        with patch("services.document_updater.read_living_document", return_value="# Living Doc"):
            from app.components.chat import _get_system_prompt
            prompt = _get_system_prompt()

        assert "<book_framework>" not in prompt


class TestBookUploadSessionState:
    """Feature 1: Verify session state defaults."""

    def test_state_defaults_include_book_fields(self):
        """init_session_state should set book_crosscheck_content and book_crosscheck_filename."""
        # Ensure the keys don't exist yet so init_session_state fills them
        mock_st.session_state.pop("book_crosscheck_content", None)
        mock_st.session_state.pop("book_crosscheck_filename", None)

        from app.state import init_session_state
        init_session_state()

        assert "book_crosscheck_content" in mock_st.session_state
        assert "book_crosscheck_filename" in mock_st.session_state
        assert mock_st.session_state["book_crosscheck_content"] == ""
        assert mock_st.session_state["book_crosscheck_filename"] == ""


# ===========================================================================
# Feature 2: MongoDB Atlas Vector Search with Voyage AI
# ===========================================================================


class TestVectorSearchText:
    """Feature 2: Tests for vector_search_text() in mongo_client."""

    def test_builds_pipeline_with_query_string(self):
        """Should use queryString instead of queryVector."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = [{"claim_text": "test", "score": 0.95}]

        with patch.object(mc, "get_db", return_value=mock_db):
            results = mc.vector_search_text("claims", "target market pricing", "claims_vector_index")
            pipeline = mock_collection.aggregate.call_args[0][0]

            assert pipeline[0]["$vectorSearch"]["queryString"] == "target market pricing"
            assert pipeline[0]["$vectorSearch"]["index"] == "claims_vector_index"
            assert pipeline[0]["$vectorSearch"]["path"] == "claim_text_embedding"
            assert "queryVector" not in pipeline[0]["$vectorSearch"]
            assert "$addFields" in pipeline[1]
            assert len(results) == 1

    def test_includes_filter_when_provided(self):
        """Should add filter to pipeline when filter_query is given."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.vector_search_text(
                "claims", "query", "idx",
                filter_query={"source_type": "investor"},
            )
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0]["$vectorSearch"]["filter"] == {"source_type": "investor"}

    def test_no_filter_when_not_provided(self):
        """Should not include filter when filter_query is None."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.vector_search_text("claims", "query", "idx")
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert "filter" not in pipeline[0]["$vectorSearch"]

    def test_returns_empty_when_db_none(self):
        """Should return empty list when database is unavailable."""
        import services.mongo_client as mc

        with patch.object(mc, "get_db", return_value=None):
            result = mc.vector_search_text("claims", "query", "idx")
            assert result == []

    def test_handles_exception_gracefully(self):
        """Should return empty list on exception (no warning)."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.side_effect = Exception("index not found")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.vector_search_text("claims", "query", "idx")
            assert result == []

    def test_num_candidates_is_limit_times_10(self):
        """numCandidates should be limit * 10."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.vector_search_text("claims", "query", "idx", limit=7)
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0]["$vectorSearch"]["numCandidates"] == 70
            assert pipeline[0]["$vectorSearch"]["limit"] == 7


class TestGetRagEvidenceVectorSearch:
    """Feature 2: Tests for upgraded _get_rag_evidence() with vector search."""

    def test_uses_vector_search_when_available(self):
        """Should use vector search results when they return data."""
        from services.consistency import _get_rag_evidence

        mock_vector_results = [
            {"claim_text": "Target market is small nuclear", "created_at": "2026-02-01", "source_type": "session"},
            {"claim_text": "Pricing at 50K per facility", "created_at": "2026-02-05", "source_type": "session"},
        ]

        claims = [{"claim_text": "We should target enterprise accounts"}]

        with patch("services.mongo_client.vector_search_text", return_value=mock_vector_results), \
             patch("services.mongo_client.get_claims", return_value=[]) as mock_get_claims, \
             patch("services.mongo_client.get_sessions", return_value=[]) as mock_get_sessions:
            evidence = _get_rag_evidence(claims)

        assert len(evidence) == 2
        assert evidence[0]["relevant_excerpt"] == "Target market is small nuclear"
        # Should NOT fall back to time-based when vector search succeeds
        mock_get_claims.assert_not_called()
        mock_get_sessions.assert_not_called()

    def test_falls_back_to_time_based_when_vector_search_empty(self):
        """Should fall back to time-based retrieval when vector search returns empty."""
        from services.consistency import _get_rag_evidence

        claims = [{"claim_text": "test claim"}]

        with patch("services.mongo_client.vector_search_text", return_value=[]), \
             patch("services.mongo_client.get_claims", return_value=[]) as mock_get_claims, \
             patch("services.mongo_client.get_sessions", return_value=[]) as mock_get_sessions:
            evidence = _get_rag_evidence(claims)

        # Should fall back to time-based
        mock_get_claims.assert_called_once()
        mock_get_sessions.assert_called_once()

    def test_falls_back_when_vector_search_raises_exception(self):
        """Should gracefully degrade to time-based when vector search fails."""
        from services.consistency import _get_rag_evidence

        claims = [{"claim_text": "test claim"}]

        with patch("services.mongo_client.vector_search_text", side_effect=Exception("index missing")), \
             patch("services.mongo_client.get_claims", return_value=[]) as mock_get_claims, \
             patch("services.mongo_client.get_sessions", return_value=[]) as mock_get_sessions:
            evidence = _get_rag_evidence(claims)

        mock_get_claims.assert_called_once()
        mock_get_sessions.assert_called_once()

    def test_skips_vector_search_when_no_claim_text(self):
        """Should fall back when claims have no text to build query."""
        from services.consistency import _get_rag_evidence

        claims = [{"claim_type": "decision"}]  # No claim_text

        with patch("services.mongo_client.vector_search_text") as mock_vector, \
             patch("services.mongo_client.get_claims", return_value=[]), \
             patch("services.mongo_client.get_sessions", return_value=[]):
            _get_rag_evidence(claims)

        # vector_search_text should not be called with empty query
        mock_vector.assert_not_called()


# ===========================================================================
# Feature 3: Direct Corrections with Consistency Check
# ===========================================================================


class TestDirectCorrectionWithConsistencyCheck:
    """Feature 3: Tests for _apply_direct_correction() with consistency check."""

    def test_applies_correction_even_when_contradictions_found(self):
        """Correction should always apply, even when consistency check finds issues."""
        from app.components.chat import _apply_direct_correction

        mock_consistency = {
            "has_contradictions": True,
            "pass2": {
                "retained": [
                    {
                        "severity": "Notable",
                        "evidence_summary": "This contradicts the current target market decision.",
                    }
                ]
            },
        }

        mock_update = {"success": True, "message": "1 change(s) applied."}

        with patch("services.document_updater.update_document", return_value=mock_update) as mock_ud, \
             patch("services.consistency.run_consistency_check", return_value=mock_consistency):
            result = _apply_direct_correction("No, our target market is actually enterprise")

        mock_ud.assert_called_once()
        assert "Got it — updated" in result
        assert "Heads up" in result
        assert "Notable" in result

    def test_applies_correction_when_no_contradictions(self):
        """Correction should apply cleanly when no contradictions found."""
        from app.components.chat import _apply_direct_correction

        mock_consistency = {"has_contradictions": False}
        mock_update = {"success": True, "message": "1 change(s) applied."}

        with patch("services.document_updater.update_document", return_value=mock_update), \
             patch("services.consistency.run_consistency_check", return_value=mock_consistency):
            result = _apply_direct_correction("No, the price is actually 75K")

        assert "Got it — updated" in result
        assert "Heads up" not in result

    def test_applies_correction_when_consistency_check_fails(self):
        """Correction should apply even when consistency check raises an exception."""
        from app.components.chat import _apply_direct_correction

        mock_update = {"success": True, "message": "1 change(s) applied."}

        with patch("services.document_updater.update_document", return_value=mock_update), \
             patch("services.consistency.run_consistency_check", side_effect=Exception("API error")):
            result = _apply_direct_correction("Actually, we're targeting the US market")

        assert "Got it — updated" in result
        assert "Heads up" not in result

    def test_consistency_check_called_with_synthetic_claim(self):
        """Should call run_consistency_check with a synthetic claim from user message."""
        from app.components.chat import _apply_direct_correction

        mock_update = {"success": True, "message": "ok"}

        with patch("services.document_updater.update_document", return_value=mock_update), \
             patch("services.consistency.run_consistency_check", return_value={"has_contradictions": False}) as mock_cc:
            _apply_direct_correction("No, our pricing is 100K")

        mock_cc.assert_called_once()
        args = mock_cc.call_args
        claims = args[0][0]
        assert len(claims) == 1
        assert claims[0]["claim_text"] == "No, our pricing is 100K"
        assert claims[0]["claim_type"] == "decision"
        assert args[1]["session_type"] == "Direct correction"

    def test_handles_update_failure(self):
        """Should return error message when update_document fails."""
        from app.components.chat import _apply_direct_correction

        mock_update = {"success": False, "message": "Verification failed"}

        with patch("services.document_updater.update_document", return_value=mock_update), \
             patch("services.consistency.run_consistency_check", return_value={"has_contradictions": False}):
            result = _apply_direct_correction("No, it's wrong")

        assert "ran into an issue" in result

    def test_handles_complete_exception(self):
        """Should return error message when entire function fails."""
        from app.components.chat import _apply_direct_correction

        with patch("services.document_updater.update_document", side_effect=Exception("fatal")), \
             patch("services.consistency.run_consistency_check", return_value={"has_contradictions": False}):
            result = _apply_direct_correction("Change it")

        assert "Could not auto-update" in result


# ===========================================================================
# Feature 4: Dismissed Contradictions + Decision Log Entries
# ===========================================================================


class TestResolveContradictionKeep:
    """Feature 4: 'keep' action should add Dismissed Contradiction, NOT call update_document."""

    def test_keep_adds_dismissed_entry(self):
        """'keep' should call _add_dismissed() and NOT call update_document()."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "We should target enterprise",
            "existing_position": "Small nuclear plants",
            "existing_section": "Current State → Target Market",
            "tension_description": "Different target market",
        }

        mock_doc = "## Dismissed Contradictions\n[No dismissed contradictions]\n"

        with patch("services.document_updater.update_document") as mock_update, \
             patch("services.document_updater.read_living_document", return_value=mock_doc), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._add_dismissed") as mock_dismissed, \
             patch("services.document_updater._add_decision") as mock_decision, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            mock_dismissed.return_value = "## Dismissed Contradictions\n- dismissed entry\n"

            _resolve_contradiction(contradiction, "keep", "", "")

        # Should NOT call update_document for "keep"
        mock_update.assert_not_called()
        # Should call _add_dismissed
        mock_dismissed.assert_called_once()
        dismissed_args = mock_dismissed.call_args[0]
        assert "Dismissed" in dismissed_args[1]
        assert "We should target enterprise" in dismissed_args[1]
        # Should NOT call _add_decision
        mock_decision.assert_not_called()
        # Should write the document
        mock_write.assert_called_once()

    def test_keep_calls_git_commit(self):
        """'keep' should git commit the dismissed entry."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "test",
            "existing_position": "existing",
            "existing_section": "Section",
            "tension_description": "tension",
        }

        with patch("services.document_updater.update_document"), \
             patch("services.document_updater.read_living_document", return_value="doc"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._add_dismissed", return_value="doc"), \
             patch("services.document_updater._git_commit", return_value=True) as mock_git, \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            _resolve_contradiction(contradiction, "keep", "", "")

        mock_git.assert_called_once()
        assert "Dismissed" in mock_git.call_args[0][0]


class TestResolveContradictionUpdate:
    """Feature 4: 'update' action should call update_document AND _add_decision."""

    def test_update_calls_both_update_and_decision(self):
        """'update' should call update_document() AND _add_decision()."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "Enterprise is our market",
            "existing_position": "Small nuclear plants",
            "existing_section": "Current State → Target Market",
            "tension_description": "Market shift",
        }

        with patch("services.document_updater.update_document") as mock_update, \
             patch("services.document_updater.read_living_document", return_value="## Decision Log\n"), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._add_decision") as mock_decision, \
             patch("services.document_updater._add_dismissed") as mock_dismissed, \
             patch("services.document_updater._git_commit", return_value=True) as mock_git, \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            mock_decision.return_value = "## Decision Log\n- entry\n"

            _resolve_contradiction(contradiction, "update", "Enterprise is our market", "")

        # Should call update_document
        mock_update.assert_called_once()
        # Should call _add_decision
        mock_decision.assert_called_once()
        decision_args = mock_decision.call_args[0]
        assert "Enterprise is our market" in decision_args[1]
        assert "Contradiction resolution" in decision_args[1]
        # Should NOT call _add_dismissed
        mock_dismissed.assert_not_called()
        # Should git commit
        mock_git.assert_called_once()
        assert "Decision log" in mock_git.call_args[0][0]

    def test_update_mirrors_to_mongodb(self):
        """'update' should call upsert_living_document after adding decision."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "test",
            "existing_position": "existing",
            "existing_section": "Section",
            "tension_description": "tension",
        }

        with patch("services.document_updater.update_document"), \
             patch("services.document_updater.read_living_document", return_value="doc"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._add_decision", return_value="updated_doc"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True) as mock_upsert:

            _resolve_contradiction(contradiction, "update", "new position", "")

        mock_upsert.assert_called_once()


class TestResolveContradictionExplain:
    """Feature 4: 'explain' action should call update_document AND _add_decision with explanation."""

    def test_explain_includes_explanation_in_decision(self):
        """'explain' should include the explanation text in the Decision Log entry."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "We changed pricing",
            "existing_position": "50K per facility",
            "existing_section": "Current State → Pricing",
            "tension_description": "Pricing change",
        }

        with patch("services.document_updater.update_document") as mock_update, \
             patch("services.document_updater.read_living_document", return_value="## Decision Log\n"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._add_decision") as mock_decision, \
             patch("services.document_updater._add_dismissed") as mock_dismissed, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            mock_decision.return_value = "## Decision Log\n- entry\n"

            _resolve_contradiction(
                contradiction, "explain", "New pricing is 75K",
                "Customer feedback showed 50K was too low",
            )

        mock_update.assert_called_once()
        # Check update_document received the explanation
        update_args = mock_update.call_args
        assert "Customer feedback showed 50K was too low" in update_args[0][0]

        mock_decision.assert_called_once()
        decision_args = mock_decision.call_args[0]
        assert "New pricing is 75K" in decision_args[1]
        assert "Customer feedback showed 50K was too low" in decision_args[1]

        mock_dismissed.assert_not_called()

    def test_explain_calls_git_commit(self):
        """'explain' should git commit with a Decision log message."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "test",
            "existing_position": "existing",
            "existing_section": "Section",
            "tension_description": "tension",
        }

        with patch("services.document_updater.update_document"), \
             patch("services.document_updater.read_living_document", return_value="doc"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._add_decision", return_value="doc"), \
             patch("services.document_updater._git_commit", return_value=True) as mock_git, \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            _resolve_contradiction(contradiction, "explain", "new", "because reasons")

        mock_git.assert_called_once()
        assert "Decision log" in mock_git.call_args[0][0]


class TestResolveContradictionErrorHandling:
    """Feature 4: Verify graceful error handling in _resolve_contradiction."""

    def test_exception_shows_warning(self):
        """Should display st.warning on exception, not crash."""
        from app.components.chat import _resolve_contradiction

        contradiction = {
            "new_claim": "test",
            "existing_position": "existing",
            "existing_section": "Section",
            "tension_description": "tension",
        }

        mock_st.warning.reset_mock()

        with patch("services.document_updater.update_document", side_effect=Exception("fail")):
            # Should not raise
            _resolve_contradiction(contradiction, "update", "new", "")

        mock_st.warning.assert_called()


# ===========================================================================
# RAG Health Monitor
# ===========================================================================


class TestCheckRagHealth:
    """Tests for check_rag_health() threshold monitoring."""

    def test_below_threshold_no_upgrade_needed(self):
        """Should report healthy when claim count is below threshold."""
        from services.consistency import check_rag_health, RAG_UPGRADE_CLAIM_THRESHOLD

        with patch("services.mongo_client.count_documents", return_value=50):
            result = check_rag_health()

        assert result["needs_upgrade"] is False
        assert result["claim_count"] == 50
        assert result["threshold"] == RAG_UPGRADE_CLAIM_THRESHOLD
        assert "50" in result["message"]

    def test_at_threshold_upgrade_needed(self):
        """Should flag upgrade needed when claim count equals threshold."""
        from services.consistency import check_rag_health, RAG_UPGRADE_CLAIM_THRESHOLD

        with patch("services.mongo_client.count_documents", return_value=RAG_UPGRADE_CLAIM_THRESHOLD):
            result = check_rag_health()

        assert result["needs_upgrade"] is True
        assert "Upgrade" in result["message"]

    def test_above_threshold_upgrade_needed(self):
        """Should flag upgrade needed when claim count exceeds threshold."""
        from services.consistency import check_rag_health

        with patch("services.mongo_client.count_documents", return_value=500):
            result = check_rag_health()

        assert result["needs_upgrade"] is True
        assert result["claim_count"] == 500
        assert "M10+" in result["message"]

    def test_zero_claims_no_upgrade(self):
        """Should report healthy when no claims exist."""
        from services.consistency import check_rag_health

        with patch("services.mongo_client.count_documents", return_value=0):
            result = check_rag_health()

        assert result["needs_upgrade"] is False
        assert result["claim_count"] == 0

    def test_remaining_count_in_message(self):
        """Should show how many claims remain before upgrade is needed."""
        from services.consistency import check_rag_health, RAG_UPGRADE_CLAIM_THRESHOLD

        with patch("services.mongo_client.count_documents", return_value=150):
            result = check_rag_health()

        remaining = RAG_UPGRADE_CLAIM_THRESHOLD - 150
        assert str(remaining) in result["message"]


class TestCountDocuments:
    """Tests for count_documents() in mongo_client."""

    def test_counts_documents(self):
        """Should return count from collection."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.count_documents.return_value = 42

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.count_documents("claims")
            assert result == 42

    def test_returns_zero_when_db_none(self):
        """Should return 0 when database is unavailable."""
        import services.mongo_client as mc

        with patch.object(mc, "get_db", return_value=None):
            result = mc.count_documents("claims")
            assert result == 0

    def test_returns_zero_on_exception(self):
        """Should return 0 on exception."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.count_documents.side_effect = Exception("error")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.count_documents("claims")
            assert result == 0

    def test_passes_query_filter(self):
        """Should pass query parameter to count_documents."""
        import services.mongo_client as mc

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.count_documents.return_value = 5

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.count_documents("claims", {"source_type": "session"})
            mock_collection.count_documents.assert_called_once_with({"source_type": "session"})


class TestGetRagEvidenceLogsWarning:
    """Test that _get_rag_evidence logs a warning when over threshold and using fallback."""

    def test_logs_warning_when_over_threshold(self):
        """Should log warning when claim count exceeds threshold during fallback."""
        from services.consistency import _get_rag_evidence, RAG_UPGRADE_CLAIM_THRESHOLD

        claims = [{"claim_text": "test"}]

        with patch("services.mongo_client.vector_search_text", return_value=[]), \
             patch("services.mongo_client.get_claims", return_value=[]), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.count_documents", return_value=RAG_UPGRADE_CLAIM_THRESHOLD + 50), \
             patch("logging.warning") as mock_warning:
            _get_rag_evidence(claims)

        mock_warning.assert_called_once()
        warning_msg = mock_warning.call_args[0][0]
        assert "time-based fallback" in warning_msg

    def test_no_warning_when_below_threshold(self):
        """Should not log warning when claim count is below threshold."""
        from services.consistency import _get_rag_evidence

        claims = [{"claim_text": "test"}]

        with patch("services.mongo_client.vector_search_text", return_value=[]), \
             patch("services.mongo_client.get_claims", return_value=[]), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.count_documents", return_value=10), \
             patch("logging.warning") as mock_warning:
            _get_rag_evidence(claims)

        mock_warning.assert_not_called()
