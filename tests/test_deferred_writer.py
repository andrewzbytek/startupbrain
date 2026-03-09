"""
Unit tests for services/deferred_writer.py — DeferredWriter, load_pending_ingestion,
and rollback_last_session.
All tests run without API keys, MongoDB, or network access.
"""

import sys
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = MagicMock()
mock_st.session_state = {}
sys.modules.setdefault("streamlit", mock_st)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOC = "## Current State\n### Pricing\n**Current position:** $50/mo\n**Changelog:**\n"
SAMPLE_CLAIMS = [
    {"claim_text": "Price is $100/mo", "claim_type": "decision", "confidence": "definite", "confirmed": True},
]
SAMPLE_METADATA = {"participants": "Alice, Bob", "topic": "Pricing", "session_type": "Co-founder discussion"}


def _make_writer(doc=SAMPLE_DOC, claims=None, metadata=None):
    """Create and initialize a DeferredWriter with mocked file read."""
    with patch("services.document_updater.read_living_document", return_value=doc):
        from services.deferred_writer import DeferredWriter
        writer = DeferredWriter()
        writer.initialize(
            transcript="test transcript",
            confirmed_claims=claims or list(SAMPLE_CLAIMS),
            metadata=metadata or dict(SAMPLE_METADATA),
            session_summary="A test session",
            topic_tags=["pricing"],
            session_type="Co-founder discussion",
        )
    return writer


# ---------------------------------------------------------------------------
# Initialize tests
# ---------------------------------------------------------------------------

class TestInitialize:

    def test_snapshots_document(self):
        writer = _make_writer()
        assert writer.original_doc == SAMPLE_DOC
        assert writer.in_memory_doc == SAMPLE_DOC

    def test_stores_transcript(self):
        writer = _make_writer()
        assert writer.transcript == "test transcript"

    def test_stores_claims(self):
        writer = _make_writer()
        assert len(writer.confirmed_claims) == 1
        assert writer.confirmed_claims[0]["claim_text"] == "Price is $100/mo"

    def test_stores_metadata(self):
        writer = _make_writer()
        assert writer.metadata["participants"] == "Alice, Bob"
        assert writer.session_type == "Co-founder discussion"

    def test_stage_is_initialized(self):
        writer = _make_writer()
        assert writer.stage == "initialized"


# ---------------------------------------------------------------------------
# Checkpoint round-trip tests
# ---------------------------------------------------------------------------

class TestCheckpointRoundTrip:

    def test_to_checkpoint_returns_dict(self):
        writer = _make_writer()
        cp = writer.to_checkpoint()
        assert isinstance(cp, dict)
        assert cp["_id"] == "pending"

    def test_round_trip_preserves_fields(self):
        from services.deferred_writer import DeferredWriter
        writer = _make_writer()
        writer.stage = "awaiting_resolution"
        writer.contradiction_resolutions = [{"index": 0, "action": "keep", "new_claim": "", "explanation": ""}]

        cp = writer.to_checkpoint()
        restored = DeferredWriter.from_checkpoint(cp)

        assert restored.original_doc == writer.original_doc
        assert restored.in_memory_doc == writer.in_memory_doc
        assert restored.transcript == writer.transcript
        assert len(restored.confirmed_claims) == len(writer.confirmed_claims)
        assert restored.session_type == writer.session_type
        assert restored.stage == "awaiting_resolution"
        assert len(restored.contradiction_resolutions) == 1

    def test_from_checkpoint_handles_missing_keys(self):
        from services.deferred_writer import DeferredWriter
        restored = DeferredWriter.from_checkpoint({"_id": "pending"})
        assert restored.original_doc == ""
        assert restored.confirmed_claims == []
        assert restored.stage == "unknown"


# ---------------------------------------------------------------------------
# apply_document_update_deferred tests
# ---------------------------------------------------------------------------

class TestApplyDocumentUpdateDeferred:

    def test_modifies_in_memory_doc(self):
        writer = _make_writer()
        original = writer.in_memory_doc

        with patch("services.document_updater.generate_diff", return_value="SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n**Current position:** $100/mo"), \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": []}):
            result = writer.apply_document_update_deferred("Price changed to $100/mo", "test")

        assert result["success"] is True
        assert result["changes_applied"] >= 1
        assert writer.in_memory_doc != original

    def test_does_not_write_to_disk(self):
        writer = _make_writer()

        with patch("services.document_updater.generate_diff", return_value="SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n**Current position:** $100/mo"), \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": []}), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._git_commit") as mock_git, \
             patch("services.mongo_client.upsert_living_document") as mock_upsert:
            writer.apply_document_update_deferred("Price changed to $100/mo", "test")

        mock_write.assert_not_called()
        mock_git.assert_not_called()
        mock_upsert.assert_not_called()

    def test_returns_failure_when_no_doc(self):
        from services.deferred_writer import DeferredWriter
        writer = DeferredWriter()
        # in_memory_doc is empty string
        result = writer.apply_document_update_deferred("info", "reason")
        assert result["success"] is False

    def test_returns_failure_on_verification_fail(self):
        writer = _make_writer()

        with patch("services.document_updater.generate_diff", return_value="bad diff"), \
             patch("services.document_updater.verify_diff", return_value={"verified": False, "notes": "", "issues": ["bad"]}):
            result = writer.apply_document_update_deferred("info", "reason")

        assert result["success"] is False
        assert "verification failed" in result["message"].lower()


# ---------------------------------------------------------------------------
# apply_decision_log_deferred / apply_dismissed_deferred tests
# ---------------------------------------------------------------------------

class TestDeferredLogEntries:

    def test_apply_decision_log_deferred(self):
        doc = SAMPLE_DOC + "\n## Decision Log\n\n## Dismissed Contradictions\n"
        writer = _make_writer(doc=doc)
        entry = "### 2026-03-01 — Test decision\n**Decision:** Something"
        writer.apply_decision_log_deferred(entry)
        assert "Test decision" in writer.in_memory_doc

    def test_apply_dismissed_deferred(self):
        doc = SAMPLE_DOC + "\n## Decision Log\n\n## Dismissed Contradictions\n[No dismissed contradictions]"
        writer = _make_writer(doc=doc)
        entry = '- [2026-03-01] Dismissed: "some claim"'
        writer.apply_dismissed_deferred(entry)
        assert "some claim" in writer.in_memory_doc


# ---------------------------------------------------------------------------
# record_contradiction_resolution tests
# ---------------------------------------------------------------------------

class TestRecordContradictionResolution:

    def test_list_grows(self):
        writer = _make_writer()
        assert len(writer.contradiction_resolutions) == 0
        writer.record_contradiction_resolution(0, "update", "new pos", "")
        assert len(writer.contradiction_resolutions) == 1
        writer.record_contradiction_resolution(1, "keep", "", "")
        assert len(writer.contradiction_resolutions) == 2

    def test_stores_all_fields(self):
        writer = _make_writer()
        writer.record_contradiction_resolution(2, "explain", "claim text", "my reason")
        r = writer.contradiction_resolutions[0]
        assert r["index"] == 2
        assert r["action"] == "explain"
        assert r["new_claim"] == "claim text"
        assert r["explanation"] == "my reason"


# ---------------------------------------------------------------------------
# save_checkpoint tests
# ---------------------------------------------------------------------------

class TestSaveCheckpoint:

    def test_calls_upsert(self):
        writer = _make_writer()
        with patch("services.mongo_client.upsert_pending_ingestion") as mock_upsert:
            writer.save_checkpoint()
        mock_upsert.assert_called_once()
        arg = mock_upsert.call_args[0][0]
        assert arg["_id"] == "pending"
        assert arg["transcript"] == "test transcript"


# ---------------------------------------------------------------------------
# rollback tests
# ---------------------------------------------------------------------------

class TestRollback:

    def test_restores_original_doc(self):
        writer = _make_writer()
        writer.in_memory_doc = "modified content"
        with patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"):
            writer.rollback()
        assert writer.in_memory_doc == SAMPLE_DOC

    def test_deletes_checkpoint(self):
        writer = _make_writer()
        with patch("services.mongo_client.delete_pending_ingestion") as mock_delete, \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"):
            writer.rollback()
        mock_delete.assert_called_once()

    def test_clears_resolutions(self):
        writer = _make_writer()
        writer.contradiction_resolutions = [{"index": 0}]
        with patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"):
            writer.rollback()
        assert writer.contradiction_resolutions == []


# ---------------------------------------------------------------------------
# batch_commit tests
# ---------------------------------------------------------------------------

class TestBatchCommit:

    def test_writes_file_when_doc_changed(self):
        writer = _make_writer()
        writer.in_memory_doc = "changed content"

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        mock_write.assert_called_once_with("changed content", brain="pitch")
        assert result["success"] is True

    def test_skip_write_when_doc_unchanged(self):
        writer = _make_writer()
        # in_memory_doc == original_doc

        with patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._git_commit") as mock_git, \
             patch("services.mongo_client.upsert_living_document") as mock_upsert, \
             patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]):
            result = writer.batch_commit()

        mock_write.assert_not_called()
        mock_git.assert_not_called()
        mock_upsert.assert_not_called()
        assert result["success"] is True

    def test_single_git_commit(self):
        writer = _make_writer()
        writer.in_memory_doc = "changed"

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True) as mock_git, \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.ingestion.store_session", return_value="s1"), \
             patch("services.ingestion.store_confirmed_claims", return_value=[]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            writer.batch_commit()

        assert mock_git.call_count == 1

    def test_stores_session_and_claims(self):
        writer = _make_writer()
        writer.in_memory_doc = "changed"

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.mongo_client.delete_pending_ingestion"), \
             patch("services.ingestion.store_session", return_value="sess1") as mock_store_session, \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1", "c2"]) as mock_store_claims, \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        mock_store_session.assert_called_once()
        mock_store_claims.assert_called_once()
        assert result["claims_stored"] == 2

    def test_deletes_checkpoint_on_success(self):
        writer = _make_writer()

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.mongo_client.delete_pending_ingestion") as mock_delete, \
             patch("services.ingestion.store_session", return_value="s1"), \
             patch("services.ingestion.store_confirmed_claims", return_value=[]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            writer.batch_commit()

        mock_delete.assert_called_once()

    def test_preserves_checkpoint_on_failure_when_doc_changed(self):
        """Checkpoint is preserved on failure when doc was changed, enabling retry."""
        writer = _make_writer()
        writer.in_memory_doc = "changed"

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.write_living_document", side_effect=IOError("disk full")), \
             patch("services.mongo_client.delete_pending_ingestion") as mock_delete, \
             patch("services.mongo_client.upsert_pending_ingestion") as mock_save_cp, \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is False
        mock_delete.assert_not_called()
        mock_save_cp.assert_called_once()  # checkpoint saved for retry

    def test_deletes_checkpoint_on_failure_when_doc_unchanged(self):
        """Checkpoint is deleted on failure when doc was NOT changed (no retry needed)."""
        writer = _make_writer()
        # in_memory_doc == original_doc, so doc_changed is False

        with patch("services.ingestion.store_session", side_effect=IOError("db error")), \
             patch("services.mongo_client.delete_pending_ingestion") as mock_delete, \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is False
        mock_delete.assert_called_once()

    def test_batch_commit_doc_lock_failure(self):
        """batch_commit should handle doc lock failure gracefully and save checkpoint for retry."""
        writer = _make_writer()
        writer.in_memory_doc = "changed content"

        with patch("services.ingestion_lock.acquire_doc_lock", return_value=None), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.mongo_client.upsert_pending_ingestion", return_value=True) as mock_save_cp:
            result = writer.batch_commit()

        assert result["success"] is False
        assert "lock" in result["message"].lower()
        mock_write.assert_not_called()
        # Checkpoint should be saved (not deleted) so retry can skip session re-insert
        mock_save_cp.assert_called_once()


# ---------------------------------------------------------------------------
# load_pending_ingestion tests
# ---------------------------------------------------------------------------

class TestLoadPendingIngestion:

    def test_returns_writer_when_checkpoint_exists(self):
        checkpoint = {
            "_id": "pending",
            "original_doc": "doc",
            "in_memory_doc": "doc modified",
            "transcript": "transcript",
            "confirmed_claims": [{"claim_text": "x"}],
            "metadata": {},
            "session_summary": "summary",
            "topic_tags": [],
            "session_type": "Other",
            "consistency_results": None,
            "contradiction_resolutions": [],
            "stage": "awaiting_resolution",
        }
        with patch("services.mongo_client.get_pending_ingestion", return_value=checkpoint):
            from services.deferred_writer import load_pending_ingestion
            writer = load_pending_ingestion()

        assert writer is not None
        assert writer.original_doc == "doc"
        assert writer.in_memory_doc == "doc modified"
        assert writer.stage == "awaiting_resolution"

    def test_returns_none_when_no_checkpoint(self):
        with patch("services.mongo_client.get_pending_ingestion", return_value=None):
            from services.deferred_writer import load_pending_ingestion
            result = load_pending_ingestion()

        assert result is None


# ---------------------------------------------------------------------------
# _serialize_consistency tests
# ---------------------------------------------------------------------------

class TestSerializeConsistency:

    def test_handles_none(self):
        from services.deferred_writer import _serialize_consistency
        assert _serialize_consistency(None) is None

    def test_strips_raw_output(self):
        from services.deferred_writer import _serialize_consistency
        results = {
            "has_contradictions": True,
            "has_critical": False,
            "summary": "1 Notable",
            "pass1": {"raw": "huge xml blob"},
            "pass2": {"retained": [{"id": "1"}], "has_critical": False, "total_retained": 1, "raw": "more xml"},
        }
        serialized = _serialize_consistency(results)
        assert "raw" not in str(serialized)
        assert serialized["has_contradictions"] is True
        assert serialized["pass2"]["retained"] == [{"id": "1"}]


# ---------------------------------------------------------------------------
# rollback_last_session tests
# ---------------------------------------------------------------------------

class TestRollbackLastSession:

    def _mock_subprocess_run(self, log_stdout="abc1234 Latest commit\ndef5678 Previous commit", show_stdout="previous doc content"):
        """Create a side_effect function for subprocess.run that handles git log and git show."""
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "log" in cmd:
                result.stdout = log_stdout
            elif "show" in cmd:
                result.stdout = show_stdout
            else:
                result.stdout = ""
            return result
        return side_effect

    def test_returns_failure_when_no_sessions(self):
        with patch("services.mongo_client.get_latest_session", return_value=None):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()
        assert result["success"] is False
        assert "No sessions" in result["message"]

    def test_deletes_claims_and_session(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=3) as mock_del_many, \
             patch("services.mongo_client.delete_one", return_value=True) as mock_del_one, \
             patch("subprocess.run", side_effect=self._mock_subprocess_run()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.document_updater._git_commit", return_value=True):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        # delete_many called for claims and feedback
        assert mock_del_many.call_count == 2
        mock_del_many.assert_any_call("claims", {"session_id": str(sid)})
        mock_del_many.assert_any_call("feedback", {"session_id": str(sid)})
        mock_del_one.assert_called_once_with("sessions", {"_id": sid})
        assert result["claims_deleted"] == 3

    def test_reverts_document_to_previous_commit(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=1), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=self._mock_subprocess_run(show_stdout="reverted content")), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.mongo_client.upsert_living_document") as mock_upsert, \
             patch("services.document_updater._git_commit", return_value=True):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        mock_write.assert_called_once_with("reverted content", brain="pitch")
        mock_upsert.assert_called_once()
        assert result["success"] is True

    def test_git_commits_the_revert(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=0), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=self._mock_subprocess_run()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.document_updater._git_commit", return_value=True) as mock_git:
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        mock_git.assert_called_once()
        assert "Rollback session" in mock_git.call_args[0][0]

    def test_handles_single_commit_gracefully(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=2), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=self._mock_subprocess_run(log_stdout="abc1234 Only commit")), \
             patch("services.document_updater.write_living_document") as mock_write:
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        # Should still succeed but not revert git
        assert result["success"] is True
        assert "no git revert" in result["message"].lower()
        mock_write.assert_not_called()

    def test_handles_git_failure_gracefully(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        def fail_subprocess(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=1), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=fail_subprocess):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        # MongoDB cleanup still succeeded
        assert result["success"] is True
        assert "Git revert failed" in result["message"]
        assert result["claims_deleted"] == 1

    def test_returns_session_id(self):
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=0), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=self._mock_subprocess_run()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.document_updater._git_commit", return_value=True):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        assert result["session_id"] == str(sid)

    def test_rollback_ops_brain(self):
        """rollback_last_session should use ops brain when session has brain='ops'."""
        from bson import ObjectId
        sid = ObjectId()
        session = {"_id": sid, "created_at": "2026-03-01", "brain": "ops"}

        with patch("services.mongo_client.get_latest_session", return_value=session), \
             patch("services.mongo_client.delete_many", return_value=1), \
             patch("services.mongo_client.delete_one", return_value=True), \
             patch("subprocess.run", side_effect=self._mock_subprocess_run(show_stdout="ops reverted content")), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.mongo_client.upsert_living_document") as mock_upsert, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            from services.deferred_writer import rollback_last_session
            result = rollback_last_session()

        assert result["success"] is True
        mock_write.assert_called_once_with("ops reverted content", brain="ops")
        mock_upsert.assert_called_once()
        # Verify upsert was called with brain="ops"
        assert mock_upsert.call_args[1].get("brain") == "ops"


# ---------------------------------------------------------------------------
# Document freshness check tests
# ---------------------------------------------------------------------------

class TestDocumentFreshnessCheck:
    """Tests for the document freshness check in batch_commit (Option A: re-diff)."""

    def test_batch_commit_detects_stale_document(self):
        """When the document changes during the pipeline, batch_commit should detect it."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        # read_living_document returns a different doc than the original snapshot
        concurrent_doc = SAMPLE_DOC + "\n### New Hypothesis\n**hypothesis text**\n"

        with patch("services.document_updater.read_living_document", return_value=concurrent_doc), \
             patch("services.document_updater.generate_diff", return_value="SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n**Current position:** $100/mo") as mock_gen, \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": []}) as mock_verify, \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.delete_pending_ingestion", return_value=True), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is True
        # generate_diff should be called with the CURRENT doc, not the stale snapshot
        mock_gen.assert_called_once()
        assert mock_gen.call_args[0][0] == concurrent_doc

    def test_batch_commit_reapplies_diffs_on_conflict(self):
        """On conflict, generate_diff is called with the current document and claims summary."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        concurrent_doc = SAMPLE_DOC + "\n## Extra Section\n"

        with patch("services.document_updater.read_living_document", return_value=concurrent_doc), \
             patch("services.document_updater.generate_diff", return_value="SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n**Current position:** $100/mo") as mock_gen, \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": []}), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.delete_pending_ingestion", return_value=True), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is True
        # The written doc should be the result of apply_diff on concurrent_doc, not stale snapshot
        written_doc = mock_write.call_args[0][0]
        assert "$100/mo" in written_doc

    def test_batch_commit_preserves_concurrent_changes(self):
        """A hypothesis written during the pipeline should survive batch_commit."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        hypothesis_line = "- [2026-03-07] **We should pivot to enterprise**"
        concurrent_doc = SAMPLE_DOC + f"\n## Active Hypotheses\n{hypothesis_line}\n"

        with patch("services.document_updater.read_living_document", return_value=concurrent_doc), \
             patch("services.document_updater.generate_diff", return_value="SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n**Current position:** $100/mo"), \
             patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": []}), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.delete_pending_ingestion", return_value=True), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is True
        written_doc = mock_write.call_args[0][0]
        # The hypothesis from the concurrent write should be preserved
        assert "pivot to enterprise" in written_doc

    def test_batch_commit_no_conflict_skips_rediff(self):
        """When document hasn't changed, no re-diff should happen."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        with patch("services.document_updater.read_living_document", return_value=SAMPLE_DOC), \
             patch("services.document_updater.generate_diff") as mock_gen, \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.delete_pending_ingestion", return_value=True), \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"):
            result = writer.batch_commit()

        assert result["success"] is True
        # generate_diff should NOT be called when document hasn't changed
        mock_gen.assert_not_called()

    def test_batch_commit_conflict_verification_fails(self):
        """When re-diff verification fails, session+claims stored but doc not updated."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        concurrent_doc = SAMPLE_DOC + "\n## Extra\n"

        with patch("services.document_updater.read_living_document", return_value=concurrent_doc), \
             patch("services.document_updater.generate_diff", return_value="bad diff"), \
             patch("services.document_updater.verify_diff", return_value={"verified": False, "notes": "", "issues": ["bad"]}), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.ingestion.store_session", return_value="sess123"), \
             patch("services.ingestion.store_confirmed_claims", return_value=["c1"]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock"), \
             patch("services.mongo_client.delete_pending_ingestion") as mock_del_cp:
            result = writer.batch_commit()

        assert result["success"] is False
        assert result["document_updated"] is False
        assert "modified while you were reviewing" in result["message"]
        assert result["claims_stored"] == 1
        # Document should NOT have been written
        mock_write.assert_not_called()
        # Checkpoint should be DELETED (session+claims stored, user told to re-ingest)
        mock_del_cp.assert_called_once()

    def test_batch_commit_conflict_api_error(self):
        """When generate_diff throws during conflict re-diff, stale doc is NOT written."""
        writer = _make_writer()
        writer.in_memory_doc = "modified by pipeline"

        concurrent_doc = SAMPLE_DOC + "\n## Extra\n"

        with patch("services.document_updater.read_living_document", return_value=concurrent_doc), \
             patch("services.document_updater.generate_diff", side_effect=Exception("API timeout")), \
             patch("services.document_updater.write_living_document") as mock_write, \
             patch("services.mongo_client.upsert_living_document") as mock_upsert, \
             patch("services.mongo_client.upsert_pending_ingestion", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="lock-123"), \
             patch("services.ingestion_lock.release_doc_lock") as mock_release:
            result = writer.batch_commit()

        assert result["success"] is False
        # CRITICAL: stale document must NOT be written
        mock_write.assert_not_called()
        # Lock must be released even on error
        mock_release.assert_called_once_with("lock-123")

    def test_build_claims_summary(self):
        """_build_claims_summary should format all confirmed claims."""
        writer = _make_writer(claims=[
            {"claim_text": "Price is $100", "claim_type": "decision", "who_said_it": "Alice"},
            {"claim_text": "TAM is $1B", "claim_type": "market_data"},
            {"claim_text": "", "claim_type": "claim"},
        ])
        summary = writer._build_claims_summary()
        assert "[decision] Price is $100 (said by Alice)" in summary
        assert "[market_data] TAM is $1B" in summary
        assert "(said by" not in summary.split("\n")[1]  # no who_said_it for second claim

    def test_checkpoint_preserves_doc_hash(self):
        """original_doc_hash should survive to_checkpoint → from_checkpoint round-trip."""
        from services.deferred_writer import DeferredWriter
        writer = _make_writer()
        original_hash = writer.original_doc_hash

        assert original_hash != ""
        assert len(original_hash) == 64  # SHA-256 hex digest

        cp = writer.to_checkpoint()
        assert cp["original_doc_hash"] == original_hash

        restored = DeferredWriter.from_checkpoint(cp)
        assert restored.original_doc_hash == original_hash

    def test_checkpoint_recomputes_hash_for_old_checkpoints(self):
        """Old checkpoints without original_doc_hash should recompute it."""
        import hashlib
        from services.deferred_writer import DeferredWriter

        old_checkpoint = {
            "_id": "pending",
            "original_doc": "some doc content",
            "in_memory_doc": "modified",
            # No original_doc_hash key
        }
        restored = DeferredWriter.from_checkpoint(old_checkpoint)
        expected = hashlib.sha256("some doc content".encode()).hexdigest()
        assert restored.original_doc_hash == expected
