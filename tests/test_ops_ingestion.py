"""Tests for services/ops_ingestion.py — Ops Brain ingestion pipeline."""

import pytest
from unittest.mock import patch, MagicMock


class TestRunOpsIngestion:
    """Tests for run_ops_ingestion()."""

    @patch("services.ingestion.store_confirmed_claims")
    @patch("services.ingestion.store_session")
    @patch("services.document_updater.update_document")
    def test_basic_ops_ingestion(self, mock_update, mock_store_session, mock_store_claims):
        """Basic ops ingestion stores session and claims with brain='ops'."""
        from services.ops_ingestion import run_ops_ingestion

        mock_update.return_value = {"success": True, "message": "OK", "changes_applied": 2}
        mock_store_session.return_value = "session-123"
        mock_store_claims.return_value = ["claim-1", "claim-2"]

        claims = [
            {"claim_text": "Sarah Chen interested in pilot", "claim_type": "claim", "confidence": "definite", "confirmed": True},
            {"claim_text": "Need ML engineer by Q2", "claim_type": "decision", "confidence": "definite", "confirmed": True},
        ]

        result = run_ops_ingestion(
            transcript="Met with Sarah Chen at Entergy...",
            confirmed_claims=claims,
            metadata={"session_type": "Customer interview", "session_date": "2026-03-01"},
            session_summary="Customer meeting with Entergy",
            session_type="Customer interview",
        )

        assert result["success"] is True
        assert result["claims_stored"] == 2
        assert result["session_id"] == "session-123"
        assert result["document_updated"] is True

        # Verify brain="ops" passed to all calls
        mock_update.assert_called_once()
        assert mock_update.call_args[1]["brain"] == "ops"
        mock_store_session.assert_called_once()
        assert mock_store_session.call_args[1]["brain"] == "ops"
        mock_store_claims.assert_called_once()
        assert mock_store_claims.call_args[1]["brain"] == "ops"

    @patch("services.ingestion.store_confirmed_claims")
    @patch("services.ingestion.store_session")
    @patch("services.document_updater.update_document")
    def test_ops_ingestion_doc_update_fails(self, mock_update, mock_store_session, mock_store_claims):
        """Ops ingestion still succeeds if doc update fails but claims stored."""
        from services.ops_ingestion import run_ops_ingestion

        mock_update.return_value = {"success": False, "message": "Doc lock failed", "changes_applied": 0}
        mock_store_session.return_value = "session-456"
        mock_store_claims.return_value = ["claim-1"]

        result = run_ops_ingestion(
            transcript="Notes...",
            confirmed_claims=[{"claim_text": "Test", "confirmed": True}],
        )

        assert result["success"] is True  # claims stored successfully
        assert result["document_updated"] is False
        assert result["claims_stored"] == 1

    @patch("services.ingestion.store_confirmed_claims")
    @patch("services.ingestion.store_session")
    @patch("services.document_updater.update_document")
    def test_ops_ingestion_no_session_id(self, mock_update, mock_store_session, mock_store_claims):
        """Ops ingestion handles None session_id gracefully."""
        from services.ops_ingestion import run_ops_ingestion

        mock_update.return_value = {"success": True, "message": "OK", "changes_applied": 1}
        mock_store_session.return_value = None
        mock_store_claims.return_value = []

        result = run_ops_ingestion(
            transcript="Notes...",
            confirmed_claims=[{"claim_text": "Test", "confirmed": True}],
        )

        assert result["success"] is True
        assert result["claims_stored"] == 0
        assert result["session_id"] == ""

    @patch("services.ingestion.store_confirmed_claims")
    @patch("services.ingestion.store_session")
    @patch("services.document_updater.update_document")
    def test_ops_ingestion_empty_claims(self, mock_update, mock_store_session, mock_store_claims):
        """Ops ingestion with empty claims list."""
        from services.ops_ingestion import run_ops_ingestion

        mock_update.return_value = {"success": False, "message": "No changes", "changes_applied": 0}
        mock_store_session.return_value = "session-789"
        mock_store_claims.return_value = []

        result = run_ops_ingestion(
            transcript="Empty meeting",
            confirmed_claims=[],
        )

        assert result["claims_stored"] == 0

    @patch("services.ingestion.store_confirmed_claims")
    @patch("services.ingestion.store_session")
    @patch("services.document_updater.update_document")
    def test_ops_ingestion_builds_update_reason(self, mock_update, mock_store_session, mock_store_claims):
        """Ops ingestion builds correct update reason from metadata."""
        from services.ops_ingestion import run_ops_ingestion

        mock_update.return_value = {"success": True, "message": "OK", "changes_applied": 1}
        mock_store_session.return_value = "s1"
        mock_store_claims.return_value = []

        run_ops_ingestion(
            transcript="Notes",
            confirmed_claims=[{"claim_text": "Test", "confirmed": True}],
            metadata={"session_type": "Advisor session", "session_date": "2026-03-01", "participants": "John"},
            session_type="Advisor session",
        )

        call_args = mock_update.call_args
        update_reason = call_args.kwargs.get("update_reason", "")
        assert "Advisor session" in update_reason
        assert "2026-03-01" in update_reason
        assert "John" in update_reason
