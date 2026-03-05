"""
Unit tests for services/export.py — generate_context_export.
All tests run without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock streamlit before importing
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = MagicMock()
mock_st.session_state = {}
sys.modules.setdefault("streamlit", mock_st)

from bson import ObjectId

SAMPLE_DOC = "# Startup Brain\n## Current State\n### Pricing\n**Current position:** $50/mo\n"

SAMPLE_SESSIONS = [
    {
        "_id": ObjectId(),
        "summary": "First session about vision",
        "session_date": "2026-03-01",
        "metadata": {"session_type": "Co-founder discussion", "participants": "Alice, Bob"},
        "created_at": "2026-03-01T00:00:00",
    },
    {
        "_id": ObjectId(),
        "summary": "Second session about pricing",
        "session_date": "2026-03-02",
        "metadata": {"session_type": "Investor meeting", "participants": "Alice, Charlie"},
        "created_at": "2026-03-02T00:00:00",
    },
]

SAMPLE_CLAIMS = [
    {"claim_text": "Price is $100/mo", "confidence": "definite", "claim_type": "decision"},
    {"claim_text": "Market might be larger", "confidence": "speculative", "claim_type": "claim"},
]


class TestGenerateContextExport:

    def _generate(self, doc=SAMPLE_DOC, sessions=None, claims=None):
        """Helper to call generate_context_export with mocks."""
        with patch("services.document_updater.read_living_document", return_value=doc), \
             patch("services.mongo_client.get_sessions", return_value=list(sessions or [])), \
             patch("services.mongo_client.get_claims", return_value=list(claims or [])):
            from services.export import generate_context_export
            return generate_context_export()

    def test_includes_export_header(self):
        result = self._generate()
        assert "# Startup Context Export" in result

    def test_includes_usage_instructions(self):
        result = self._generate()
        assert "## How to Use This Document" in result

    def test_includes_living_document(self):
        result = self._generate()
        assert "## Living Document" in result
        assert SAMPLE_DOC in result

    def test_includes_session_history_header(self):
        result = self._generate()
        assert "## Session History" in result

    def test_includes_sessions_chronologically(self):
        result = self._generate(sessions=SAMPLE_SESSIONS)
        pos1 = result.index("First session about vision")
        pos2 = result.index("Second session about pricing")
        assert pos1 < pos2

    def test_session_metadata_displayed(self):
        result = self._generate(sessions=SAMPLE_SESSIONS)
        assert "Co-founder discussion" in result
        assert "Alice, Bob" in result
        assert "2026-03-01" in result

    def test_includes_claims_per_session(self):
        result = self._generate(sessions=SAMPLE_SESSIONS, claims=SAMPLE_CLAIMS)
        assert "Price is $100/mo" in result
        assert "Market might be larger" in result

    def test_claims_show_confidence(self):
        result = self._generate(sessions=SAMPLE_SESSIONS, claims=SAMPLE_CLAIMS)
        assert "[definite]" in result
        assert "[speculative]" in result

    def test_graceful_without_sessions(self):
        result = self._generate(sessions=[])
        assert "# Startup Context Export" in result
        assert SAMPLE_DOC in result
        assert "No sessions recorded yet" in result

    def test_graceful_without_living_document(self):
        result = self._generate(doc="")
        assert "# Startup Context Export" in result
        assert "No living document found" in result

    def test_session_numbering(self):
        result = self._generate(sessions=SAMPLE_SESSIONS)
        assert "### Session 1" in result
        assert "### Session 2" in result

    def test_claims_count_displayed(self):
        result = self._generate(sessions=SAMPLE_SESSIONS, claims=SAMPLE_CLAIMS)
        assert "Claims extracted (2)" in result
