"""
Deferred writes for the ingestion pipeline.
Runs LLM calls eagerly but defers all disk/MongoDB/git writes
until batch_commit() at the very end of the pipeline.

Checkpoints pipeline state to MongoDB so crashes are recoverable.
"""

import hashlib
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
        self.original_doc_hash = hashlib.sha256(doc.encode()).hexdigest()
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

    def save_checkpoint(self) -> bool:
        """Persist current pipeline state to MongoDB pending_ingestion collection."""
        from services.mongo_client import upsert_pending_ingestion
        ok = upsert_pending_ingestion(self.to_checkpoint())
        if not ok:
            logging.error("save_checkpoint: checkpoint not persisted to MongoDB")
        return ok

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
        from services.mongo_client import upsert_living_document, delete_pending_ingestion, find_many
        from services.ingestion import store_session, store_confirmed_claims
        from services.ingestion_lock import acquire_doc_lock, release_doc_lock

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc_changed = self.in_memory_doc != self.original_doc

        session_id = getattr(self, '_committed_session_id', None)
        claims_stored = 0
        doc_write_succeeded = False

        # Revalidate ingestion lock ownership — guard against stale session after network interruption
        if self.lock_session_id:
            from services.ingestion_lock import check_lock
            lock_status = check_lock()
            if lock_status.get("locked") and lock_status.get("session_id") != self.lock_session_id:
                logging.error("batch_commit: ingestion lock owned by another session (%s != %s) — aborting",
                              lock_status.get("session_id"), self.lock_session_id)
                return {
                    "success": False,
                    "message": "Another ingestion took over — your session's lock expired. Please re-ingest.",
                    "claims_stored": 0,
                    "session_id": "",
                    "document_updated": False,
                    "changes_applied": 0,
                }

        try:
            # 1. Write file (only if changed) — acquire doc lock to prevent clobbering
            if doc_changed:
                lock_id = acquire_doc_lock(timeout_seconds=60)
                if not lock_id:
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
                            self._committed_session_id = session_id_result
                            inserted = store_confirmed_claims(
                                self.confirmed_claims, session_id_result,
                                metadata=self.metadata, brain=self.brain,
                            )
                            claims_stored_count = len(inserted) if inserted else 0
                    except Exception as store_err:
                        logging.error("Failed to store session/claims on doc-lock failure: %s", store_err)
                    # Save checkpoint with committed_session_id so retry skips session re-insert
                    try:
                        self.save_checkpoint()
                    except Exception as cp_err:
                        logging.warning("Could not save checkpoint after doc-lock failure session store: %s", cp_err)
                    return {
                        "success": False,
                        "message": "Document lock unavailable — session and claims stored but document not updated. Try again later.",
                        "claims_stored": claims_stored_count,
                        "session_id": session_id_result or "",
                        "document_updated": False,
                        "changes_applied": 0,
                    }
                try:
                    # Freshness check: detect concurrent document modifications
                    from services.document_updater import read_living_document, generate_diff, verify_diff, parse_diff_output, apply_diff
                    current_doc = read_living_document(brain=self.brain)
                    current_hash = hashlib.sha256(current_doc.encode()).hexdigest()

                    if current_hash != getattr(self, "original_doc_hash", ""):
                        logging.warning("batch_commit: document was modified during pipeline — re-generating diffs against current document")
                        # Re-apply diffs to the current (not stale) document (Option A)
                        new_info = self._build_claims_summary()
                        update_reason_for_diff = self._build_update_reason()
                        diff_output = generate_diff(current_doc, new_info, update_reason_for_diff, brain=self.brain)
                        verification = verify_diff(current_doc, diff_output, new_info, brain=self.brain)

                        if verification["verified"]:
                            diff_blocks = parse_diff_output(diff_output)
                            if diff_blocks:
                                self.in_memory_doc = apply_diff(current_doc, diff_blocks, brain=self.brain)
                                self._changes_applied = len(diff_blocks)
                                logging.info("batch_commit: re-applied %d diff block(s) to current document", len(diff_blocks))
                            else:
                                # No changes needed — information already present in current doc
                                self.in_memory_doc = current_doc
                                self._changes_applied = 0
                                logging.info("batch_commit: re-diff produced no changes — concurrent write may have included same info")
                        else:
                            logging.error("batch_commit: re-generated diff failed verification — aborting doc write")
                            # Store session + claims even though doc can't be updated
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
                                    self._committed_session_id = session_id_result
                                    inserted = store_confirmed_claims(
                                        self.confirmed_claims, session_id_result,
                                        metadata=self.metadata, brain=self.brain,
                                    )
                                    claims_stored_count = len(inserted) if inserted else 0
                            except Exception as store_err:
                                logging.error("Failed to store session/claims on conflict resolution failure: %s", store_err)
                            return {
                                "success": False,
                                "message": "The document was modified while you were reviewing claims. "
                                           "Session and claims saved, but document could not be updated. Please re-ingest to apply document changes.",
                                "claims_stored": claims_stored_count,
                                "session_id": session_id_result or "",
                                "document_updated": False,
                                "changes_applied": 0,
                            }

                        # Update doc_changed flag after re-diff
                        doc_changed = self.in_memory_doc != current_doc

                    # 2. Mirror to MongoDB first (source of truth on Render's ephemeral FS)
                    update_reason = self._build_update_reason()
                    if doc_changed:
                        try:
                            mirror_ok = upsert_living_document(
                                self.in_memory_doc,
                                metadata={"last_updated": date_str, "update_reason": update_reason},
                                brain=self.brain,
                            )
                            if not mirror_ok:
                                raise RuntimeError("upsert_living_document returned False")
                        except Exception as mirror_err:
                            logging.error("MongoDB mirror failed in batch_commit — aborting doc write to prevent desync: %s", mirror_err)
                            raise  # Let outer except handle checkpoint + retry

                        write_living_document(self.in_memory_doc, brain=self.brain)
                        doc_write_succeeded = True

                    # 3. Single git commit
                    if doc_changed:
                        brain_label = "pitch_brain.md" if self.brain == "pitch" else "ops_brain.md"
                        commit_msg = f"Update {brain_label}: {self._build_update_reason()} ({date_str})"
                        _git_commit(commit_msg, brain=self.brain)
                finally:
                    release_doc_lock(lock_id)

            # 4. Store session (skip if already stored from a previous attempt)
            if not session_id:
                session_id = store_session(
                    self.transcript,
                    metadata=self.metadata,
                    session_summary=self.session_summary,
                    topic_tags=self.topic_tags,
                    brain=self.brain,
                )
                if session_id:
                    self._committed_session_id = session_id
                else:
                    logging.error("batch_commit: store_session returned None — session not persisted")

            # 5. Store claims (skip if already stored from a previous attempt)
            claims_stored = 0
            if session_id:
                existing_claims = find_many("claims", {"session_id": session_id})
                if existing_claims and len(existing_claims) >= len(self.confirmed_claims):
                    claims_stored = len(existing_claims)
                    logging.info("batch_commit: %d claims already exist for session %s — skipping re-insert", claims_stored, session_id)
                else:
                    # Partial or no claims stored — insert missing ones
                    existing_texts = {c.get("claim_text", "") for c in existing_claims} if existing_claims else set()
                    missing_claims = [c for c in self.confirmed_claims if c.get("claim_text", "") not in existing_texts]
                    if missing_claims:
                        inserted = store_confirmed_claims(
                            missing_claims, session_id, metadata=self.metadata,
                            brain=self.brain,
                        )
                        claims_stored = len(inserted) + (len(existing_claims) if existing_claims else 0)
                    else:
                        claims_stored = len(existing_claims) if existing_claims else 0
                    if self.confirmed_claims and claims_stored == 0:
                        logging.error("batch_commit: all claim inserts failed — session stored but no RAG evidence")

            # 6. Delete checkpoint
            if not delete_pending_ingestion():
                logging.error("checkpoint deletion failed — stale checkpoint may trigger false recovery on next load")

            return {
                "success": bool(session_id) and (claims_stored > 0 or not self.confirmed_claims),
                "message": "Batch commit complete." if (session_id and (claims_stored > 0 or not self.confirmed_claims)) else "Document updated but session could not be saved to database.",
                "claims_stored": claims_stored,
                "session_id": session_id or "",
                "document_updated": doc_write_succeeded,
                "changes_applied": getattr(self, '_changes_applied', 0) if doc_write_succeeded else 0,
            }

        except Exception as e:
            logging.error("batch_commit failed: %s", e)
            # Clean up orphaned session if claims storage failed
            if session_id and claims_stored == 0:
                try:
                    from services.mongo_client import delete_one
                    if not delete_one("sessions", {"_id": session_id}):
                        logging.warning("batch_commit: could not clean up orphaned session %s", session_id)
                    self._committed_session_id = None
                    logging.info("Cleaned up orphaned session %s after batch_commit failure", session_id)
                except Exception as cleanup_err:
                    logging.warning("Could not clean up orphaned session %s: %s", session_id, cleanup_err)
            # Preserve checkpoint for retry — only delete if doc was already committed
            if doc_changed:
                # Doc write succeeded, only session/claims failed — save checkpoint
                # so retry can skip the doc write and just re-store session/claims
                try:
                    self.stage = "ready_to_commit"
                    self.save_checkpoint()
                except Exception as cp_err:
                    logging.warning("Could not save checkpoint for retry: %s", cp_err)
            else:
                try:
                    if not delete_pending_ingestion():
                        logging.error("checkpoint deletion failed — stale checkpoint may trigger false recovery on next load")
                except Exception as cp_err:
                    logging.warning("Could not delete checkpoint in batch_commit failure path: %s", cp_err)
            return {
                "success": False,
                "message": f"Batch commit failed: {e}",
                "claims_stored": 0,
                "session_id": "",
                "document_updated": doc_write_succeeded,
                "changes_applied": getattr(self, '_changes_applied', 0) if doc_write_succeeded else 0,
            }

    def rollback(self):
        """Discard all in-memory changes and delete the checkpoint."""
        from services.mongo_client import delete_pending_ingestion, delete_one, delete_many
        # Clean up any committed session/claims from a partial batch_commit
        committed_id = getattr(self, '_committed_session_id', None)
        if committed_id:
            try:
                delete_many("claims", {"session_id": str(committed_id)})
                delete_one("sessions", {"_id": committed_id})
            except Exception as e:
                logging.error("rollback: failed to clean up committed session %s: %s", committed_id, e)
        # Revert document if it was already written to disk/MongoDB
        if self.in_memory_doc != self.original_doc:
            try:
                from services.document_updater import write_living_document
                from services.mongo_client import upsert_living_document
                upsert_living_document(self.original_doc, metadata={"update_reason": "Discard recovery"}, brain=self.brain)
                write_living_document(self.original_doc, brain=self.brain)
            except Exception as e:
                logging.error("rollback: failed to revert document: %s", e)
        self.in_memory_doc = self.original_doc
        self.contradiction_resolutions = []
        delete_pending_ingestion()

    def _build_claims_summary(self) -> str:
        """Build a summary of confirmed claims for re-generating diffs."""
        parts = []
        for claim in self.confirmed_claims:
            text = claim.get("claim_text", "")
            ctype = claim.get("claim_type", "claim")
            who = claim.get("who_said_it", "")
            line = f"[{ctype}] {text}"
            if who:
                line += f" (said by {who})"
            parts.append(line)
        return "\n".join(parts)

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
            "original_doc_hash": getattr(self, "original_doc_hash", ""),
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
            "committed_session_id": getattr(self, "_committed_session_id", None),
            "changes_applied": getattr(self, "_changes_applied", 0),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_checkpoint(cls, data: dict) -> "DeferredWriter":
        """Restore a DeferredWriter from a MongoDB checkpoint dict."""
        writer = cls()
        writer.original_doc = data.get("original_doc", "")
        writer.original_doc_hash = data.get("original_doc_hash", "")
        # Recompute hash if missing (backward compat with old checkpoints)
        if not writer.original_doc_hash and writer.original_doc:
            writer.original_doc_hash = hashlib.sha256(writer.original_doc.encode()).hexdigest()
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
        writer._committed_session_id = data.get("committed_session_id")
        writer._changes_applied = data.get("changes_applied", 0)
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
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        git_error = e  # Git unavailable — will still delete MongoDB data

    # 3. Acquire doc lock BEFORE MongoDB deletes to ensure atomicity
    #    (prevents window where MongoDB data is deleted but doc revert fails due to lock)
    from services.ingestion_lock import acquire_doc_lock, release_doc_lock
    doc_lock_id = None
    if prev_content is not None:
        doc_lock_id = acquire_doc_lock(timeout_seconds=30)
        if not doc_lock_id:
            return {
                "success": False,
                "message": "Could not acquire document lock for rollback — no changes made.",
                "session_id": session_id,
                "claims_deleted": 0,
            }

    try:
        # 4. Revert living document FIRST (before deleting MongoDB data)
        #    so that if the file write fails, MongoDB data is still intact.
        if prev_content is not None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            upsert_living_document(
                prev_content,
                metadata={"last_updated": date_str, "update_reason": f"Rollback session {session_id}"},
                brain=brain,
            )
            write_living_document(prev_content, brain=brain)
            _git_commit(f"Rollback session: {session_id}", brain=brain)

        # 5. Delete the session document first (orphaned claims are less visible than orphaned sessions)
        session_deleted = delete_one("sessions", {"_id": session["_id"]})
        if not session_deleted:
            logging.warning("rollback: session %s could not be deleted from MongoDB", session_id)

        # 6. Delete claims for this session
        claims_deleted = delete_many("claims", {"session_id": session_id})

        # 7. Delete feedback for this session
        try:
            feedback_deleted = delete_many("feedback", {"session_id": session_id})
            if feedback_deleted:
                logging.info("rollback: deleted %d feedback records for session %s", feedback_deleted, session_id)
        except Exception as fb_err:
            logging.warning("rollback: could not delete feedback for session %s: %s", session_id, fb_err)
    finally:
        if doc_lock_id:
            release_doc_lock(doc_lock_id)

    if prev_content is not None:
        return {
            "success": session_deleted,
            "message": f"Rolled back session {session_id}: {claims_deleted} claims deleted, "
                       f"document reverted to commit {prev_hash}.",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
    elif git_error is not None:
        return {
            "success": session_deleted,
            "message": f"Session {session_id} deleted from MongoDB ({claims_deleted} claims). "
                       f"Git revert failed: {git_error}",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
    else:
        return {
            "success": session_deleted,
            "message": f"Session {session_id} deleted from MongoDB ({claims_deleted} claims). "
                       "Only one git commit for the document — no git revert performed.",
            "session_id": session_id,
            "claims_deleted": claims_deleted,
        }
