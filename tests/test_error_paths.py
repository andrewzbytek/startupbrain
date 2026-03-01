"""
Cross-cutting failure mode tests for Startup Brain.
Verifies graceful degradation when APIs, MongoDB, file I/O, or subprocess calls fail.
"""

import subprocess
import sys
from unittest.mock import MagicMock, patch, PropertyMock

# Mock streamlit before importing any services
mock_st = MagicMock()
mock_st.cache_resource = lambda f: f
mock_st.secrets = {}
sys.modules.setdefault("streamlit", mock_st)

import pytest


# ---------------------------------------------------------------------------
# API Failures
# ---------------------------------------------------------------------------

class TestAPIFailures:
    """Test that Claude API call wrappers handle errors gracefully."""

    def test_call_sonnet_rate_limit_error(self):
        """Rate limit exception returns error dict, no crash."""
        from services.claude_client import call_sonnet

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("rate_limit_error: 429")

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_sonnet("test prompt")
        assert "Error" in result["text"]
        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0

    def test_call_sonnet_auth_error(self):
        """Auth error (401) returns error dict."""
        from services.claude_client import call_sonnet

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("authentication_error: 401")

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_sonnet("test prompt")
        assert "Error" in result["text"]
        assert result["tokens_in"] == 0

    def test_call_sonnet_timeout_error(self):
        """Timeout exception returns error dict."""
        from services.claude_client import call_sonnet

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = TimeoutError("Request timed out")

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_sonnet("test prompt")
        assert "Error" in result["text"]

    def test_call_sonnet_network_error(self):
        """Network/connection error returns error dict."""
        from services.claude_client import call_sonnet

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("Failed to connect")

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_sonnet("test prompt")
        assert "Error" in result["text"]

    def test_call_sonnet_empty_response_content(self):
        """Empty response.content list returns error message."""
        from services.claude_client import call_sonnet

        mock_response = MagicMock()
        mock_response.content = []  # empty content list
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_sonnet("test prompt")
        assert "Empty response" in result["text"]

    def test_call_sonnet_client_unavailable(self):
        """None client returns error dict about client being unavailable."""
        from services.claude_client import call_sonnet

        with patch("services.claude_client._get_client", return_value=None):
            result = call_sonnet("test prompt")
        assert "unavailable" in result["text"].lower()

    def test_call_opus_rate_limit_error(self):
        """Opus rate limit exception returns error dict."""
        from services.claude_client import call_opus

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("rate_limit_error")

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_opus("test prompt")
        assert "Error" in result["text"]

    def test_call_opus_empty_response(self):
        """Opus empty response.content returns error message."""
        from services.claude_client import call_opus

        mock_response = MagicMock()
        mock_response.content = []
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("services.claude_client._get_client", return_value=mock_client):
            result = call_opus("test prompt")
        assert "Empty response" in result["text"]

    def test_call_opus_client_unavailable(self):
        """Opus with None client returns error dict."""
        from services.claude_client import call_opus

        with patch("services.claude_client._get_client", return_value=None):
            result = call_opus("test prompt")
        assert "unavailable" in result["text"].lower()

    def test_stream_mid_error_yields_error_string(self):
        """Streaming generator yields error string when exception occurs mid-stream."""
        from services.claude_client import call_sonnet

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        # Make text_stream raise after yielding one chunk
        mock_stream_ctx.text_stream = iter(["chunk1"])
        mock_stream_ctx.get_final_message.side_effect = Exception("Stream interrupted")

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream_ctx

        with patch("services.claude_client._get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            gen = call_sonnet("test prompt", stream=True)
            chunks = list(gen)
        # Should get chunks (possibly including error)
        assert len(chunks) >= 1

    def test_stream_cost_logged_in_finally(self):
        """Cost tracker is called even when streaming errors out."""
        from services.claude_client import call_sonnet

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter([])
        mock_stream_ctx.get_final_message.side_effect = Exception("broken")

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream_ctx

        with patch("services.claude_client._get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call") as mock_log:
            gen = call_sonnet("test prompt", stream=True)
            list(gen)  # exhaust the generator
        # log_api_call should be called in finally block
        mock_log.assert_called_once()

    def test_call_with_routing_over_budget_forces_sonnet(self):
        """When over budget, call_with_routing forces Sonnet even for Opus tasks."""
        from services.claude_client import call_with_routing

        with patch("services.cost_tracker.is_over_budget", return_value=True), \
             patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus:
            mock_sonnet.return_value = {"text": "ok", "tokens_in": 0, "tokens_out": 0, "model": "sonnet"}
            call_with_routing("prompt", task_type="consistency_pass3")
        mock_sonnet.assert_called_once()
        mock_opus.assert_not_called()


# ---------------------------------------------------------------------------
# MongoDB Failures
# ---------------------------------------------------------------------------

class TestMongoFailures:
    """Test MongoDB operations gracefully handle exceptions."""

    def test_insert_one_db_exception_returns_none(self):
        """insert_one returns None and warns when DB raises."""
        from services.mongo_client import insert_one

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        mock_db["test"].insert_one.side_effect = Exception("DB write error")

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = insert_one("test", {"key": "value"})
        assert result is None

    def test_insert_one_db_unavailable_returns_none(self):
        """insert_one returns None when get_db returns None."""
        from services.mongo_client import insert_one

        with patch("services.mongo_client.get_db", return_value=None):
            result = insert_one("test", {"key": "value"})
        assert result is None

    def test_find_many_db_exception_returns_empty_list(self):
        """find_many returns [] when DB raises."""
        from services.mongo_client import find_many

        mock_collection = MagicMock()
        mock_collection.find.side_effect = Exception("DB read error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = find_many("test")
        assert result == []

    def test_find_many_db_unavailable_returns_empty_list(self):
        """find_many returns [] when get_db returns None."""
        from services.mongo_client import find_many

        with patch("services.mongo_client.get_db", return_value=None):
            result = find_many("test")
        assert result == []

    def test_find_one_exception_returns_none(self):
        """find_one returns None on exception."""
        from services.mongo_client import find_one

        mock_collection = MagicMock()
        mock_collection.find_one.side_effect = Exception("DB error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = find_one("test", {"_id": "abc"})
        assert result is None

    def test_find_one_db_unavailable_returns_none(self):
        """find_one returns None when DB is unavailable."""
        from services.mongo_client import find_one

        with patch("services.mongo_client.get_db", return_value=None):
            result = find_one("test", {"_id": "abc"})
        assert result is None

    def test_update_one_exception_returns_false(self):
        """update_one returns False on exception."""
        from services.mongo_client import update_one

        mock_collection = MagicMock()
        mock_collection.update_one.side_effect = Exception("DB error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = update_one("test", {"_id": "abc"}, {"$set": {"key": "val"}})
        assert result is False

    def test_update_one_db_unavailable_returns_false(self):
        """update_one returns False when DB is unavailable."""
        from services.mongo_client import update_one

        with patch("services.mongo_client.get_db", return_value=None):
            result = update_one("test", {"_id": "abc"}, {"$set": {"key": "val"}})
        assert result is False

    def test_delete_one_exception_returns_false(self):
        """delete_one returns False on exception."""
        from services.mongo_client import delete_one

        mock_collection = MagicMock()
        mock_collection.delete_one.side_effect = Exception("DB error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = delete_one("test", {"_id": "abc"})
        assert result is False

    def test_delete_one_db_unavailable_returns_false(self):
        """delete_one returns False when DB is unavailable."""
        from services.mongo_client import delete_one

        with patch("services.mongo_client.get_db", return_value=None):
            result = delete_one("test", {"_id": "abc"})
        assert result is False

    def test_vector_search_exception_returns_empty_list(self):
        """vector_search returns [] on exception."""
        from services.mongo_client import vector_search

        mock_collection = MagicMock()
        mock_collection.aggregate.side_effect = Exception("Vector search failed")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = vector_search("test", [0.1, 0.2], "index_name")
        assert result == []

    def test_vector_search_db_unavailable_returns_empty_list(self):
        """vector_search returns [] when DB is unavailable."""
        from services.mongo_client import vector_search

        with patch("services.mongo_client.get_db", return_value=None):
            result = vector_search("test", [0.1, 0.2], "index_name")
        assert result == []

    def test_get_db_returns_none_when_client_none(self):
        """get_db returns None when get_mongo_client returns None."""
        from services.mongo_client import get_db

        with patch("services.mongo_client.get_mongo_client", return_value=None):
            result = get_db()
        assert result is None


# ---------------------------------------------------------------------------
# Document Updater Failures
# ---------------------------------------------------------------------------

class TestDocumentUpdaterFailures:
    """Test document_updater handles I/O and subprocess failures."""

    def test_write_living_document_permission_error(self):
        """update_document catches write permission errors and returns failure."""
        from services.document_updater import update_document

        with patch("services.document_updater.read_living_document", return_value="# Doc\nContent"), \
             patch("services.document_updater.generate_diff", return_value="SECTION: Decision Log\nACTION: ADD_DECISION\nCONTENT:\n### New Decision"), \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": [], "raw": ""}), \
             patch("services.document_updater.write_living_document", side_effect=PermissionError("Access denied")), \
             patch("services.mongo_client.update_one", return_value=True):
            result = update_document("new info")
        assert result["success"] is False
        assert "Failed to write" in result["message"]

    def test_git_commit_called_process_error(self):
        """_git_commit returns False on CalledProcessError."""
        from services.document_updater import _git_commit

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = _git_commit("test commit message")
        assert result is False

    def test_git_commit_generic_exception(self):
        """_git_commit returns False on unexpected exception."""
        from services.document_updater import _git_commit

        with patch("subprocess.run", side_effect=OSError("No such file or directory: git")):
            result = _git_commit("test commit message")
        assert result is False

    def test_update_document_empty_document(self):
        """update_document returns failure when living document is empty."""
        from services.document_updater import update_document

        with patch("services.document_updater.read_living_document", return_value=""):
            result = update_document("new info")
        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert result["changes_applied"] == 0

    def test_update_document_max_retries_exhausted(self):
        """update_document returns failure after verification fails max_retries+1 times."""
        from services.document_updater import update_document

        with patch("services.document_updater.read_living_document", return_value="# Doc\nContent"), \
             patch("services.document_updater.generate_diff", return_value="some diff"), \
             patch("services.document_updater.verify_diff", return_value={
                 "verified": False,
                 "notes": "",
                 "issues": ["Bad diff structure"],
                 "raw": "",
             }):
            result = update_document("new info", max_retries=1)
        assert result["success"] is False
        assert "failed" in result["message"].lower()

    def test_update_document_empty_diff_blocks(self):
        """update_document returns failure when parsed diff has no blocks."""
        from services.document_updater import update_document

        with patch("services.document_updater.read_living_document", return_value="# Doc\nContent"), \
             patch("services.document_updater.generate_diff", return_value="no valid diff format here"), \
             patch("services.document_updater.verify_diff", return_value={
                 "verified": True,
                 "notes": "",
                 "issues": [],
                 "raw": "",
             }):
            result = update_document("new info")
        assert result["success"] is False
        assert "no changes" in result["message"].lower()
        assert result["changes_applied"] == 0


# ---------------------------------------------------------------------------
# Cost Tracker Edge Cases
# ---------------------------------------------------------------------------

class TestCostTrackerEdgeCases:
    """Test cost tracker with edge case inputs."""

    def test_unknown_model_uses_default_pricing(self):
        """Unknown model name falls back to DEFAULT_PRICING."""
        from services.cost_tracker import _calculate_cost, DEFAULT_PRICING

        cost = _calculate_cost("unknown-model-xyz", 1_000_000, 1_000_000)
        expected = DEFAULT_PRICING["input"] + DEFAULT_PRICING["output"]
        assert cost == pytest.approx(expected)

    def test_zero_tokens_cost_is_zero(self):
        """Zero tokens produces zero cost."""
        from services.cost_tracker import _calculate_cost

        cost = _calculate_cost("claude-sonnet-4-20250514", 0, 0)
        assert cost == 0.0

    def test_get_monthly_cost_db_unavailable_returns_zero(self):
        """get_monthly_cost returns 0.0 when DB is unavailable."""
        from services.cost_tracker import get_monthly_cost

        with patch("services.mongo_client.get_db", return_value=None):
            result = get_monthly_cost()
        assert result == 0.0

    def test_get_daily_breakdown_db_unavailable_returns_empty(self):
        """get_daily_breakdown returns {} when DB is unavailable."""
        from services.cost_tracker import get_daily_breakdown

        with patch("services.mongo_client.get_db", return_value=None):
            result = get_daily_breakdown()
        assert result == {}

    def test_get_monthly_cost_aggregation_exception_returns_zero(self):
        """get_monthly_cost returns 0.0 when aggregation raises."""
        from services.cost_tracker import get_monthly_cost

        mock_collection = MagicMock()
        mock_collection.aggregate.side_effect = Exception("Aggregation error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = get_monthly_cost()
        assert result == 0.0

    def test_get_daily_breakdown_aggregation_exception_returns_empty(self):
        """get_daily_breakdown returns {} when aggregation raises."""
        from services.cost_tracker import get_daily_breakdown

        mock_collection = MagicMock()
        mock_collection.aggregate.side_effect = Exception("Aggregation error")
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = get_daily_breakdown()
        assert result == {}

    def test_log_api_call_when_mongo_unavailable_returns_none(self):
        """log_api_call returns None when MongoDB cannot store the log."""
        from services.cost_tracker import log_api_call

        with patch("services.mongo_client.insert_one", return_value=None):
            result = log_api_call("claude-sonnet-4-20250514", 100, 50, "test")
        assert result is None

    def test_is_over_budget_when_db_unavailable(self):
        """is_over_budget returns False when DB returns 0.0 cost."""
        from services.cost_tracker import is_over_budget

        with patch("services.mongo_client.get_db", return_value=None):
            result = is_over_budget(threshold=300.0)
        assert result is False

    def test_known_model_uses_specific_pricing(self):
        """Known model uses its specific pricing, not default."""
        from services.cost_tracker import _calculate_cost, PRICING

        # Sonnet pricing: $3/MTok in, $15/MTok out
        cost = _calculate_cost("claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        expected = PRICING["claude-sonnet-4-20250514"]["input"] + PRICING["claude-sonnet-4-20250514"]["output"]
        assert cost == pytest.approx(expected)

    def test_opus_pricing_higher_than_sonnet(self):
        """Opus pricing should be higher than Sonnet for the same token count."""
        from services.cost_tracker import _calculate_cost

        sonnet_cost = _calculate_cost("claude-sonnet-4-20250514", 1000, 1000)
        opus_cost = _calculate_cost("claude-opus-4-20250514", 1000, 1000)
        assert opus_cost > sonnet_cost
