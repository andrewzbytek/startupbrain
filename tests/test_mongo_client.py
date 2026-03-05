"""
Unit tests for services/mongo_client.py.
All tests run without MongoDB, pymongo, or network access.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit and pymongo before importing the module under test
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)

# Mock pymongo so it appears available
mock_pymongo = MagicMock()
mock_pymongo.ASCENDING = 1
mock_pymongo.errors = MagicMock()
mock_pymongo.errors.ConnectionFailure = type("ConnectionFailure", (Exception,), {})
mock_pymongo.errors.ServerSelectionTimeoutError = type("ServerSelectionTimeoutError", (Exception,), {})
sys.modules.setdefault("pymongo", mock_pymongo)
sys.modules.setdefault("pymongo.errors", mock_pymongo.errors)

import services.mongo_client as mc


# ---------------------------------------------------------------------------
# get_mongo_client tests
# ---------------------------------------------------------------------------

class TestGetMongoClient:
    """Tests for get_mongo_client: creates and caches MongoDB client."""

    def test_valid_uri_returns_client(self):
        """Should return a MongoClient when URI is available."""
        mock_st.secrets.__getitem__ = MagicMock(return_value="mongodb+srv://test:test@cluster.mongodb.net")
        original = mc.PYMONGO_AVAILABLE
        try:
            mc.PYMONGO_AVAILABLE = True
            mock_client = MagicMock()
            with patch.object(mc, "MongoClient", return_value=mock_client):
                result = mc.get_mongo_client()
                assert result is mock_client
        finally:
            mc.PYMONGO_AVAILABLE = original

    def test_no_pymongo_returns_none(self):
        """Should return None when pymongo is not available."""
        original = mc.PYMONGO_AVAILABLE
        try:
            mc.PYMONGO_AVAILABLE = False
            result = mc.get_mongo_client()
            assert result is None
        finally:
            mc.PYMONGO_AVAILABLE = original

    def test_no_uri_returns_none(self):
        """Should return None when no URI is configured."""
        fake_secrets = MagicMock()
        fake_secrets.__getitem__ = MagicMock(side_effect=KeyError("MONGODB_URI"))
        original = mc.PYMONGO_AVAILABLE
        try:
            mc.PYMONGO_AVAILABLE = True
            env_copy = {k: v for k, v in os.environ.items() if k != "MONGODB_URI"}
            with patch.object(mc, "st", MagicMock(secrets=fake_secrets, warning=MagicMock())), \
                 patch.dict(os.environ, env_copy, clear=True):
                result = mc.get_mongo_client()
                assert result is None
        finally:
            mc.PYMONGO_AVAILABLE = original

    def test_connection_failure_returns_none(self):
        """Should return None on ConnectionFailure."""
        mock_st.secrets.__getitem__ = MagicMock(return_value="mongodb://test")
        original = mc.PYMONGO_AVAILABLE
        try:
            mc.PYMONGO_AVAILABLE = True
            with patch.object(mc, "MongoClient", side_effect=mc.ConnectionFailure("fail")):
                result = mc.get_mongo_client()
                assert result is None
        finally:
            mc.PYMONGO_AVAILABLE = original

    def test_timeout_returns_none(self):
        """Should return None on ServerSelectionTimeoutError."""
        mock_st.secrets.__getitem__ = MagicMock(return_value="mongodb://test")
        original = mc.PYMONGO_AVAILABLE
        try:
            mc.PYMONGO_AVAILABLE = True
            with patch.object(mc, "MongoClient", side_effect=mc.ServerSelectionTimeoutError("timeout")):
                result = mc.get_mongo_client()
                assert result is None
        finally:
            mc.PYMONGO_AVAILABLE = original


# ---------------------------------------------------------------------------
# get_db tests
# ---------------------------------------------------------------------------

class TestGetDb:
    """Tests for get_db: returns the startup_brain database."""

    def test_returns_database_when_client_available(self):
        """Should return database object from client."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch.object(mc, "get_mongo_client", return_value=mock_client):
            result = mc.get_db()
            assert result is mock_db

    def test_returns_none_when_client_none(self):
        """Should return None when no client available."""
        with patch.object(mc, "get_mongo_client", return_value=None):
            result = mc.get_db()
            assert result is None


# ---------------------------------------------------------------------------
# is_mongo_available tests
# ---------------------------------------------------------------------------

class TestIsMongoAvailable:
    """Tests for is_mongo_available: health check."""

    def test_true_when_available(self):
        with patch.object(mc, "get_mongo_client", return_value=MagicMock()):
            assert mc.is_mongo_available() is True

    def test_false_when_not(self):
        with patch.object(mc, "get_mongo_client", return_value=None):
            assert mc.is_mongo_available() is False


# ---------------------------------------------------------------------------
# insert_one tests
# ---------------------------------------------------------------------------

class TestInsertOne:
    """Tests for insert_one: inserts a document with created_at timestamp."""

    def test_adds_created_at(self):
        """Should add created_at timestamp to the document."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_result = MagicMock()
        mock_result.inserted_id = "abc123"
        mock_collection.insert_one.return_value = mock_result

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.insert_one("sessions", {"data": "test"})
            inserted_doc = mock_collection.insert_one.call_args[0][0]
            assert "created_at" in inserted_doc
            assert isinstance(inserted_doc["created_at"], datetime)

    def test_returns_string_id(self):
        """Should return the inserted _id as string."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_result = MagicMock()
        mock_result.inserted_id = "abc123"
        mock_collection.insert_one.return_value = mock_result

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.insert_one("sessions", {"data": "test"})
            assert result == "abc123"

    def test_returns_none_when_db_none(self):
        """Should return None when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.insert_one("sessions", {"data": "test"})
            assert result is None

    def test_handles_exception(self):
        """Should catch exceptions and return None."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.insert_one.side_effect = Exception("write error")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.insert_one("sessions", {"data": "test"})
            assert result is None


# ---------------------------------------------------------------------------
# find_many tests
# ---------------------------------------------------------------------------

class TestFindMany:
    """Tests for find_many: retrieves documents from a collection."""

    def test_returns_list(self):
        """Should return a list of documents."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [{"doc": 1}, {"doc": 2}]
        mock_collection.find.return_value = mock_cursor

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.find_many("sessions")
            assert len(result) == 2

    def test_returns_empty_list_when_db_none(self):
        """Should return empty list when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.find_many("sessions")
            assert result == []

    def test_respects_limit(self):
        """Should pass the limit parameter to the cursor."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = []
        mock_collection.find.return_value = mock_cursor

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.find_many("sessions", limit=10)
            mock_cursor.limit.assert_called_once_with(10)

    def test_handles_exception(self):
        """Should catch exceptions and return empty list."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find.side_effect = Exception("query error")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.find_many("sessions")
            assert result == []


# ---------------------------------------------------------------------------
# find_one tests
# ---------------------------------------------------------------------------

class TestFindOne:
    """Tests for find_one: retrieves a single document."""

    def test_returns_document(self):
        """Should return a single document dict."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find_one.return_value = {"_id": "1", "data": "test"}

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.find_one("sessions", {"_id": "1"})
            assert result["data"] == "test"

    def test_returns_none_when_db_none(self):
        """Should return None when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.find_one("sessions", {"_id": "1"})
            assert result is None

    def test_handles_exception(self):
        """Should catch exceptions and return None."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find_one.side_effect = Exception("find error")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.find_one("sessions", {"_id": "1"})
            assert result is None


# ---------------------------------------------------------------------------
# update_one tests
# ---------------------------------------------------------------------------

class TestUpdateOne:
    """Tests for update_one: updates a single document."""

    def test_adds_updated_at_to_set(self):
        """Should add updated_at to the $set operation."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_one("sessions", {"_id": "1"}, {"$set": {"name": "test"}})
            update_arg = mock_collection.update_one.call_args[0][1]
            assert "updated_at" in update_arg["$set"]

    def test_creates_set_if_not_present(self):
        """Should create $set with updated_at if not present."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_one("sessions", {"_id": "1"}, {"$inc": {"count": 1}})
            update_arg = mock_collection.update_one.call_args[0][1]
            assert "$set" in update_arg
            assert "updated_at" in update_arg["$set"]

    def test_upsert_parameter_passed(self):
        """Should pass upsert parameter to MongoDB."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.update_one("sessions", {"_id": "1"}, {"$set": {"x": 1}}, upsert=True)
            mock_collection.update_one.assert_called_once()
            assert mock_collection.update_one.call_args[1]["upsert"] is True

    def test_returns_true_on_success(self):
        """Should return True on successful update."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.update_one("sessions", {"_id": "1"}, {"$set": {"x": 1}})
            assert result is True

    def test_returns_false_when_db_none(self):
        """Should return False when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.update_one("sessions", {"_id": "1"}, {"$set": {"x": 1}})
            assert result is False


# ---------------------------------------------------------------------------
# delete_one tests
# ---------------------------------------------------------------------------

class TestDeleteOne:
    """Tests for delete_one: deletes a single document."""

    def test_returns_true_on_success(self):
        """Should return True on successful delete."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.delete_one("sessions", {"_id": "1"})
            assert result is True
            mock_collection.delete_one.assert_called_once_with({"_id": "1"})

    def test_returns_false_when_db_none(self):
        """Should return False when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.delete_one("sessions", {"_id": "1"})
            assert result is False


# ---------------------------------------------------------------------------
# Collection helper delegation tests
# ---------------------------------------------------------------------------

class TestCollectionHelpers:
    """Tests that collection helpers delegate to the correct CRUD function."""

    def test_insert_session(self):
        with patch.object(mc, "insert_one", return_value="id1") as mock:
            result = mc.insert_session({"transcript": "text"})
            mock.assert_called_once_with("sessions", {"transcript": "text", "brain": "pitch"})
            assert result == "id1"

    def test_get_sessions(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_sessions(limit=10)
            mock.assert_called_once_with("sessions", query={}, sort_by="created_at", sort_order=-1, limit=10)

    def test_get_sessions_with_brain(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_sessions(limit=10, brain="pitch")
            call_query = mock.call_args[1]["query"]
            assert "$or" in call_query
            assert {"brain": "pitch"} in call_query["$or"]
            assert {"brain": {"$exists": False}} in call_query["$or"]

    def test_insert_claim(self):
        with patch.object(mc, "insert_one", return_value="id2") as mock:
            result = mc.insert_claim({"claim_text": "test"})
            mock.assert_called_once_with("claims", {"claim_text": "test", "brain": "pitch"})
            assert result == "id2"

    def test_get_claims_no_filter(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_claims()
            mock.assert_called_once_with("claims", query={}, sort_by="created_at", sort_order=-1, limit=200)

    def test_get_claims_with_session_id(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_claims(session_id="s1")
            mock.assert_called_once_with("claims", query={"session_id": "s1"}, sort_by="created_at", sort_order=-1, limit=200)

    def test_insert_whiteboard_extraction(self):
        with patch.object(mc, "insert_one", return_value="id3") as mock:
            mc.insert_whiteboard_extraction({"data": "x"})
            mock.assert_called_once_with("whiteboard_extractions", {"data": "x"})

    def test_insert_feedback(self):
        with patch.object(mc, "insert_one", return_value="id4") as mock:
            mc.insert_feedback({"text": "good"})
            mock.assert_called_once_with("feedback", {"text": "good"})

    def test_get_feedback_no_filter(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_feedback()
            mock.assert_called_once_with("feedback", query={}, sort_by="created_at", sort_order=-1, limit=100)

    def test_get_feedback_with_source_type(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_feedback(source_type="investor")
            mock.assert_called_once_with("feedback", query={"source_type": "investor"}, sort_by="created_at", sort_order=-1, limit=100)

    def test_insert_book_framework(self):
        with patch.object(mc, "insert_one", return_value="id5") as mock:
            mc.insert_book_framework({"title": "Lean"})
            mock.assert_called_once_with("book_frameworks", {"title": "Lean"})

    def test_get_book_frameworks(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_book_frameworks()
            mock.assert_called_once_with("book_frameworks", sort_by="created_at", sort_order=1, limit=20)

    def test_upsert_living_document(self):
        with patch.object(mc, "update_one", return_value=True) as mock:
            result = mc.upsert_living_document("# Document content")
            mock.assert_called_once()
            args = mock.call_args
            assert args[0][0] == "living_document"
            assert args[0][1] == {"_id": "pitch_brain"}
            assert args[1]["upsert"] is True
            assert result is True

    def test_get_living_document(self):
        with patch.object(mc, "find_one", return_value={"content": "doc"}) as mock:
            result = mc.get_living_document()
            mock.assert_called_once_with("living_document", {"_id": "pitch_brain"})
            assert result["content"] == "doc"

    def test_log_cost(self):
        with patch.object(mc, "insert_one", return_value="cost_id") as mock:
            result = mc.log_cost({"cost_usd": 0.05})
            mock.assert_called_once_with("cost_log", {"cost_usd": 0.05})
            assert result == "cost_id"

    def test_get_cost_log(self):
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.get_cost_log(limit=50)
            mock.assert_called_once_with("cost_log", sort_by="created_at", sort_order=-1, limit=50)


# ---------------------------------------------------------------------------
# vector_search tests
# ---------------------------------------------------------------------------

class TestVectorSearch:
    """Tests for vector_search: runs MongoDB Atlas Vector Search."""

    def test_builds_correct_pipeline(self):
        """Should build a pipeline with $vectorSearch and $addFields stages."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.vector_search("claims", [0.1, 0.2, 0.3], "claims_index")
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0]["$vectorSearch"]["index"] == "claims_index"
            assert pipeline[0]["$vectorSearch"]["queryVector"] == [0.1, 0.2, 0.3]
            assert "$addFields" in pipeline[1]

    def test_with_filter(self):
        """Should add filter to $vectorSearch stage when provided."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.return_value = []

        with patch.object(mc, "get_db", return_value=mock_db):
            mc.vector_search("claims", [0.1], "idx", filter_query={"topic": "pricing"})
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0]["$vectorSearch"]["filter"] == {"topic": "pricing"}

    def test_returns_empty_when_db_none(self):
        """Should return empty list when database is unavailable."""
        with patch.object(mc, "get_db", return_value=None):
            result = mc.vector_search("claims", [0.1], "idx")
            assert result == []

    def test_handles_exception(self):
        """Should catch exceptions and return empty list."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.aggregate.side_effect = Exception("search error")

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.vector_search("claims", [0.1], "idx")
            assert result == []


# ---------------------------------------------------------------------------
# search_sessions tests
# ---------------------------------------------------------------------------

class TestSearchSessions:
    """Tests for search_sessions: searches sessions with optional filters."""

    def test_no_filters(self):
        """Should delegate to find_many with empty query when no filters given."""
        with patch.object(mc, "find_many", return_value=[]) as mock:
            result = mc.search_sessions()
            mock.assert_called_once_with(
                "sessions", query={}, sort_by="created_at", sort_order=-1, limit=20
            )
            assert result == []

    def test_session_type_filter(self):
        """Should build a case-insensitive regex query on metadata.session_type."""
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.search_sessions(session_type="Investor")
            mock.assert_called_once_with(
                "sessions",
                query={"metadata.session_type": {"$regex": "Investor", "$options": "i"}},
                sort_by="created_at",
                sort_order=-1,
                limit=20,
            )

    def test_date_range_filter(self):
        """Should include session_date query with $gte and $lte when both dates given."""
        with patch.object(mc, "find_many", return_value=[]) as mock:
            mc.search_sessions(date_from="2026-01-01", date_to="2026-03-01")
            mock.assert_called_once_with(
                "sessions",
                query={"session_date": {"$gte": "2026-01-01", "$lte": "2026-03-01"}},
                sort_by="created_at",
                sort_order=-1,
                limit=20,
            )


# ---------------------------------------------------------------------------
# get_session_claims tests
# ---------------------------------------------------------------------------

class TestGetSessionClaims:
    """Tests for get_session_claims: retrieves claims for specific session IDs."""

    def test_with_session_ids(self):
        """Should build $in query and delegate to find_many."""
        with patch.object(mc, "find_many", return_value=[{"claim": "c1"}]) as mock:
            result = mc.get_session_claims(["id1", "id2"])
            mock.assert_called_once_with(
                "claims",
                query={"session_id": {"$in": ["id1", "id2"]}},
                sort_by="created_at",
                sort_order=-1,
                limit=100,
            )
            assert result == [{"claim": "c1"}]

    def test_empty_list_returns_empty(self):
        """Should return empty list without calling find_many when session_ids is empty."""
        with patch.object(mc, "find_many", return_value=[]) as mock:
            result = mc.get_session_claims([])
            mock.assert_not_called()
            assert result == []


# ---------------------------------------------------------------------------
# delete_many tests
# ---------------------------------------------------------------------------

class TestDeleteMany:
    """Tests for delete_many: deletes all matching documents."""

    def test_returns_count_on_success(self):
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.delete_many.return_value = MagicMock(deleted_count=5)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.delete_many("claims", {"session_id": "s1"})
            assert result == 5
            mock_collection.delete_many.assert_called_once_with({"session_id": "s1"})

    def test_returns_zero_when_db_none(self):
        with patch.object(mc, "get_db", return_value=None):
            result = mc.delete_many("claims", {"session_id": "s1"})
            assert result == 0

    def test_returns_zero_on_exception(self):
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.delete_many.side_effect = Exception("fail")
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.delete_many("claims", {})
            assert result == 0


# ---------------------------------------------------------------------------
# get_latest_session tests
# ---------------------------------------------------------------------------

class TestGetLatestSession:
    """Tests for get_latest_session: retrieves the most recent session."""

    def test_returns_session(self):
        mock_db = MagicMock()
        mock_sessions = MagicMock()
        mock_sessions.find_one.return_value = {"_id": "s1", "created_at": "2026-03-01"}
        mock_db.__getitem__ = MagicMock(return_value=mock_sessions)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.get_latest_session()
            assert result["_id"] == "s1"
            mock_sessions.find_one.assert_called_once_with(sort=[("created_at", -1)])

    def test_returns_none_when_db_none(self):
        with patch.object(mc, "get_db", return_value=None):
            result = mc.get_latest_session()
            assert result is None

    def test_returns_none_on_exception(self):
        mock_db = MagicMock()
        mock_sessions = MagicMock()
        mock_sessions.find_one.side_effect = Exception("fail")
        mock_db.__getitem__ = MagicMock(return_value=mock_sessions)

        with patch.object(mc, "get_db", return_value=mock_db):
            result = mc.get_latest_session()
            assert result is None
