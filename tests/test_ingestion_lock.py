"""
Unit tests for services/ingestion_lock.py — MongoDB-based ingestion lock.
All tests run without MongoDB or network access, using mocked collections.
"""

import sys
from datetime import datetime, timezone, timedelta
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


# Mock streamlit before importing modules
mock_st = MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)
mock_st = sys.modules["streamlit"]
if not isinstance(getattr(mock_st, 'session_state', None), _AttrDict):
    mock_st.session_state = _AttrDict()

import services.ingestion_lock as lock_module
from services.ingestion_lock import (
    acquire_lock,
    release_lock,
    check_lock,
    ensure_lock_document,
    LOCK_TIMEOUT_MINUTES,
)


@pytest.fixture
def mock_collection():
    """Provide a mocked MongoDB collection and patch it in."""
    collection = MagicMock()
    with patch.object(lock_module, "_get_lock_collection", return_value=collection):
        yield collection


@pytest.fixture
def no_mongo():
    """Simulate MongoDB being unavailable."""
    with patch.object(lock_module, "_get_lock_collection", return_value=None):
        yield


class TestAcquireLock:
    def test_acquire_unlocked(self, mock_collection):
        """Lock can be acquired when not held."""
        mock_collection.find_one_and_update.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "session_id": "sess-1",
        }
        result = acquire_lock(session_id="sess-1")
        assert result["acquired"] is True

    def test_acquire_already_locked(self, mock_collection):
        """Lock cannot be acquired when held by another session."""
        mock_collection.find_one_and_update.return_value = None
        mock_collection.find_one.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "locked_at": datetime.now(timezone.utc),
            "session_id": "other-session",
        }
        result = acquire_lock(session_id="my-session")
        assert result["acquired"] is False
        assert "in progress" in result["message"]

    def test_acquire_same_session_refreshes(self, mock_collection):
        """Same session re-acquiring refreshes the lock."""
        # First find_one_and_update (acquire attempt) returns None (lock held)
        # Second find_one_and_update (refresh with session_id filter) returns the doc
        mock_collection.find_one_and_update.side_effect = [
            None,  # acquire attempt fails
            {"_id": "ingestion_lock", "locked": True, "session_id": "sess-1"},  # refresh succeeds
        ]
        mock_collection.find_one.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "locked_at": datetime.now(timezone.utc),
            "session_id": "sess-1",
        }
        result = acquire_lock(session_id="sess-1")
        assert result["acquired"] is True
        assert "refreshed" in result["message"]

    def test_acquire_stale_lock(self, mock_collection):
        """Stale lock (>30 min) can be taken over."""
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES + 5)
        # find_one_and_update succeeds because $or includes stale check
        mock_collection.find_one_and_update.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "locked_at": stale_time,
            "session_id": "new-session",
        }
        result = acquire_lock(session_id="new-session")
        assert result["acquired"] is True

    def test_acquire_first_time_creates_document(self, mock_collection):
        """If lock document doesn't exist, create it."""
        mock_collection.find_one_and_update.return_value = None
        mock_collection.find_one.return_value = None
        mock_collection.insert_one.return_value = MagicMock()
        result = acquire_lock(session_id="first-session")
        assert result["acquired"] is True
        assert "created" in result["message"]

    def test_acquire_no_mongo_fallback(self, no_mongo):
        """When MongoDB is unavailable, lock is skipped."""
        result = acquire_lock(session_id="any")
        assert result["acquired"] is True
        assert "skipped" in result["message"]

    def test_acquire_generates_session_id(self, mock_collection):
        """If no session_id provided, one is generated."""
        mock_collection.find_one_and_update.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
        }
        result = acquire_lock()
        assert result["acquired"] is True


class TestReleaseLock:
    def test_release_held_lock(self, mock_collection):
        """Release a lock that this session holds."""
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        assert release_lock(session_id="sess-1") is True

    def test_release_without_session_id(self, mock_collection):
        """Release any lock without checking session."""
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        assert release_lock() is True

    def test_release_no_mongo(self, no_mongo):
        """When MongoDB is unavailable, release returns True."""
        assert release_lock() is True

    def test_release_wrong_session(self, mock_collection):
        """Release with wrong session_id matches nothing."""
        mock_collection.update_one.return_value = MagicMock(modified_count=0, matched_count=0)
        assert release_lock(session_id="wrong-session") is False


class TestCheckLock:
    def test_check_unlocked(self, mock_collection):
        """Check returns unlocked when not held."""
        mock_collection.find_one.return_value = {
            "_id": "ingestion_lock",
            "locked": False,
        }
        result = check_lock()
        assert result["locked"] is False

    def test_check_locked(self, mock_collection):
        """Check returns locked status."""
        mock_collection.find_one.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "locked_at": datetime.now(timezone.utc),
            "session_id": "sess-1",
        }
        result = check_lock()
        assert result["locked"] is True
        assert result["stale"] is False

    def test_check_stale(self, mock_collection):
        """Check detects stale lock."""
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES + 5)
        mock_collection.find_one.return_value = {
            "_id": "ingestion_lock",
            "locked": True,
            "locked_at": stale_time,
            "session_id": "old-session",
        }
        result = check_lock()
        assert result["locked"] is True
        assert result["stale"] is True

    def test_check_no_document(self, mock_collection):
        """Check returns unlocked when no document exists."""
        mock_collection.find_one.return_value = None
        result = check_lock()
        assert result["locked"] is False

    def test_check_no_mongo(self, no_mongo):
        """When MongoDB is unavailable, check returns unlocked."""
        result = check_lock()
        assert result["locked"] is False


class TestEnsureLockDocument:
    def test_creates_document(self, mock_collection):
        """ensure_lock_document creates the lock doc if missing."""
        ensure_lock_document()
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": "ingestion_lock"}
        assert call_args[1].get("upsert") is True

    def test_no_mongo_no_error(self, no_mongo):
        """ensure_lock_document does nothing when MongoDB is unavailable."""
        ensure_lock_document()  # Should not raise
