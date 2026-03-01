"""
Diff-and-verify living document update tests — SPEC Section 17.3.

Tests document update logic using mocked Claude responses.
All tests mock external APIs and run without API keys.
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
import re


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiffMinimalChanges:
    """test_diff_minimal_changes: Verify diff output contains only changed sections."""

    def test_diff_only_changes_pricing_section(self, sample_living_document, sample_diff_output):
        """Diff output should reference only changed sections, not every section in the document."""
        from services.document_updater import parse_diff_output

        blocks = parse_diff_output(sample_diff_output)
        section_names = [b["section"] for b in blocks]

        # The diff touches Pricing and Decision Log — not all 9+ sections
        total_document_sections = 9  # Current State has ~9 subsections plus Decision Log etc.
        assert len(section_names) < total_document_sections, \
            "Diff should only touch changed sections, not the full document"

        # At least one block should be about Pricing (which changed)
        assert any("Pricing" in s for s in section_names), \
            "Diff should include a Pricing section update"

    def test_diff_produces_valid_blocks(self, sample_diff_output):
        """Parsed diff should produce valid, non-empty blocks."""
        from services.document_updater import parse_diff_output

        blocks = parse_diff_output(sample_diff_output)
        assert len(blocks) > 0, "Diff should produce at least one block"

        for block in blocks:
            assert "section" in block, "Block must have 'section'"
            assert "action" in block, "Block must have 'action'"
            assert "content" in block, "Block must have 'content'"
            assert block["section"] != "", "Section must be non-empty"
            assert block["action"] != "", "Action must be non-empty"


class TestDiffParseFormat:
    """test_diff_parse_format: Verify parse_diff_output() correctly parses SECTION/ACTION/CONTENT format."""

    def test_parses_update_position(self):
        diff_text = """SECTION: Current State → Target Market / Initial Customer
ACTION: UPDATE_POSITION
CONTENT:
**Current position:** Small nuclear plants in UK AND large oil & gas companies as secondary target.
"""
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output(diff_text)

        assert len(blocks) == 1
        assert blocks[0]["section"] == "Current State → Target Market / Initial Customer"
        assert blocks[0]["action"] == "UPDATE_POSITION"
        assert "Current position:" in blocks[0]["content"]

    def test_parses_add_changelog(self):
        diff_text = """SECTION: Current State → Pricing
ACTION: ADD_CHANGELOG
CONTENT:
- 2026-02-15: Hybrid pricing model under evaluation. Source: Session 5
"""
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output(diff_text)

        assert len(blocks) == 1
        assert blocks[0]["action"] == "ADD_CHANGELOG"
        assert "2026-02-15" in blocks[0]["content"]

    def test_parses_add_decision(self):
        diff_text = """SECTION: Decision Log
ACTION: ADD_DECISION
CONTENT:
### 2026-02-15 — Hybrid Pricing Model Under Evaluation
**Decision:** Evaluating hybrid pricing based on customer feedback.
**Why:** Three customers noted OpEx approval is faster for variable costs.
**Status:** Under evaluation
"""
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output(diff_text)

        assert len(blocks) == 1
        assert blocks[0]["action"] == "ADD_DECISION"
        assert "Hybrid Pricing" in blocks[0]["content"]

    def test_parses_multiple_blocks(self, sample_diff_output):
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output(sample_diff_output)

        assert len(blocks) >= 2, "Should parse multiple diff blocks"
        actions = [b["action"] for b in blocks]
        assert "UPDATE_POSITION" in actions or "ADD_CHANGELOG" in actions

    def test_empty_diff_returns_empty_list(self):
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output("")
        assert blocks == [], "Empty diff should return empty list"

    def test_malformed_diff_returns_empty_list(self):
        from services.document_updater import parse_diff_output
        blocks = parse_diff_output("This is not a valid diff format.")
        assert blocks == [], "Malformed diff should return empty list"


class TestChangelogAdded:
    """test_changelog_added: Verify changelog entry added when position updated."""

    def test_changelog_entry_appears_in_updated_doc(self, sample_living_document):
        diff_text = """SECTION: Current State → Pricing
ACTION: ADD_CHANGELOG
CONTENT:
- 2026-02-15: Hybrid pricing model under evaluation (base £15K + £0.10/doc). Source: Session 5
"""
        from services.document_updater import parse_diff_output, apply_diff

        blocks = parse_diff_output(diff_text)
        updated = apply_diff(sample_living_document, blocks)

        assert "Hybrid pricing model under evaluation" in updated, \
            "Changelog entry should appear in updated document"
        assert "2026-02-15" in updated, "Changelog date should appear in updated document"


class TestVerifyCatchesBadDiff:
    """test_verify_catches_bad_diff: Verify verification rejects a diff that would lose content."""

    def test_bad_diff_rejected(self, sample_living_document):
        bad_diff = "SECTION: Current State → Pricing\nACTION: UPDATE_POSITION\nCONTENT:\n(empty)"

        reject_response = """<verify_output>
  <verdict>REJECTED</verdict>
  <notes>The diff would remove the entire pricing section content without replacing it adequately.</notes>
  <issues>
    <issue>
      <description>Pricing section would lose all changelog entries.</description>
    </issue>
    <issue>
      <description>Current position would be replaced with placeholder text.</description>
    </issue>
  </issues>
</verify_output>"""

        mock_response = {
            "text": reject_response,
            "tokens_in": 400,
            "tokens_out": 200,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.document_updater import verify_diff
            result = verify_diff(sample_living_document, bad_diff, "Some new info")

        assert result["verified"] is False, "Bad diff should be rejected"
        assert len(result["issues"]) > 0, "Rejected diff should have issues listed"


class TestVerifyAcceptsGoodDiff:
    """test_verify_accepts_good_diff: Verify VERIFIED response passes validation."""

    def test_good_diff_accepted(self, sample_living_document, sample_diff_output):
        accept_response = """<verify_output>
  <verdict>VERIFIED</verdict>
  <notes>The diff correctly adds a changelog entry and updates the pricing position. All other sections are preserved. No content is lost.</notes>
  <issues/>
</verify_output>"""

        mock_response = {
            "text": accept_response,
            "tokens_in": 500,
            "tokens_out": 200,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.document_updater import verify_diff
            result = verify_diff(sample_living_document, sample_diff_output, "Pricing model update")

        assert result["verified"] is True, "Good diff should be accepted"
        assert result["notes"] != "", "Notes should be included for verified diff"


class TestDocumentPreservedAfterUpdate:
    """test_document_preserved_after_update: Verify all sections still present after applying update."""

    def test_all_sections_preserved(self, sample_living_document, sample_diff_output):
        from services.document_updater import parse_diff_output, apply_diff

        blocks = parse_diff_output(sample_diff_output)
        updated = apply_diff(sample_living_document, blocks)

        required_sections = [
            "## Current State",
            "### Target Market / Initial Customer",
            "### Value Proposition",
            "### Business Model / Revenue Model",
            "### Pricing",
            "### Technical Approach",
            "## Decision Log",
            "## Feedback Tracker",
            "## Dismissed Contradictions",
        ]

        for section in required_sections:
            assert section in updated, f"Section '{section}' should still be present after update"

    def test_unchanged_sections_not_modified(self, sample_living_document, sample_diff_output):
        """Sections not mentioned in the diff should be unchanged."""
        from services.document_updater import parse_diff_output, apply_diff

        blocks = parse_diff_output(sample_diff_output)
        updated = apply_diff(sample_living_document, blocks)

        # Target market section should be unchanged (diff only touches Pricing)
        original_tm_match = re.search(
            r"### Target Market / Initial Customer\n\*\*Current position:\*\* (.*?)\n",
            sample_living_document,
        )
        updated_tm_match = re.search(
            r"### Target Market / Initial Customer\n\*\*Current position:\*\* (.*?)\n",
            updated,
        )

        if original_tm_match and updated_tm_match:
            assert original_tm_match.group(1) == updated_tm_match.group(1), \
                "Target market section should be unchanged when only pricing is updated"


class TestRetryOnVerificationFailure:
    """test_retry_on_verification_failure: Verify retry logic when verification fails."""

    def test_retries_on_verification_failure(self, sample_living_document, sample_diff_output, tmp_path):
        """When verification fails, update_document should retry and succeed on second attempt."""
        reject_response_text = """<verify_output>
  <verdict>REJECTED</verdict>
  <notes>Diff is incomplete.</notes>
  <issues><issue><description>Missing changelog entry.</description></issue></issues>
</verify_output>"""

        accept_response_text = """<verify_output>
  <verdict>VERIFIED</verdict>
  <notes>Diff is now complete and correct.</notes>
  <issues/>
</verify_output>"""

        # First call: generate_diff, Second: verify (fail), Third: generate_diff (retry), Fourth: verify (pass)
        call_count = [0]

        def mock_sonnet_side_effect(*args, **kwargs):
            call_count[0] += 1
            # Calls: 1=generate, 2=verify(fail), 3=generate(retry), 4=verify(pass)
            if call_count[0] in (2,):
                return {"text": reject_response_text, "tokens_in": 300, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
            elif call_count[0] in (4,):
                return {"text": accept_response_text, "tokens_in": 300, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
            else:
                # Generate diff calls
                return {"text": sample_diff_output, "tokens_in": 500, "tokens_out": 400, "model": "claude-sonnet-4-20250514"}

        # Create a temp living doc
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        with patch("services.claude_client.call_sonnet", side_effect=mock_sonnet_side_effect), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.document_updater.LIVING_DOC_PATH", living_doc_path), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):
            from services.document_updater import update_document
            result = update_document("New pricing info.", update_reason="Session 5")

        assert result["success"] is True, "Should succeed after retry"
        assert call_count[0] >= 3, "Should have retried at least once"


class TestLivingDocReadWrite:
    """test_living_doc_read_write: Verify read_living_document() and write cycle."""

    def test_read_returns_string(self, tmp_path, sample_living_document):
        living_doc_path = tmp_path / "startup_brain.md"
        living_doc_path.write_text(sample_living_document, encoding="utf-8")

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path):
            from services.document_updater import read_living_document
            content = read_living_document()

        assert isinstance(content, str), "read_living_document should return a string"
        assert "## Current State" in content, "Should contain expected sections"

    def test_write_then_read_roundtrip(self, tmp_path, sample_living_document):
        living_doc_path = tmp_path / "startup_brain.md"

        with patch("services.document_updater.LIVING_DOC_PATH", living_doc_path):
            from services.document_updater import write_living_document, read_living_document
            write_living_document(sample_living_document)
            content = read_living_document()

        assert content == sample_living_document, "Read content should match written content"

    def test_read_nonexistent_returns_empty(self, tmp_path):
        nonexistent_path = tmp_path / "nonexistent.md"

        with patch("services.document_updater.LIVING_DOC_PATH", nonexistent_path):
            from services.document_updater import read_living_document
            content = read_living_document()

        assert content == "", "Non-existent file should return empty string"

    def test_write_creates_directories(self, tmp_path):
        nested_path = tmp_path / "nested" / "dir" / "startup_brain.md"

        with patch("services.document_updater.LIVING_DOC_PATH", nested_path):
            from services.document_updater import write_living_document, read_living_document
            write_living_document("# Test Document")
            content = read_living_document()

        assert content == "# Test Document", "Should create parent directories and write file"


class TestFallbackPaths:
    """Bug 24: Test _update_position and _add_changelog fallback when section not found."""

    def test_update_position_nonexistent_section(self, sample_living_document):
        from services.document_updater import _update_position
        result = _update_position(sample_living_document, "Current State → Nonexistent Section", "New content")
        assert result == sample_living_document, "Should return unmodified doc when section not found"

    def test_add_changelog_nonexistent_section(self, sample_living_document):
        from services.document_updater import _add_changelog
        result = _add_changelog(sample_living_document, "Current State → Nonexistent Section", "- New entry")
        assert result == sample_living_document, "Should return unmodified doc when section not found"
