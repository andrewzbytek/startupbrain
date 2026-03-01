"""
Unit tests for services/document_updater.py — focusing on functions NOT covered by test_update.py.
All tests run without API keys, MongoDB, or network access.
"""

import sys
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)


# ---------------------------------------------------------------------------
# generate_diff tests
# ---------------------------------------------------------------------------

class TestGenerateDiff:
    """Tests for generate_diff: calls Sonnet with diff_generate prompt."""

    def test_calls_sonnet(self):
        """Should call call_sonnet with the diff_generate prompt."""
        with patch("services.claude_client.call_sonnet", return_value={"text": "SECTION: ...", "tokens_in": 100, "tokens_out": 50, "model": "m"}) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="diff template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.document_updater import generate_diff
            result = generate_diff("current doc", "new info", "session update")
            mock_call.assert_called_once()
            assert result == "SECTION: ..."

    def test_passes_current_doc_and_new_info(self):
        """Should include current_doc and new_info in the prompt."""
        with patch("services.claude_client.call_sonnet", return_value={"text": "diff"}) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.document_updater import generate_diff
            generate_diff("DOCUMENT CONTENT", "NEW INFORMATION", "reason")
            prompt_arg = mock_call.call_args[0][0]
            assert "DOCUMENT CONTENT" in prompt_arg
            assert "NEW INFORMATION" in prompt_arg

    def test_returns_string(self):
        """Should return the text from the API response."""
        with patch("services.claude_client.call_sonnet", return_value={"text": "output"}), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.document_updater import generate_diff
            result = generate_diff("doc", "info")
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# verify_diff tests (supplement to test_update.py)
# ---------------------------------------------------------------------------

class TestVerifyDiffUnit:
    """Additional verify_diff tests not in test_update.py."""

    def test_verified_verdict(self):
        """VERIFIED verdict should set verified=True."""
        xml = "<verify_output><verdict>VERIFIED</verdict><notes>All good</notes></verify_output>"
        with patch("services.claude_client.call_sonnet", return_value={"text": xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}), \
             patch("services.claude_client.load_prompt", return_value="t"):
            from services.document_updater import verify_diff
            result = verify_diff("orig", "diff", "info")
            assert result["verified"] is True
            assert result["notes"] == "All good"

    def test_issues_found_verdict(self):
        """ISSUES_FOUND should set verified=False with issues list."""
        xml = (
            "<verify_output><verdict>ISSUES_FOUND</verdict>"
            "<notes>Problems found</notes>"
            "<issues><issue><description>Missing entry</description></issue>"
            "<issue><description>Wrong section</description></issue></issues>"
            "</verify_output>"
        )
        with patch("services.claude_client.call_sonnet", return_value={"text": xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}), \
             patch("services.claude_client.load_prompt", return_value="t"):
            from services.document_updater import verify_diff
            result = verify_diff("orig", "diff", "info")
            assert result["verified"] is False
            assert len(result["issues"]) == 2
            assert "Missing entry" in result["issues"]
            assert "Wrong section" in result["issues"]

    def test_notes_extracted(self):
        """Notes should be extracted from the response."""
        xml = "<verify_output><verdict>VERIFIED</verdict><notes>Some notes here</notes></verify_output>"
        with patch("services.claude_client.call_sonnet", return_value={"text": xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}), \
             patch("services.claude_client.load_prompt", return_value="t"):
            from services.document_updater import verify_diff
            result = verify_diff("orig", "diff", "info")
            assert result["notes"] == "Some notes here"


# ---------------------------------------------------------------------------
# _add_decision tests
# ---------------------------------------------------------------------------

class TestAddDecision:
    """Tests for _add_decision: adds entries to Decision Log."""

    def test_adds_to_decision_log(self, sample_living_document):
        """Should add decision content to the Decision Log section."""
        from services.document_updater import _add_decision
        new_decision = "### 2026-02-20 — New Decision\n**Decision:** We decided X.\n**Why:** Because Y.\n**Status:** Active"
        result = _add_decision(sample_living_document, new_decision)
        assert "New Decision" in result
        assert "## Decision Log" in result

    def test_creates_section_if_missing(self):
        """Should create Decision Log section if it doesn't exist."""
        from services.document_updater import _add_decision
        doc_without = "# Startup Brain\n\n## Current State\nContent here."
        result = _add_decision(doc_without, "### New Decision\n**Decision:** X")
        assert "## Decision Log" in result
        assert "New Decision" in result


# ---------------------------------------------------------------------------
# _add_feedback tests
# ---------------------------------------------------------------------------

class TestAddFeedback:
    """Tests for _add_feedback: adds entries to Feedback Tracker."""

    def test_adds_to_feedback_section(self, sample_living_document):
        """Should add feedback content to the Feedback Tracker section."""
        from services.document_updater import _add_feedback
        new_feedback = "- 2026-02-20 | Jane (VC): Positive on team."
        result = _add_feedback(sample_living_document, new_feedback)
        assert "Jane (VC)" in result
        assert "## Feedback Tracker" in result

    def test_creates_section_if_missing(self):
        """Should create Feedback Tracker section if it doesn't exist."""
        from services.document_updater import _add_feedback
        doc_without = "# Startup Brain\n\n## Current State\nContent."
        result = _add_feedback(doc_without, "- Feedback entry")
        assert "## Feedback Tracker" in result
        assert "Feedback entry" in result


# ---------------------------------------------------------------------------
# _add_dismissed tests
# ---------------------------------------------------------------------------

class TestAddDismissed:
    """Tests for _add_dismissed: adds entries to Dismissed Contradictions."""

    def test_adds_to_dismissed_section(self, sample_living_document):
        """Should add dismissed content to the Dismissed Contradictions section."""
        from services.document_updater import _add_dismissed
        new_dismissed = "- 2026-02-20: Dismissed idea X — reason: Y"
        result = _add_dismissed(sample_living_document, new_dismissed)
        assert "Dismissed idea X" in result

    def test_replaces_no_dismissed_placeholder(self):
        """Should replace '[No dismissed contradictions]' placeholder."""
        from services.document_updater import _add_dismissed
        doc = "# Doc\n\n## Dismissed Contradictions\n[No dismissed contradictions]\n"
        result = _add_dismissed(doc, "- 2026-02-20: First dismissal")
        assert "[No dismissed contradictions]" not in result
        assert "First dismissal" in result

    def test_creates_section_if_missing(self):
        """Should create Dismissed Contradictions section if missing."""
        from services.document_updater import _add_dismissed
        doc = "# Startup Brain\n\n## Current State\nContent."
        result = _add_dismissed(doc, "- Dismissed entry")
        assert "## Dismissed Contradictions" in result
        assert "Dismissed entry" in result


# ---------------------------------------------------------------------------
# _add_section tests
# ---------------------------------------------------------------------------

class TestAddSection:
    """Tests for _add_section: adds new sections to Current State."""

    def test_inserts_before_decision_log(self, sample_living_document):
        """Should insert new section content before Decision Log."""
        from services.document_updater import _add_section
        new_section = "### New Subsection\n**Current position:** Something new."
        result = _add_section(sample_living_document, "Current State → New Subsection", new_section)
        # New section should appear before Decision Log
        new_idx = result.index("New Subsection")
        decision_idx = result.index("## Decision Log")
        assert new_idx < decision_idx

    def test_appends_to_end_if_no_decision_log(self):
        """Should append to end if no Decision Log section exists."""
        from services.document_updater import _add_section
        doc = "# Startup Brain\n\n## Current State\nContent."
        result = _add_section(doc, "New Section", "### New\nContent here.")
        assert result.endswith("### New\nContent here.\n")


# ---------------------------------------------------------------------------
# _git_commit tests
# ---------------------------------------------------------------------------

class TestGitCommit:
    """Tests for _git_commit: commits living document to git."""

    def test_success_returns_true(self):
        """Should return True on successful git commands."""
        from services.document_updater import _git_commit
        with patch("services.document_updater.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _git_commit("test commit")
            assert result is True
            assert mock_run.call_count == 2  # git add + git commit

    def test_called_process_error_returns_false(self):
        """Should return False when git command fails."""
        from services.document_updater import _git_commit
        with patch("services.document_updater.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = _git_commit("test commit")
            assert result is False

    def test_generic_exception_returns_false(self):
        """Should return False on unexpected exceptions (e.g., not a git repo)."""
        from services.document_updater import _git_commit
        with patch("services.document_updater.subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = _git_commit("test commit")
            assert result is False


# ---------------------------------------------------------------------------
# update_document tests (supplement to test_update.py retry test)
# ---------------------------------------------------------------------------

class TestUpdateDocumentUnit:
    """Additional update_document tests focusing on edge cases."""

    def test_returns_failure_on_empty_document(self, tmp_path):
        """Should return failure when living document is empty."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text("", encoding="utf-8")

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path):
            from services.document_updater import update_document
            result = update_document("new info")
            assert result["success"] is False
            assert "not found" in result["message"].lower()

    def test_returns_failure_on_empty_diff_blocks(self, tmp_path, sample_living_document):
        """Should return failure when diff produces no parseable blocks."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        verified_xml = "<verify_output><verdict>VERIFIED</verdict><notes>ok</notes></verify_output>"

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.claude_client.call_sonnet", return_value={"text": "no valid diff here", "tokens_in": 100, "tokens_out": 50, "model": "m"}), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            # Override verify_diff to return verified=True
            with patch("services.document_updater.verify_diff", return_value={"verified": True, "notes": "", "issues": [], "raw": ""}):
                from services.document_updater import update_document
                result = update_document("new info")
                assert result["success"] is False
                assert "no changes" in result["message"].lower()

    def test_max_retries_exhausted(self, tmp_path, sample_living_document):
        """Should return failure after max retries when verification keeps failing."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        fail_xml = "<verify_output><verdict>REJECTED</verdict><notes>bad</notes><issues><issue><description>Problem</description></issue></issues></verify_output>"

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.claude_client.call_sonnet", return_value={"text": fail_xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.document_updater import update_document
            result = update_document("new info", max_retries=1)
            assert result["success"] is False
            assert "failed" in result["message"].lower()

    def test_success_with_changes_applied(self, tmp_path, sample_living_document):
        """Should return success with correct changes_applied count."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        diff_text = (
            "SECTION: Current State \u2192 Pricing\n"
            "ACTION: ADD_CHANGELOG\n"
            "CONTENT:\n"
            "- 2026-02-28: Test entry\n"
        )
        verified_xml = "<verify_output><verdict>VERIFIED</verdict><notes>ok</notes></verify_output>"

        call_count = [0]

        def mock_sonnet(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # generate_diff
                return {"text": diff_text, "tokens_in": 100, "tokens_out": 50, "model": "m"}
            else:  # verify_diff
                return {"text": verified_xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.claude_client.call_sonnet", side_effect=mock_sonnet), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True) as mock_upsert:
            from services.document_updater import update_document
            result = update_document("new info", update_reason="test")
            assert result["success"] is True
            assert result["changes_applied"] >= 1
            # Verify MongoDB upsert was called
            mock_upsert.assert_called_once()

    def test_write_permission_error(self, tmp_path, sample_living_document):
        """Should handle write permission errors gracefully."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        diff_text = (
            "SECTION: Decision Log\n"
            "ACTION: ADD_DECISION\n"
            "CONTENT:\n"
            "### 2026-02-28 \u2014 Test\n**Decision:** X\n**Why:** Y\n**Status:** Active\n"
        )
        verified_xml = "<verify_output><verdict>VERIFIED</verdict><notes>ok</notes></verify_output>"

        call_count = [0]

        def mock_sonnet(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"text": diff_text, "tokens_in": 100, "tokens_out": 50, "model": "m"}
            else:
                return {"text": verified_xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.claude_client.call_sonnet", side_effect=mock_sonnet), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.document_updater.write_living_document", side_effect=PermissionError("read-only")):
            from services.document_updater import update_document
            result = update_document("new info")
            assert result["success"] is False
            assert "failed to write" in result["message"].lower()

    def test_git_commit_called(self, tmp_path, sample_living_document):
        """Should call _git_commit after successful update."""
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        diff_text = (
            "SECTION: Decision Log\n"
            "ACTION: ADD_DECISION\n"
            "CONTENT:\n"
            "### 2026-02-28 \u2014 Test Decision\n**Decision:** X\n**Why:** Y\n**Status:** Active\n"
        )
        verified_xml = "<verify_output><verdict>VERIFIED</verdict><notes>ok</notes></verify_output>"

        call_count = [0]

        def mock_sonnet(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"text": diff_text, "tokens_in": 100, "tokens_out": 50, "model": "m"}
            else:
                return {"text": verified_xml, "tokens_in": 100, "tokens_out": 50, "model": "m"}

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.claude_client.call_sonnet", side_effect=mock_sonnet), \
             patch("services.claude_client.load_prompt", return_value="t"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.document_updater._git_commit", return_value=True) as mock_git, \
             patch("services.mongo_client.upsert_living_document", return_value=True):
            from services.document_updater import update_document
            result = update_document("new info", update_reason="session update")
            mock_git.assert_called_once()
            assert result["success"] is True
