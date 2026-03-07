"""
MongoDB-based ingestion lock for Startup Brain.
Ensures only one user can run ingestion at a time.
Stale locks auto-expire after 30 minutes.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

try:
    from pymongo import ReturnDocument
except ImportError:
    ReturnDocument = None  # pymongo unavailable — lock functions return early


# Lock expires after 30 minutes (handles browser close / crash)
LOCK_TIMEOUT_MINUTES = 30


def _get_lock_collection():
    """Get the MongoDB collection for locks. Returns None if unavailable."""
    try:
        from services.mongo_client import get_db
        db = get_db()
        if db is None:
            return None
        return db["locks"]
    except Exception:
        return None


def acquire_lock(session_id: Optional[str] = None) -> dict:
    """
    Try to acquire the ingestion lock atomically.

    Args:
        session_id: Unique identifier for this browser session.

    Returns:
        dict with keys: acquired (bool), locked_by (str or None), message (str)
    """
    collection = _get_lock_collection()
    if collection is None:
        # MongoDB unavailable — allow ingestion (single-user fallback)
        return {"acquired": True, "locked_by": None, "message": "No MongoDB — lock skipped"}

    if not session_id:
        session_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(minutes=LOCK_TIMEOUT_MINUTES)

    try:
        # Atomic: acquire if unlocked OR if lock is stale
        result = collection.find_one_and_update(
            {
                "_id": "ingestion_lock",
                "$or": [
                    {"locked": False},
                    {"locked_at": {"$lt": stale_threshold}},
                ],
            },
            {
                "$set": {
                    "locked": True,
                    "locked_at": now,
                    "session_id": session_id,
                }
            },
            upsert=False,
            return_document=ReturnDocument.AFTER,
        )

        if result is not None:
            return {"acquired": True, "locked_by": session_id, "message": "Lock acquired"}

        # Lock exists and is held — check if it's our own session
        existing = collection.find_one({"_id": "ingestion_lock"})
        if existing is None:
            # Lock document doesn't exist yet — create it
            try:
                collection.insert_one({
                    "_id": "ingestion_lock",
                    "locked": True,
                    "locked_at": now,
                    "session_id": session_id,
                })
                return {"acquired": True, "locked_by": session_id, "message": "Lock created and acquired"}
            except Exception:
                # Race condition: another session just created it
                return {"acquired": False, "locked_by": None, "message": "Lock contention — try again"}

        if existing.get("session_id") == session_id:
            # We already hold the lock — refresh it atomically (verify ownership)
            refresh = collection.find_one_and_update(
                {"_id": "ingestion_lock", "session_id": session_id},
                {"$set": {"locked_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if refresh is not None:
                return {"acquired": True, "locked_by": session_id, "message": "Lock refreshed (same session)"}
            # Lock was stolen between check and refresh
            return {"acquired": False, "locked_by": None, "message": "Lock ownership changed — try again"}

        return {
            "acquired": False,
            "locked_by": existing.get("session_id"),
            "message": "Ingestion in progress by another session",
        }

    except Exception as e:
        # MongoDB error — fail closed to protect concurrent safety
        logging.error("Ingestion lock acquisition failed: %s", e)
        return {"acquired": False, "locked_by": None, "message": "Lock check failed — denying ingestion for safety"}


def release_lock(session_id: Optional[str] = None) -> bool:
    """
    Release the ingestion lock.

    Args:
        session_id: If provided, only release if held by this session.

    Returns:
        True if lock was released, False otherwise.
    """
    collection = _get_lock_collection()
    if collection is None:
        return True

    try:
        query = {"_id": "ingestion_lock"}
        if session_id:
            query["session_id"] = session_id

        result = collection.update_one(
            query,
            {"$set": {"locked": False, "session_id": None}},
        )
        return result.modified_count > 0
    except Exception as e:
        logging.error("release_lock failed — ingestion lock may remain held for up to %d min: %s",
                      LOCK_TIMEOUT_MINUTES, e)
        return False


def check_lock() -> dict:
    """
    Check current lock status without modifying it.

    Returns:
        dict with keys: locked (bool), session_id (str or None), stale (bool)
    """
    collection = _get_lock_collection()
    if collection is None:
        return {"locked": False, "session_id": None, "stale": False}

    try:
        doc = collection.find_one({"_id": "ingestion_lock"})
        if doc is None:
            return {"locked": False, "session_id": None, "stale": False}

        locked = doc.get("locked", False)
        if not locked:
            return {"locked": False, "session_id": None, "stale": False}

        # Check if stale
        locked_at = doc.get("locked_at")
        stale = False
        if locked_at:
            if locked_at.tzinfo is None:
                locked_at = locked_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            stale = (now - locked_at) > timedelta(minutes=LOCK_TIMEOUT_MINUTES)

        return {
            "locked": True,
            "session_id": doc.get("session_id"),
            "stale": stale,
        }
    except Exception:
        return {"locked": False, "session_id": None, "stale": False}


def ensure_lock_document():
    """Create the lock document if it doesn't exist. Called once at startup."""
    collection = _get_lock_collection()
    if collection is None:
        return
    try:
        collection.update_one(
            {"_id": "ingestion_lock"},
            {"$setOnInsert": {"locked": False, "locked_at": None, "session_id": None}},
            upsert=True,
        )
    except Exception as e:
        logging.warning("ensure_lock_document failed — first-use race condition possible: %s", e)


def ensure_doc_write_lock():
    """Create the doc_write_lock document if it doesn't exist. Called once at startup."""
    collection = _get_lock_collection()
    if collection is None:
        return
    try:
        collection.update_one(
            {"_id": "doc_write_lock"},
            {"$setOnInsert": {"locked": False, "locked_at": None, "session_id": None}},
            upsert=True,
        )
    except Exception as e:
        logging.warning("ensure_doc_write_lock failed — first-use race condition possible: %s", e)


# ---------------------------------------------------------------------------
# Document write lock — short-lived lock protecting the living document
# from concurrent read-modify-write cycles (chat corrections, feedback, etc.)
# ---------------------------------------------------------------------------

DOC_LOCK_TIMEOUT_SECONDS = 120  # 2 minutes — LLM diff+verify can take ~60s


def acquire_doc_lock(timeout_seconds: int = 30) -> Optional[str]:
    """
    Acquire a short-lived lock on the living document.
    Blocks (polls) up to timeout_seconds.

    Returns:
        A lock_id string (truthy) if acquired, None (falsy) if not.
        Pass the returned lock_id to release_doc_lock() to release.
    """
    import time

    lock_id = str(uuid.uuid4())

    collection = _get_lock_collection()
    if collection is None:
        return lock_id  # No MongoDB — allow write

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            now = datetime.now(timezone.utc)
            stale_threshold = now - timedelta(seconds=DOC_LOCK_TIMEOUT_SECONDS)

            result = collection.find_one_and_update(
                {
                    "_id": "doc_write_lock",
                    "$or": [
                        {"locked": False},
                        {"locked_at": {"$lt": stale_threshold}},
                    ],
                },
                {"$set": {"locked": True, "locked_at": now, "session_id": lock_id}},
                upsert=False,
                return_document=ReturnDocument.AFTER,
            )

            if result is not None:
                return lock_id

            # Lock document may not exist yet
            existing = collection.find_one({"_id": "doc_write_lock"})
            if existing is None:
                try:
                    collection.insert_one({
                        "_id": "doc_write_lock",
                        "locked": True,
                        "locked_at": now,
                        "session_id": lock_id,
                    })
                    return lock_id
                except Exception:
                    pass  # Another process just created it — retry
        except Exception as _e:
            logging.debug("acquire_doc_lock transient error (will retry): %s", _e)

        time.sleep(1)

    return None


def release_doc_lock(lock_id: Optional[str] = None) -> None:
    """Release the document write lock, verifying ownership if lock_id provided."""
    collection = _get_lock_collection()
    if collection is None:
        return
    try:
        query = {"_id": "doc_write_lock"}
        if lock_id:
            query["session_id"] = lock_id
        collection.update_one(
            query,
            {"$set": {"locked": False, "session_id": None}},
        )
    except Exception as e:
        logging.error("release_doc_lock failed — lock may remain held for up to %ds: %s",
                      DOC_LOCK_TIMEOUT_SECONDS, e)
