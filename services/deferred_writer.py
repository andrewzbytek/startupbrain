"""
Deferred writes for the ingestion pipeline.
Runs LLM calls eagerly but defers all disk/MongoDB/git writes
until batch_commit() at the very end of the pipeline.

Checkpoints pipeline state to MongoDB so crashes are recoverable.
"""

import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional


class DeferredWriter:
    """
    Holds an in-memory copy of the living document, accumulates changes,
    and writes everything in a single batch at pipeline completion.
    """

    def __init__(self):
        self.original_doc = ""
        self.in_memory_doc = ""
        self.transcript = ""
        self.confirmed_claims = []
        self.metadata = {}
        self.session_summary = ""
        self.topic_tags = []
        self.session_type = ""
        self.consistency_results = None
        self.contradiction_resolutions = []
        self.stage = "initialized"
        self.pipeline_result = {}
        self.lock_session_id = None  # Ties checkpoint to the session that created it
        self.brain = "pitch"

    def initialize(
        self,
        transcript: str,
        confirmed_claims: list,
        metadata: dict = None,
        session_summary: str = "",
        topic_tags: list = None,
        session_type: str = "",
        brain: str = "pitch",
    ):
        """Snapshot the living document and store pipeline inputs."""
        from services.document_updater import read_living_document

        doc = read_living_document(brain=brain)
        self.original_doc = doc
        self.in_memory_doc = doc
        self.transcript = transcript
        self.confirmed_claims = list(confirmed_claims)
        self.metadata = metadata or {}
        self.session_summary = session_summary
        self.topic_tags = topic_tags or []
        self.session_type = session_type
        self.brain = brain
        self.stage = "initialized"

    def apply_document_update_deferred(self, new_info: str, update_reason: str = "") -> dict:
        """
        Run generate_diff / verify_diff / apply_diff against in_memory_doc.
        LLM calls execute immediately but NO file/MongoDB/git writes happen.

        Returns dict with: success (bool), message (str), changes_applied (int)
        """
        from services.document_updater import (
            generate_diff, verify_diff, parse_diff_output, apply_diff,
        )

        if not self.in_memory_doc:
            return {"success": False, "message": "No document loaded.", "changes_applied": 0}

        max_retries = 2
        diff_output = generate_diff(self.in_memory_doc, new_info, update_reason, brain=self.brain)
        verification_feedback = ""

        for attempt in range(max_retries + 1):
            if verification_feedback and attempt > 0:
                retry_info = f"{new_info}\n\nPrevious verification failed with issues:\n{verification_feedback}"
                diff_output = generate_diff(self.in_memory_doc, retry_info, update_reason, brain=self.brain)

            verification = verify_diff(self.in_memory_doc, diff_output, new_info, brain=self.brain)

            if verification["verified"]:
                break

            verification_feedback = "\n".join(verification["issues"])
            if attempt == max_retries:
                return {
                    "success": False,
                    "message": f"Diff verification failed after {max_retries + 1} attempts: {verification_feedback}",
                    "changes_applied": 0,
                }

        diff_blocks = parse_diff_output(diff_output)
        if not diff_blocks:
            return {"success": True, "message": "No changes needed — information already present.", "changes_applied": 0}

        self.in_memory_doc = apply_diff(self.in_memory_doc, diff_blocks, brain=self.brain)
        self._changes_applied = len(diff_blocks)

        return {
            "success": True,
            "message": f"{len(diff_blocks)} change(s) applied to in-memory document.",
            "changes_applied": len(diff_blocks),
        }

    def apply_decision_log_deferred(self, entry: str):
        """Add a Decision Log entry to the in-memory document."""
        from services.document_updater import _add_decision
        self.in_memory_doc = _add_decision(self.in_memory_doc, entry, brain=self.brain)

    def apply_dismissed_deferred(self, entry: str):
        """Add a Dismissed Contradictions entry to the in-memory document."""
        from services.document_updater import _add_dismissed
        self.in_memory_doc = _add_dismissed(self.in_memory_doc, entry, brain=self.brain)

    def record_contradiction_resolution(self, idx: int, action: str, new_claim: str, explanation: str):
        """Record a contradiction resolution for the checkpoint."""
        self.contradiction_resolutions.append({
            "index": idx,
            "action": action,
            "new_claim": new_claim,
            "explanation": explanation,
        })

    def save_checkpoint(self):
        """Persist current pipeline state to MongoDB pending_ingestion collection."""
        from services.mongo_client import upsert_pending_ingestion
        upsert_pending_ingestion(self.to_checkpoint())

    def batch_commit(self) -> dict:
        """
        Write everything in a single batch:
        1. Write living document to disk
        2. Mirror to MongoDB
        3. Single git commit
        4. Store session + claims in MongoDB
        5. Delete checkpoint

        Returns dict with: success (bool), message (str), claims_stored (int), session_id (str)
        """
        from services.document_updater import write_living_document, _git_commit
        from services.mongo_client import upsert_living_document, delete_pending_ingestion
        from services.ingestion import store_session, store_confirmed_claims
        from services.ingestion_lock import acquire_doc_lock, release_doc_lock

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc_changed = self.in_memory_doc != self.original_doc

        try:
            # 1. Write file (only if changed) — acquire doc lock to prevent clobbering
            if doc_changed:
                if not acquire_doc_lock(timeout_seconds=60):
                    # Still store session + claims even if doc can't be updated
                    session_id_result = None
                    claims_stored_count = 0
                    try:
                        session_id_result = store_session(
                            self.transcript,
                            metadata=self.metadata,
                            session_summary=self.session_summary,
                            topic_tags=self.topic_tags,
                            brain=self.brain,
                        )
                        if session_id_result:
                            inserted = store_confirmed_claims(
                                self.confirmed_claims, session_id_result,
                                metadata=self.metadata, brain=self.brain,
                            )
                            claims_stored_count = len(inserted) if inserted else 0
                    except Exception as store_err:
                        logging.error("Failed to store session/claims on doc-lock failure: %s", store_err)
                    try:
                        delete_pending_ingestion()
                    except Exception as cleanup_err:
                        logging.warning("Could not delete checkpoint after doc-lock failure: %s", cleanup_err)
                    return {
                        "success": False,
                        "message": "Document lock unavailable — session and claims stored but document not updated. Try again later.",
                        "claims_stored": claims_stored_count,
                        "session_id": session_id_result or "",
                        "document_updated": False,
                        "changes_applied": 0,
                    }
                try:
                    write_living_document(self.in_memory_doc, brain=self.brain)

                    # 2. Mirror to MongoDB
                    update_reason = self._build_update_reason()
                    upsert_living_document(
                        self.in_memory_doc,
                        metadata={"last_updated": date_str, "update_reason": update_reason},
                        brain=self.brain,
                    )

                    # 3. Single git commit
                    brain_label = "pitch_brain.md" if self.brain == "pitch" else "ops_brain.md"
                    commit_msg = f"Update {brain_label}: {self._build_update_reason()} ({date_str})"
                    _git_commit(commit_msg, brain=self.brain)
                finally:
                    release_doc_lock()

            # 4. Store session
            session_id = store_session(
                self.transcript,
                metadata=self.metadata,
                session_summary=self.session_summary,
                topic_tags=self.topic_tags,
                brain=self.brain,
            )

            # 5. Store claims
            claims_stored = 0
            if session_id:
                inserted = store_confirmed_claims(
                    self.confirmed_claims, session_id, metadata=self.metadata,
                    brain=self.brain,
                )
                claims_stored = len(inserted)

            # 6. Delete checkpoint
            delete_pending_ingestion()

            return {
                "success": True,
                "message": "Batch commit complete.",
                "claims_stored": claims_stored,
                "session_id": session_id or "",
                "document_updated": doc_changed,
                "changes_applied": getattr(self, '_changes_applied', 0) if doc_changed else 0,
            }

        except Exception as e:
            logging.error("batch_commit failed: %s", e)
            return {
                "success": False,
                "message": f"Batch commit failed: {e}",
                "claims_stored": 0,
                "session_id": "",
                "document_updated": False,
                "changes_applied": 0,
            }

    def rollback(self):
        """Discard all in-memory changes and delete the checkpoint."""
        from services.mongo_client import delete_pending_ingestion
        self.in_memory_doc = self.original_doc
        self.contradiction_resolutions = []
        delete_pending_ingestion()

    def _build_update_reason(self) -> str:
        """Build an update reason string from metadata."""
        date_str = self.metadata.get(
            "session_date",
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        if self.session_type:
            reason = f"{self.session_type} — {date_str}"
        else:
            reason = f"Session {date_str}"
        participants = self.metadata.get("participants", "")
        if participants:
            reason += f" ({participants})"
        return reason

    def to_checkpoint(self) -> dict:
        """Serialize to a dict for MongoDB storage."""
        return {
            "_id": "pending",
            "original_doc": self.original_doc,
            "in_memory_doc": self.in_memory_doc,
            "transcript": self.transcript,
            "confirmed_claims": self.confirmed_claims,
            "metadata": self.metadata,
            "session_summary": self.session_summary,
            "topic_tags": self.topic_tags,
            "session_type": self.session_type,
            "consistency_results": _serialize_consistency(self.consistency_results),
            "contradiction_resolutions": self.contradiction_resolutions,
            "stage": self.stage,
            "lock_session_id": self.lock_session_id,
            "brain": self.brain,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_checkpoint(cls, data: dict) -> "DeferredWriter":
        """Restore a DeferredWriter from a MongoDB checkpoint dict."""
        writer = cls()
        writer.original_doc = data.get("original_doc", "")
        writer.in_memory_doc = data.get("in_memory_doc", "")
        writer.transcript = data.get("transcript", "")
        writer.confirmed_claims = data.get("confirmed_claims", [])
        writer.metadata = data.get("metadata", {})
        writer.session_summary = data.get("session_summary", "")
        writer.topic_tags = data.get("topic_tags", [])
        writer.session_type = data.get("session_type", "")
        writer.consistency_results = data.get("consistency_results")
        writer.contradiction_resolutions = data.get("contradiction_resolutions", [])
        writer.stage = data.get("stage", "unknown")
        writer.lock_session_id = data.get("lock_session_id")
        writer.brain = data.get("brain", "pitch")
        return writer


def _serialize_consistency(results) -> Optional[dict]:
    """Make consistency results JSON-serializable for MongoDB (strip raw LLM output)."""
    if results is None:
        return None
    safe = {}
    for key in ("has_contradictions", "has_critical", "summary"):
        if key in results:
            safe[key] = results[key]
    if results.get("pass2"):
        p2 = results["pass2"]
        safe["pass2"] = {
            "retained": p2.get("retained", []),
            "has_critical": p2.get("has_critical", False),
            "total_retained": p2.get("total_retained", 0),
        }
    if results.get("pass3"):
        p3 = results["pass3"]
        safe["pass3"] = {"analyses": p3.get("analyses", [])}
    return safe


def load_pending_ingestion() -> Optional[DeferredWriter]:
    """
    Check MongoDB for a pending ingestion checkpoint.
    Returns a restored DeferredWriter if found, None otherwise.
    """
    from services.mongo_client import get_pending_ingestion

    data = get_pending_ingestion()
    if data is None:
        return None
    return DeferredWriter.from_checkpoint(data)


def rollback_last_session() -> dict:
    """
    Roll back the most recently committed session:
    1. Find latest session in MongoDB
    2. Delete session + its claims from MongoDB
    3. Revert the correct brain document (pitch_brain.md or ops_brain.md) to previous git version based on session's brain field
    4. Mirror reverted doc to MongoDB
    5. Git commit the revert

    Returns dict with: success (bool), message (str), session_id (str), claims_deleted (int)
    """
    from services.mongo_client import (
        get_latest_session, delete_many, delete_one,
        upsert_living_document,
    )
    from services.document_updater import (
        write_living_document, _git_commit, _doc_path,
    )

    # 1. Find latest session
    session = get_latest_session()
    if session is None:
        return {"success": False, "message": "No sessions found in MongoDB.", "session_id": "", "claims_deleted": 0}

    session_id = str(session["_id"])
    brain = session.get("brain", "pitch")
    doc_path = _doc_path(brain)
    repo_root = doc_path.parent.parent

    # 2. Verify git revert is possible BEFORE deleting MongoDB data
    prev_content = None
    prev_hash = None
    git_error = None
    try:
        relative_path = str(doc_path.relative_to(repo_root)).replace("\\", "/")
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-2", "--", relative_path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        log_lines = log_result.stdout.strip().split("\n")
        if len(log_lines) >= 2:
            prev_hash = log_lines[1].split()[0]
            show_result = subprocess.run(
                ["git", "show", f"{prev_hash}:{relative_path}"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=True,
            )
            prev_content = show_result.stdout
    except subprocess.CalledProcessError as e:
        git_error = e  # Git unavailable — will still delete MongoDB data

    # 3. Acquire doc lock BEFORE MongoDB deletes to ensure atomicity
    #    (prevents window where MongoDB data is deleted but doc revert fails due to lock)
    from services.ingestion_lock import acquire_doc_lock, release_doc_lock
    doc_lock_acquired = False
    if prev_content is not None:
        doc_lock_acquired = acquire_doc_lock(timeout_seconds=30)
        if not doc_lock_acquired:
            return {
                "success": False,
                "message": "Could not acquire document lock for rollback — no changes made.",
                "session_id": session_id,
                "claims_deleted": 0,
            }

    try:
        # 4. Delete claims for this session
        claims_deleted = delete_many("claims", {"session_id": session_id})

        # 5. Delete the session document
        delete_one("sessions", {"_id": session["_id"]})

        # 6. Revert living document if git content was found
        if prev_content is not None:
            write_living_document(prev_content, brain=brain)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            upsert_living_document(
                prev_content,
                metadata={"last_updated": date_str, "update_reason": f"Rollback session {session_id}"},
                brain=brain,
            )
            _git_commit(f"Rollback session: {session_id}", brain=brain)
    finally:
        if doc_lock_acquired:
            release_doc_lock()

    if prev_content is not None:
        return {
            "success": True,
            "message": f"Rolled back session {session_id}: {claims_deleted} claims deleted, "
                       f"document reverted to commit {prev_hash}.",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
    elif git_error is not None:
        return {
            "success": True,
            "message": f"Session {session_id} deleted from MongoDB ({claims_deleted} claims). "
                       f"Git revert failed: {git_error}",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
    else:
        return {
            "success": True,
            "message": f"Session {session_id} deleted from MongoDB ({claims_deleted} claims). "
                       "Only one git commit for the document — no git revert performed.",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
