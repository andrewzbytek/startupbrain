"""
Unit tests for hypothesis tracking across document_updater, mongo_client, and chat.
All tests run without API keys, MongoDB, or network access.
"""

import sys
from datetime import datetime, timezone
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
sys.modules.setdefault("streamlit", mock_st)

from tests.conftest import get_sample_living_document


# ---------------------------------------------------------------------------
# TestParseHypotheses (sidebar parser)
# ---------------------------------------------------------------------------

class TestParseHypotheses:
    """Tests for _parse_hypotheses from sidebar.py."""

    def test_parses_populated_doc(self):
        from app.components.sidebar import _parse_hypotheses
        doc = get_sample_living_document()
        result = _parse_hypotheses(doc)
        assert len(result) == 2

    def test_first_hypothesis_fields(self):
        from app.components.sidebar import _parse_hypotheses
        doc = get_sample_living_document()
        result = _parse_hypotheses(doc)
        h = result[0]
        assert h["date"] == "2026-02-10"
        assert "procurement cycles" in h["text"]
        assert h["status"] == "unvalidated"
        assert "plant operators" in h["test"]
        assert h["evidence"] == "---"

    def test_second_hypothesis_has_evidence(self):
        from app.components.sidebar import _parse_hypotheses
        doc = get_sample_living_document()
        result = _parse_hypotheses(doc)
        h = result[1]
        assert h["status"] == "testing"
        assert "93%" in h["evidence"]

    def test_empty_doc_returns_empty(self):
        from app.components.sidebar import _parse_hypotheses
        assert _parse_hypotheses("") == []

    def test_placeholder_returns_empty(self):
        from app.components.sidebar import _parse_hypotheses
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        assert _parse_hypotheses(doc) == []

    def test_no_section_returns_empty(self):
        from app.components.sidebar import _parse_hypotheses
        doc = "# Startup Brain\n\n## Decision Log\nSome content."
        assert _parse_hypotheses(doc) == []

    def test_all_statuses_parsed(self):
        from app.components.sidebar import _parse_hypotheses
        doc = """## Active Hypotheses
- [2026-03-01] **Hyp one**
  Status: unvalidated | Test: test1
  Evidence: ---
- [2026-03-02] **Hyp two**
  Status: testing | Test: test2
  Evidence: some data
- [2026-03-03] **Hyp three**
  Status: validated | Test: test3
  Evidence: confirmed
- [2026-03-04] **Hyp four**
  Status: invalidated | Test: test4
  Evidence: disproved

## Decision Log
"""
        result = _parse_hypotheses(doc)
        assert len(result) == 4
        statuses = [h["status"] for h in result]
        assert statuses == ["unvalidated", "testing", "validated", "invalidated"]


# ---------------------------------------------------------------------------
# TestAddHypothesis (document_updater)
# ---------------------------------------------------------------------------

class TestAddHypothesis:
    """Tests for _add_hypothesis from document_updater.py."""

    def test_adds_to_existing_section(self):
        from services.document_updater import _add_hypothesis
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        entry = "- [2026-03-01] **Test hypothesis**\n  Status: unvalidated | Test: TBD\n  Evidence: ---"
        result = _add_hypothesis(doc, entry)
        assert "Test hypothesis" in result
        assert "[No hypotheses tracked yet]" not in result

    def test_placeholder_replaced(self):
        from services.document_updater import _add_hypothesis
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        entry = "- [2026-03-01] **New hyp**\n  Status: unvalidated | Test: x\n  Evidence: ---"
        result = _add_hypothesis(doc, entry)
        assert "[No hypotheses tracked yet]" not in result
        assert "New hyp" in result

    def test_creates_section_if_missing(self):
        from services.document_updater import _add_hypothesis
        doc = "# Startup Brain\n\n## Decision Log\nSome content."
        entry = "- [2026-03-01] **Missing section test**\n  Status: unvalidated | Test: x\n  Evidence: ---"
        result = _add_hypothesis(doc, entry)
        assert "## Active Hypotheses" in result
        assert "Missing section test" in result
        # Should be before Decision Log
        ah_idx = result.index("## Active Hypotheses")
        dl_idx = result.index("## Decision Log")
        assert ah_idx < dl_idx

    def test_preserves_existing_entries(self):
        from services.document_updater import _add_hypothesis
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-01] **Existing one**\n  Status: unvalidated | Test: x\n  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        entry = "- [2026-03-01] **New one**\n  Status: unvalidated | Test: y\n  Evidence: ---"
        result = _add_hypothesis(doc, entry)
        assert "Existing one" in result
        assert "New one" in result

    def test_appends_to_end_if_no_decision_log(self):
        from services.document_updater import _add_hypothesis
        doc = "# Startup Brain\n\nSome content."
        entry = "- [2026-03-01] **End test**\n  Status: unvalidated | Test: x\n  Evidence: ---"
        result = _add_hypothesis(doc, entry)
        assert "## Active Hypotheses" in result
        assert "End test" in result


# ---------------------------------------------------------------------------
# TestUpdateHypothesisStatus (document_updater)
# ---------------------------------------------------------------------------

class TestUpdateHypothesisStatus:
    """Tests for _update_hypothesis_status from document_updater.py."""

    def test_changes_status(self):
        from services.document_updater import _update_hypothesis_status
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-10] **Small nuclear plants have procurement cycles under 12 months**\n"
            "  Status: unvalidated | Test: Ask 3 plant operators directly\n"
            "  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        result = _update_hypothesis_status(doc, "Small nuclear plants have procurement cycles under 12 months", "validated")
        assert "Status: validated" in result
        assert "Status: unvalidated" not in result

    def test_appends_evidence(self):
        from services.document_updater import _update_hypothesis_status
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-10] **Test hyp**\n"
            "  Status: unvalidated | Test: test\n"
            "  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        result = _update_hypothesis_status(doc, "Test hyp", "testing", evidence_update="Found evidence X")
        assert "Status: testing" in result
        assert "Found evidence X" in result
        assert "---" not in result.split("Evidence: ")[1].split("\n")[0]

    def test_no_match_returns_unchanged(self):
        from services.document_updater import _update_hypothesis_status
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-10] **Existing hyp**\n"
            "  Status: unvalidated | Test: test\n"
            "  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        result = _update_hypothesis_status(doc, "Nonexistent hypothesis", "validated")
        assert result == doc

    def test_special_regex_chars_in_fragment(self):
        from services.document_updater import _update_hypothesis_status
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-10] **Price is $50K+ (per facility)**\n"
            "  Status: unvalidated | Test: test\n"
            "  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        # Should not crash — re.escape handles special chars
        result = _update_hypothesis_status(doc, "Price is $50K+ (per facility)", "validated")
        assert "Status: validated" in result


# ---------------------------------------------------------------------------
# TestApplyDiffWithHypothesis
# ---------------------------------------------------------------------------

class TestApplyDiffWithHypothesis:
    """Tests for apply_diff handling ADD_HYPOTHESIS action."""

    def test_add_hypothesis_dispatches(self):
        from services.document_updater import apply_diff
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        blocks = [{"section": "Active Hypotheses", "action": "ADD_HYPOTHESIS",
                    "content": "- [2026-03-01] **Test**\n  Status: unvalidated | Test: x\n  Evidence: ---"}]
        result = apply_diff(doc, blocks)
        assert "Test" in result
        assert "[No hypotheses tracked yet]" not in result


# ---------------------------------------------------------------------------
# TestIsHypothesis / TestIsHypothesisStatusUpdate (chat prefix detection)
# ---------------------------------------------------------------------------

class TestIsHypothesis:
    """Tests for _is_hypothesis from chat.py."""

    def test_hypothesis_prefix(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("hypothesis: Small plants have fast cycles") is True

    def test_case_insensitive(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("HYPOTHESIS: test") is True
        assert _is_hypothesis("Hypothesis: test") is True

    def test_no_space_after_colon(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("hypothesis:test") is True

    def test_normal_message_returns_false(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("What is our hypothesis about pricing?") is False

    def test_empty_returns_false(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("") is False

    def test_whitespace_handling(self):
        from app.components.chat import _is_hypothesis
        assert _is_hypothesis("  hypothesis: test  ") is True


class TestIsHypothesisStatusUpdate:
    """Tests for _is_hypothesis_status_update from chat.py."""

    def test_validated_prefix(self):
        from app.components.chat import _is_hypothesis_status_update
        assert _is_hypothesis_status_update("validated: procurement cycles confirmed") is True

    def test_invalidated_prefix(self):
        from app.components.chat import _is_hypothesis_status_update
        assert _is_hypothesis_status_update("invalidated: LLM accuracy below target") is True

    def test_case_insensitive(self):
        from app.components.chat import _is_hypothesis_status_update
        assert _is_hypothesis_status_update("VALIDATED: test") is True
        assert _is_hypothesis_status_update("INVALIDATED: test") is True

    def test_normal_message_returns_false(self):
        from app.components.chat import _is_hypothesis_status_update
        assert _is_hypothesis_status_update("The hypothesis was validated by testing") is False

    def test_empty_returns_false(self):
        from app.components.chat import _is_hypothesis_status_update
        assert _is_hypothesis_status_update("") is False


# ---------------------------------------------------------------------------
# TestStripHypothesisPrefix / TestStripStatusPrefix
# ---------------------------------------------------------------------------

class TestStripHypothesisPrefix:
    """Tests for _strip_hypothesis_prefix from chat.py."""

    def test_strips_prefix(self):
        from app.components.chat import _strip_hypothesis_prefix
        assert _strip_hypothesis_prefix("hypothesis: Small plants are fast") == "Small plants are fast"

    def test_case_insensitive(self):
        from app.components.chat import _strip_hypothesis_prefix
        assert _strip_hypothesis_prefix("HYPOTHESIS: test") == "test"

    def test_no_prefix(self):
        from app.components.chat import _strip_hypothesis_prefix
        assert _strip_hypothesis_prefix("no prefix here") == "no prefix here"


class TestStripStatusPrefix:
    """Tests for _strip_status_prefix from chat.py."""

    def test_validated_prefix(self):
        from app.components.chat import _strip_status_prefix
        status, text = _strip_status_prefix("validated: procurement cycles")
        assert status == "validated"
        assert text == "procurement cycles"

    def test_invalidated_prefix(self):
        from app.components.chat import _strip_status_prefix
        status, text = _strip_status_prefix("invalidated: LLM accuracy")
        assert status == "invalidated"
        assert text == "LLM accuracy"

    def test_no_prefix(self):
        from app.components.chat import _strip_status_prefix
        status, text = _strip_status_prefix("no prefix")
        assert status == ""
        assert text == "no prefix"


# ---------------------------------------------------------------------------
# TestApplyHypothesis (mocked integration)
# ---------------------------------------------------------------------------

class TestApplyHypothesis:
    """Tests for _apply_hypothesis from chat.py with mocked services."""

    def test_returns_confirmation(self):
        from app.components.chat import _apply_hypothesis
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        with patch("services.document_updater.read_living_document", return_value=doc), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.insert_claim", return_value="mock_id"), \
             patch("services.mongo_client.upsert_living_document", return_value=True):
            result = _apply_hypothesis("hypothesis: Test hypothesis text")
            assert "Hypothesis tracked" in result
            assert "Test hypothesis text" in result

    def test_empty_hypothesis_returns_error(self):
        from app.components.chat import _apply_hypothesis
        result = _apply_hypothesis("hypothesis:")
        assert "Please provide" in result

    def test_graceful_failure(self):
        from app.components.chat import _apply_hypothesis
        with patch("services.document_updater.read_living_document", side_effect=Exception("read fail")):
            result = _apply_hypothesis("hypothesis: test")
            assert "Could not track" in result


# ---------------------------------------------------------------------------
# TestApplyHypothesisStatusUpdate (mocked integration)
# ---------------------------------------------------------------------------

class TestApplyHypothesisStatusUpdate:
    """Tests for _apply_hypothesis_status_update from chat.py with mocked services."""

    def test_returns_confirmation(self):
        from app.components.chat import _apply_hypothesis_status_update
        doc = (
            "## Active Hypotheses\n"
            "- [2026-02-10] **Test hyp**\n"
            "  Status: unvalidated | Test: test\n"
            "  Evidence: ---\n"
            "\n## Decision Log\n"
        )
        with patch("services.document_updater.read_living_document", return_value=doc), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.update_hypothesis_status", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):
            result = _apply_hypothesis_status_update("validated: Test hyp")
            assert "validated" in result

    def test_no_match_returns_error(self):
        from app.components.chat import _apply_hypothesis_status_update
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        with patch("services.document_updater.read_living_document", return_value=doc):
            result = _apply_hypothesis_status_update("validated: Nonexistent")
            assert "Could not find" in result


# ---------------------------------------------------------------------------
# TestGetHypotheses (mongo_client)
# ---------------------------------------------------------------------------

class TestGetHypotheses:
    """Tests for get_hypotheses from mongo_client.py."""

    def test_queries_with_claim_type(self):
        from services.mongo_client import get_hypotheses
        with patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            get_hypotheses()
            mock_find.assert_called_once_with(
                "claims", query={"claim_type": "hypothesis"},
                sort_by="created_at", sort_order=-1, limit=50,
            )

    def test_filters_by_status(self):
        from services.mongo_client import get_hypotheses
        with patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            get_hypotheses(status="unvalidated")
            mock_find.assert_called_once_with(
                "claims", query={"claim_type": "hypothesis", "status": "unvalidated"},
                sort_by="created_at", sort_order=-1, limit=50,
            )

    def test_respects_limit(self):
        from services.mongo_client import get_hypotheses
        with patch("services.mongo_client.find_many", return_value=[]) as mock_find:
            get_hypotheses(limit=10)
            assert mock_find.call_args[1]["limit"] == 10


# ---------------------------------------------------------------------------
# TestUpdateHypothesisStatusMongo
# ---------------------------------------------------------------------------

class TestUpdateHypothesisStatusMongo:
    """Tests for update_hypothesis_status from mongo_client.py."""

    def test_returns_false_when_no_db(self):
        from services.mongo_client import update_hypothesis_status
        with patch("services.mongo_client.get_db", return_value=None):
            assert update_hypothesis_status("test", "validated") is False

    def test_returns_true_on_match(self):
        from services.mongo_client import update_hypothesis_status
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        with patch("services.mongo_client.get_db", return_value=mock_db):
            assert update_hypothesis_status("test hyp", "validated") is True

    def test_returns_false_on_no_match(self):
        from services.mongo_client import update_hypothesis_status
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=0)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        with patch("services.mongo_client.get_db", return_value=mock_db):
            assert update_hypothesis_status("nonexistent", "validated") is False

    def test_returns_false_on_exception(self):
        from services.mongo_client import update_hypothesis_status
        mock_collection = MagicMock()
        mock_collection.update_one.side_effect = Exception("db error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        with patch("services.mongo_client.get_db", return_value=mock_db):
            assert update_hypothesis_status("test", "validated") is False


# ---------------------------------------------------------------------------
# TestHypothesisRelevanceNote (keyword overlap in main.py)
# ---------------------------------------------------------------------------

class TestHypothesisRelevanceNote:
    """Tests for the keyword overlap logic used in hypothesis relevance check."""

    def test_overlapping_words_detected(self):
        """3+ significant word overlap should match."""
        import re
        _stop_words = {"the", "a", "an", "is", "are", "to", "of", "in", "for", "and", "we", "our"}

        def _significant_words(text):
            return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2 and w not in _stop_words}

        hyp_text = "Small nuclear plants have procurement cycles under 12 months"
        claim_text = "We confirmed that small nuclear plants in the UK have fast procurement"
        overlap = _significant_words(hyp_text) & _significant_words(claim_text)
        assert len(overlap) >= 3

    def test_no_overlap_not_detected(self):
        """Unrelated texts should not match."""
        import re
        _stop_words = {"the", "a", "an", "is", "are", "to", "of", "in", "for", "and", "we", "our"}

        def _significant_words(text):
            return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2 and w not in _stop_words}

        hyp_text = "Small nuclear plants have procurement cycles under 12 months"
        claim_text = "Our branding needs to be refreshed based on investor feedback"
        overlap = _significant_words(hyp_text) & _significant_words(claim_text)
        assert len(overlap) < 3
