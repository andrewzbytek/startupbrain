"""
MongoDB client for Startup Brain.
Uses @st.cache_resource for connection pooling.
Gracefully degrades if MongoDB is unavailable.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

DB_NAME = "startup_brain"
COLLECTIONS = [
    "sessions",
    "claims",
    "whiteboard_extractions",
    "feedback",
    "book_frameworks",
    "living_document",
    "cost_log",
    "pending_ingestion",
]


@st.cache_resource(ttl=300)
def get_mongo_client() -> Optional[object]:
    """
    Returns a cached MongoDB client, or None if unavailable.
    Tries st.secrets first, then os.environ fallback.
    """
    if not PYMONGO_AVAILABLE:
        logging.warning("pymongo not installed — MongoDB features disabled.")
        return None

    uri = None
    try:
        uri = st.secrets["MONGODB_URI"]
    except (KeyError, AttributeError, FileNotFoundError):
        uri = os.environ.get("MONGODB_URI")

    if not uri:
        logging.warning("MONGODB_URI not configured — MongoDB features disabled.")
        return None

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Verify connection
        client.admin.command("ping")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logging.error("MongoDB connection failed: %s", e)
        logging.warning("MongoDB connection failed — MongoDB features disabled.")
        return None
    except Exception as e:
        logging.error("Unexpected MongoDB error: %s", e)
        logging.warning("MongoDB connection error — MongoDB features disabled.")
        return None


def get_db():
    """Returns the startup_brain database, or None if unavailable."""
    client = get_mongo_client()
    if client is None:
        return None
    return client[DB_NAME]


def is_mongo_available() -> bool:
    """Health check — returns True if MongoDB is reachable."""
    return get_mongo_client() is not None


# ---------------------------------------------------------------------------
# Generic CRUD helpers
# ---------------------------------------------------------------------------

def insert_one(collection_name: str, document: dict) -> Optional[str]:
    """
    Insert a document into a collection.
    Automatically adds created_at timestamp.
    Returns the inserted _id as string, or None on failure.
    """
    db = get_db()
    if db is None:
        return None
    try:
        document = {**document, "created_at": datetime.now(timezone.utc)}
        result = db[collection_name].insert_one(document)
        return str(result.inserted_id)
    except Exception as e:
        logging.error("MongoDB insert failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return None


def find_many(
    collection_name: str,
    query: dict | None = None,
    sort_by: str = "created_at",
    sort_order: int = -1,
    limit: int = 100,
) -> list:
    """
    Find documents matching query.
    Returns list of documents, or empty list on failure.
    """
    db = get_db()
    if db is None:
        return []
    try:
        cursor = (
            db[collection_name]
            .find(query or {})
            .sort(sort_by, sort_order)
            .limit(limit)
        )
        return list(cursor)
    except Exception as e:
        logging.error("MongoDB find failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return []


def find_one(collection_name: str, query: dict) -> Optional[dict]:
    """
    Find a single document matching query.
    Returns document dict or None.
    """
    db = get_db()
    if db is None:
        return None
    try:
        return db[collection_name].find_one(query)
    except Exception as e:
        logging.error("MongoDB find_one failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return None


def update_one(
    collection_name: str,
    query: dict,
    update: dict,
    upsert: bool = False,
) -> bool:
    """
    Update a single document.
    Automatically adds updated_at timestamp.
    Returns True on success, False on failure.
    """
    db = get_db()
    if db is None:
        return False
    try:
        # Shallow-copy to avoid mutating caller's dict
        update = {**update}
        if "$set" in update:
            update["$set"] = {**update["$set"], "updated_at": datetime.now(timezone.utc)}
        else:
            update["$set"] = {"updated_at": datetime.now(timezone.utc)}
        result = db[collection_name].update_one(query, update, upsert=upsert)
        if upsert:
            return result.modified_count > 0 or result.upserted_id is not None
        return result.modified_count > 0
    except Exception as e:
        logging.error("MongoDB update failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return False


def delete_one(collection_name: str, query: dict) -> bool:
    """Delete a single document. Returns True on success."""
    db = get_db()
    if db is None:
        return False
    try:
        db[collection_name].delete_one(query)
        return True
    except Exception as e:
        logging.error("MongoDB delete failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return False


def delete_many(collection_name: str, query: dict) -> int:
    """Delete all matching documents. Returns count deleted."""
    db = get_db()
    if db is None:
        return 0
    try:
        result = db[collection_name].delete_many(query)
        return result.deleted_count
    except Exception as e:
        logging.error("MongoDB delete_many failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return 0


def get_latest_session(brain: str = "") -> Optional[dict]:
    """Get the most recently created session (sort by created_at desc).
    If brain is specified, only considers sessions for that brain.
    """
    db = get_db()
    if db is None:
        return None
    try:
        query = {}
        if brain:
            query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
        return db["sessions"].find_one(query, sort=[("created_at", -1)])
    except Exception as e:
        logging.error("MongoDB get_latest_session failed: %s", e)
        logging.warning("Database operation failed. Please try again.")
        return None


# ---------------------------------------------------------------------------
# Collection-specific helpers
# ---------------------------------------------------------------------------

def insert_session(session_doc: dict, brain: str = "pitch") -> Optional[str]:
    """Store a raw transcript session. Returns inserted id."""
    return insert_one("sessions", {**session_doc, "brain": brain})


def get_sessions(limit: int = 50, brain: str = "") -> list:
    """Retrieve recent sessions, newest first."""
    query = {}
    if brain:
        query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
    return find_many("sessions", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def insert_claim(claim_doc: dict, brain: str = "pitch") -> Optional[str]:
    """Store a single confirmed claim. Returns inserted id."""
    return insert_one("claims", {**claim_doc, "brain": brain})


def get_claims(session_id: str | None = None, limit: int = 200, brain: str = "") -> list:
    """Retrieve claims, optionally filtered by session_id and/or brain."""
    query = {}
    if session_id:
        query["session_id"] = session_id
    if brain:
        query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
    return find_many("claims", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def insert_whiteboard_extraction(doc: dict) -> Optional[str]:
    """Store a whiteboard extraction result."""
    return insert_one("whiteboard_extractions", doc)


def insert_feedback(feedback_doc: dict, brain: str = "") -> Optional[str]:
    """Store investor/customer feedback."""
    if brain:
        feedback_doc = {**feedback_doc, "brain": brain}
    return insert_one("feedback", feedback_doc)


def get_feedback(source_type: str | None = None, limit: int = 100, brain: str = "") -> list:
    """Retrieve feedback entries, optionally filtered by source_type and/or brain."""
    query = {"source_type": source_type} if source_type else {}
    if brain:
        query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
    return find_many("feedback", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def insert_book_framework(doc: dict) -> Optional[str]:
    """Store a book framework summary."""
    return insert_one("book_frameworks", doc)


def get_book_frameworks() -> list:
    """Retrieve all book framework summaries."""
    return find_many("book_frameworks", sort_by="created_at", sort_order=1, limit=20)


def upsert_living_document(content: str, metadata: dict | None = None, brain: str = "pitch") -> bool:
    """
    Upsert the living document mirror in MongoDB.
    There is only ever one living document per brain.
    """
    update = {
        "$set": {
            "content": content,
            "metadata": metadata or {},
        }
    }
    return update_one("living_document", {"_id": f"{brain}_brain"}, update, upsert=True)


def get_living_document(brain: str = "pitch") -> Optional[dict]:
    """Retrieve the living document mirror from MongoDB."""
    return find_one("living_document", {"_id": f"{brain}_brain"})


def log_cost(cost_doc: dict) -> Optional[str]:
    """Log an API cost event."""
    return insert_one("cost_log", cost_doc)


def get_cost_log(limit: int = 500) -> list:
    """Retrieve cost log entries, newest first."""
    return find_many("cost_log", sort_by="created_at", sort_order=-1, limit=limit)


def get_hypotheses(status=None, limit=50, brain: str = "") -> list:
    """Retrieve hypothesis claims, optionally filtered by status and/or brain."""
    query = {"claim_type": "hypothesis"}
    if status:
        query["status"] = status
    if brain:
        query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
    return find_many("claims", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def update_hypothesis_status(claim_text_fragment, new_status):
    """Update the status of a hypothesis claim by text fragment match."""
    import re
    db = get_db()
    if db is None:
        return False
    try:
        escaped = re.escape(claim_text_fragment)
        result = db["claims"].update_one(
            {"claim_type": "hypothesis", "brain": "ops", "claim_text": {"$regex": escaped, "$options": "i"}},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count > 0
    except Exception as e:
        logging.error("update_hypothesis_status failed: %s", e)
        return False


def search_sessions(
    session_type: str | None = None,
    participant: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    brain: str = "",
) -> list:
    """
    Search sessions with optional filters, all ANDed together.
    Returns list of session documents, newest first.
    """
    import re as _re

    query = {}
    if brain:
        query["$or"] = [{"brain": brain}, {"brain": {"$exists": False}}]
    if session_type:
        query["metadata.session_type"] = {"$regex": _re.escape(session_type), "$options": "i"}
    if participant:
        query["metadata.participants"] = {"$regex": _re.escape(participant), "$options": "i"}
    date_query = {}
    if date_from:
        date_query["$gte"] = date_from
    if date_to:
        date_query["$lte"] = date_to
    if date_query:
        query["session_date"] = date_query
    return find_many("sessions", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def get_session_claims(session_ids: list, limit: int = 100) -> list:
    """
    Get claims for specific session IDs.
    Returns empty list if session_ids is empty.
    """
    if not session_ids:
        return []
    return find_many(
        "claims",
        query={"session_id": {"$in": session_ids}},
        sort_by="created_at",
        sort_order=-1,
        limit=limit,
    )


def upsert_pending_ingestion(doc: dict) -> bool:
    """Upsert the pending ingestion checkpoint. Uses fixed _id='pending'."""
    update = {"$set": {k: v for k, v in doc.items() if k != "_id"}}
    return update_one("pending_ingestion", {"_id": "pending"}, update, upsert=True)


def get_pending_ingestion() -> Optional[dict]:
    """Retrieve the pending ingestion checkpoint, or None if none exists."""
    return find_one("pending_ingestion", {"_id": "pending"})


def delete_pending_ingestion() -> bool:
    """Delete the pending ingestion checkpoint."""
    return delete_one("pending_ingestion", {"_id": "pending"})


def count_documents(collection_name: str, query: dict | None = None) -> int:
    """Count documents in a collection. Returns 0 on failure."""
    db = get_db()
    if db is None:
        return 0
    try:
        return db[collection_name].count_documents(query or {})
    except Exception as e:
        logging.error("MongoDB count failed (%s): %s", collection_name, e)
        return 0


# ---------------------------------------------------------------------------
# Vector search helper
# ---------------------------------------------------------------------------

def vector_search(
    collection_name: str,
    query_vector: list,
    index_name: str,
    path: str = "embedding",
    num_candidates: int = 50,
    limit: int = 5,
    filter_query: dict | None = None,
) -> list:
    """
    Run a MongoDB Atlas Vector Search query.
    Requires an Atlas Vector Search index to be configured via the Atlas UI.

    Args:
        collection_name: MongoDB collection to search.
        query_vector: The embedding vector for the query.
        index_name: Name of the Atlas Vector Search index.
        path: Field name containing the embeddings.
        num_candidates: Number of ANN candidates to consider.
        limit: Maximum results to return.
        filter_query: Optional pre-filter for the search.

    Returns:
        List of matching documents with scores, or empty list on failure.
    """
    db = get_db()
    if db is None:
        return []

    vector_search_stage = {
        "$vectorSearch": {
            "index": index_name,
            "path": path,
            "queryVector": query_vector,
            "numCandidates": num_candidates,
            "limit": limit,
        }
    }
    if filter_query:
        vector_search_stage["$vectorSearch"]["filter"] = filter_query

    pipeline = [
        vector_search_stage,
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
    ]

    try:
        return list(db[collection_name].aggregate(pipeline))
    except Exception as e:
        logging.error("Vector search failed (%s): %s", collection_name, e)
        logging.warning("Database operation failed. Please try again.")
        return []


def vector_search_text(
    collection_name: str,
    query_text: str,
    index_name: str,
    path: str = "claim_text",
    limit: int = 5,
    filter_query: dict | None = None,
) -> list:
    """
    Run MongoDB Atlas Vector Search with automated embedding (queryString).
    Atlas automatically generates embeddings using the configured Voyage AI model.
    No API key or code-side embedding needed.

    Args:
        collection_name: MongoDB collection to search.
        query_text: Plain text query — Atlas embeds it automatically.
        index_name: Name of the Atlas Vector Search index.
        path: Field containing the auto-generated embeddings.
        limit: Maximum results to return.
        filter_query: Optional pre-filter for the search.

    Returns:
        List of matching documents with scores, or empty list on failure.
    """
    db = get_db()
    if db is None:
        return []

    stage = {
        "$vectorSearch": {
            "index": index_name,
            "queryString": query_text,
            "path": path,
            "numCandidates": limit * 10,
            "limit": limit,
        }
    }
    if filter_query:
        stage["$vectorSearch"]["filter"] = filter_query

    pipeline = [
        stage,
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
    ]

    try:
        return list(db[collection_name].aggregate(pipeline))
    except Exception as e:
        logging.error("Vector text search failed (%s): %s", collection_name, e)
        return []
