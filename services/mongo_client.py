"""
MongoDB client for Startup Brain.
Uses @st.cache_resource for connection pooling.
Gracefully degrades if MongoDB is unavailable.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

try:
    from pymongo import MongoClient, ASCENDING
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
]


@st.cache_resource
def get_mongo_client() -> Optional[object]:
    """
    Returns a cached MongoDB client, or None if unavailable.
    Tries st.secrets first, then os.environ fallback.
    """
    if not PYMONGO_AVAILABLE:
        st.warning("pymongo not installed — MongoDB features disabled.")
        return None

    uri = None
    try:
        uri = st.secrets["MONGODB_URI"]
    except (KeyError, AttributeError, FileNotFoundError):
        uri = os.environ.get("MONGODB_URI")

    if not uri:
        st.warning("MONGODB_URI not configured — MongoDB features disabled.")
        return None

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Verify connection
        client.admin.command("ping")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        st.warning(f"MongoDB connection failed: {e} — MongoDB features disabled.")
        return None
    except Exception as e:
        st.warning(f"Unexpected MongoDB error: {e} — MongoDB features disabled.")
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
        st.warning(f"MongoDB insert failed ({collection_name}): {e}")
        return None


def find_many(
    collection_name: str,
    query: dict = None,
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
        st.warning(f"MongoDB find failed ({collection_name}): {e}")
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
        st.warning(f"MongoDB find_one failed ({collection_name}): {e}")
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
        if "$set" in update:
            update["$set"]["updated_at"] = datetime.now(timezone.utc)
        else:
            update["$set"] = {"updated_at": datetime.now(timezone.utc)}
        db[collection_name].update_one(query, update, upsert=upsert)
        return True
    except Exception as e:
        st.warning(f"MongoDB update failed ({collection_name}): {e}")
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
        st.warning(f"MongoDB delete failed ({collection_name}): {e}")
        return False


# ---------------------------------------------------------------------------
# Collection-specific helpers
# ---------------------------------------------------------------------------

def insert_session(session_doc: dict) -> Optional[str]:
    """Store a raw transcript session. Returns inserted id."""
    return insert_one("sessions", session_doc)


def get_sessions(limit: int = 50) -> list:
    """Retrieve recent sessions, newest first."""
    return find_many("sessions", sort_by="created_at", sort_order=-1, limit=limit)


def insert_claim(claim_doc: dict) -> Optional[str]:
    """Store a single confirmed claim. Returns inserted id."""
    return insert_one("claims", claim_doc)


def get_claims(session_id: str = None, limit: int = 200) -> list:
    """Retrieve claims, optionally filtered by session_id."""
    query = {"session_id": session_id} if session_id else {}
    return find_many("claims", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def insert_whiteboard_extraction(doc: dict) -> Optional[str]:
    """Store a whiteboard extraction result."""
    return insert_one("whiteboard_extractions", doc)


def insert_feedback(feedback_doc: dict) -> Optional[str]:
    """Store investor/customer feedback."""
    return insert_one("feedback", feedback_doc)


def get_feedback(source_type: str = None, limit: int = 100) -> list:
    """Retrieve feedback entries, optionally filtered by source_type."""
    query = {"source_type": source_type} if source_type else {}
    return find_many("feedback", query=query, sort_by="created_at", sort_order=-1, limit=limit)


def insert_book_framework(doc: dict) -> Optional[str]:
    """Store a book framework summary."""
    return insert_one("book_frameworks", doc)


def get_book_frameworks() -> list:
    """Retrieve all book framework summaries."""
    return find_many("book_frameworks", sort_by="created_at", sort_order=1, limit=20)


def upsert_living_document(content: str, metadata: dict = None) -> bool:
    """
    Upsert the living document mirror in MongoDB.
    There is only ever one living document.
    """
    update = {
        "$set": {
            "content": content,
            "metadata": metadata or {},
        }
    }
    return update_one("living_document", {"_id": "startup_brain"}, update, upsert=True)


def get_living_document() -> Optional[dict]:
    """Retrieve the living document mirror from MongoDB."""
    return find_one("living_document", {"_id": "startup_brain"})


def log_cost(cost_doc: dict) -> Optional[str]:
    """Log an API cost event."""
    return insert_one("cost_log", cost_doc)


def get_cost_log(limit: int = 500) -> list:
    """Retrieve cost log entries, newest first."""
    return find_many("cost_log", sort_by="created_at", sort_order=-1, limit=limit)


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
    filter_query: dict = None,
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
        st.warning(f"Vector search failed ({collection_name}): {e}")
        return []
