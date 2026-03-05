"""
Unit tests for services/cost_tracker.py.
All tests run without MongoDB, API keys, or network access.
"""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)

# Mock pymongo
mock_pymongo = MagicMock()
mock_pymongo.ASCENDING = 1
mock_pymongo.errors = MagicMock()
mock_pymongo.errors.ConnectionFailure = type("ConnectionFailure", (Exception,), {})
mock_pymongo.errors.ServerSelectionTimeoutError = type("ServerSelectionTimeoutError", (Exception,), {})
sys.modules.setdefault("pymongo", mock_pymongo)
sys.modules.setdefault("pymongo.errors", mock_pymongo.errors)

import services.cost_tracker as ct


# ---------------------------------------------------------------------------
# _calculate_cost tests
# ---------------------------------------------------------------------------

class TestCalculateCost:
    """Tests for _calculate_cost: computes cost from token counts."""

    def test_sonnet_rates(self):
        """Sonnet should use $3/MTok input, $15/MTok output."""
        cost = ct._calculate_cost("claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.0 + 15.0)

    def test_opus_rates(self):
        """Opus should use $15/MTok input, $75/MTok output."""
        cost = ct._calculate_cost("claude-opus-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(15.0 + 75.0)

    def test_zero_tokens(self):
        """Zero tokens should return 0.0."""
        cost = ct._calculate_cost("claude-sonnet-4-20250514", 0, 0)
        assert cost == 0.0

    def test_unknown_model_uses_default(self):
        """Unknown model should fall back to DEFAULT_PRICING."""
        cost = ct._calculate_cost("unknown-model", 1_000_000, 1_000_000)
        expected = ct.DEFAULT_PRICING["input"] + ct.DEFAULT_PRICING["output"]
        assert cost == pytest.approx(expected)

    def test_specific_calculation(self):
        """Verify a specific numerical calculation."""
        # 500 input tokens at $3/MTok = $0.0015
        # 200 output tokens at $15/MTok = $0.003
        cost = ct._calculate_cost("claude-sonnet-4-20250514", 500, 200)
        expected = (500 / 1_000_000) * 3.0 + (200 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected)


# ---------------------------------------------------------------------------
# log_api_call tests
# ---------------------------------------------------------------------------

class TestLogApiCall:
    """Tests for log_api_call: logs API calls to MongoDB."""

    def test_builds_correct_doc(self):
        """Should build document with model, tokens, cost, task_type, timestamp."""
        with patch("services.mongo_client.log_cost", return_value="cost_id") as mock_log:
            ct.log_api_call("claude-sonnet-4-20250514", 1000, 500, "extraction")
            doc = mock_log.call_args[0][0]
            assert doc["model"] == "claude-sonnet-4-20250514"
            assert doc["tokens_in"] == 1000
            assert doc["tokens_out"] == 500
            assert doc["task_type"] == "extraction"
            assert "cost_usd" in doc
            assert "timestamp" not in doc  # removed redundant field; insert_one adds created_at

    def test_calls_mongo_log_cost(self):
        """Should call mongo_client.log_cost."""
        with patch("services.mongo_client.log_cost", return_value="id") as mock_log:
            ct.log_api_call("claude-sonnet-4-20250514", 100, 50, "general")
            mock_log.assert_called_once()

    def test_returns_inserted_id(self):
        """Should return the id from log_cost."""
        with patch("services.mongo_client.log_cost", return_value="cost_abc"):
            result = ct.log_api_call("claude-sonnet-4-20250514", 100, 50, "general")
            assert result == "cost_abc"


# ---------------------------------------------------------------------------
# get_monthly_cost tests
# ---------------------------------------------------------------------------

class TestGetMonthlyCost:
    """Tests for get_monthly_cost: aggregates monthly cost from MongoDB."""

    def test_aggregation_pipeline(self):
        """Should build correct aggregation pipeline."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = [{"_id": None, "total": 42.50}]

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = ct.get_monthly_cost(2026, 2)
            assert result == 42.50
            mock_collection.aggregate.assert_called_once()

    def test_defaults_to_current_month(self):
        """Should default to current year/month when not specified."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch("services.mongo_client.get_db", return_value=mock_db):
            ct.get_monthly_cost()
            mock_collection.aggregate.assert_called_once()

    def test_returns_zero_when_db_none(self):
        """Should return 0.0 when database is unavailable."""
        with patch("services.mongo_client.get_db", return_value=None):
            result = ct.get_monthly_cost()
            assert result == 0.0

    def test_december_year_rollover(self):
        """Should handle December correctly (next month is January of next year)."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = [{"_id": None, "total": 10.0}]

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = ct.get_monthly_cost(2026, 12)
            assert result == 10.0
            pipeline = mock_collection.aggregate.call_args[0][0]
            match_stage = pipeline[0]["$match"]
            # The end date should be January 1 of next year
            assert match_stage["created_at"]["$lt"].year == 2027
            assert match_stage["created_at"]["$lt"].month == 1

    def test_returns_zero_on_empty_result(self):
        """Should return 0.0 when no cost records exist."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = ct.get_monthly_cost(2026, 2)
            assert result == 0.0


# ---------------------------------------------------------------------------
# get_daily_breakdown tests
# ---------------------------------------------------------------------------

class TestGetDailyBreakdown:
    """Tests for get_daily_breakdown: returns daily cost breakdown."""

    def test_returns_dict(self):
        """Should return dict of {date_str: cost_usd}."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = [
            {"_id": "2026-02-01", "total": 5.0},
            {"_id": "2026-02-02", "total": 3.5},
        ]

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = ct.get_daily_breakdown(2026, 2)
            assert result == {"2026-02-01": 5.0, "2026-02-02": 3.5}

    def test_empty_month(self):
        """Should return empty dict for months with no data."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch("services.mongo_client.get_db", return_value=mock_db):
            result = ct.get_daily_breakdown(2026, 2)
            assert result == {}

    def test_returns_empty_when_db_none(self):
        """Should return empty dict when database is unavailable."""
        with patch("services.mongo_client.get_db", return_value=None):
            result = ct.get_daily_breakdown()
            assert result == {}

    def test_december_rollover(self):
        """Should handle December correctly."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch("services.mongo_client.get_db", return_value=mock_db):
            ct.get_daily_breakdown(2026, 12)
            pipeline = mock_collection.aggregate.call_args[0][0]
            match_stage = pipeline[0]["$match"]
            assert match_stage["created_at"]["$lt"].year == 2027


# ---------------------------------------------------------------------------
# is_over_budget tests
# ---------------------------------------------------------------------------

class TestIsOverBudget:
    """Tests for is_over_budget: checks if monthly cost exceeds threshold."""

    def test_true_when_over(self):
        """Should return True when cost exceeds threshold."""
        with patch.object(ct, "get_monthly_cost", return_value=350.0):
            assert ct.is_over_budget(threshold=300.0) is True

    def test_false_when_under(self):
        """Should return False when cost is below threshold."""
        with patch.object(ct, "get_monthly_cost", return_value=100.0):
            assert ct.is_over_budget(threshold=300.0) is False

    def test_false_when_exactly_at(self):
        """Should return False when exactly at threshold (uses > not >=)."""
        with patch.object(ct, "get_monthly_cost", return_value=300.0):
            assert ct.is_over_budget(threshold=300.0) is False

    def test_default_threshold(self):
        """Default threshold should be 300.0."""
        with patch.object(ct, "get_monthly_cost", return_value=301.0):
            assert ct.is_over_budget() is True


# ---------------------------------------------------------------------------
# get_cost_summary tests
# ---------------------------------------------------------------------------

class TestGetCostSummary:
    """Tests for get_cost_summary: formats cost string for sidebar."""

    def test_on_track_format(self):
        """Should show 'on track' when under budget."""
        with patch.object(ct, "get_monthly_cost", return_value=12.34):
            result = ct.get_cost_summary()
            assert result == "This month: $12.34 / $300 budget (on track)"

    def test_over_budget_format(self):
        """Should show 'over budget' when over $300."""
        with patch.object(ct, "get_monthly_cost", return_value=350.50):
            result = ct.get_cost_summary()
            assert result == "This month: $350.50 / $300 budget (over budget)"

    def test_zero_cost(self):
        """Should handle zero cost correctly."""
        with patch.object(ct, "get_monthly_cost", return_value=0.0):
            result = ct.get_cost_summary()
            assert result == "This month: $0.00 / $300 budget (on track)"
