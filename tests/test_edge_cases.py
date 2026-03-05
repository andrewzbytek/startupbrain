"""
Boundary condition and edge case tests for Startup Brain.
Tests XML parsing, whiteboard detection, document structure, and dismissed filtering.
"""

import sys
from unittest.mock import MagicMock, patch

# Mock streamlit before importing any services
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = {}
sys.modules.setdefault("streamlit", mock_st)

import pytest

from services.consistency import _extract_tag as consistency_extract_tag, check_dismissed
from services.ingestion import _extract_tag as ingestion_extract_tag
from services.document_updater import (
    _add_decision,
    _add_dismissed,
    _add_feedback,
    _update_position,
    apply_diff,
)


# ---------------------------------------------------------------------------
# XML Parsing Edge Cases
# ---------------------------------------------------------------------------

class TestXMLParsing:
    """Test _extract_tag from consistency.py and ingestion.py with edge cases."""

    def test_nested_tags_returns_inner(self):
        """Nested identical tags: non-greedy regex returns first inner match."""
        text = "<a><a>inner</a></a>"
        result = consistency_extract_tag(text, "a")
        assert result == "<a>inner"

    def test_empty_tag(self):
        """Empty tag content returns empty string."""
        text = "<tag></tag>"
        result = consistency_extract_tag(text, "tag")
        assert result == ""

    def test_no_match_returns_empty(self):
        """Text without the tag returns empty string."""
        text = "no tags here at all"
        result = consistency_extract_tag(text, "missing")
        assert result == ""

    def test_multiline_content(self):
        """Multiline content between tags is extracted."""
        text = "<notes>\nline one\nline two\nline three\n</notes>"
        result = consistency_extract_tag(text, "notes")
        assert "line one" in result
        assert "line three" in result

    def test_special_characters_ampersand(self):
        """Ampersands in tag content are preserved."""
        text = "<data>R&amp;D &amp; Operations</data>"
        result = consistency_extract_tag(text, "data")
        assert "R&amp;D" in result

    def test_special_characters_angle_brackets(self):
        """Escaped angle brackets in tag content."""
        text = "<data>value &lt; 100 &gt; 0</data>"
        result = consistency_extract_tag(text, "data")
        assert "&lt; 100" in result

    def test_special_characters_quotes(self):
        """Quotes in tag content are preserved."""
        text = '<data>She said "hello" and \'goodbye\'</data>'
        result = consistency_extract_tag(text, "data")
        assert '"hello"' in result

    def test_unicode_characters(self):
        """Unicode characters in tag content."""
        text = "<data>Price: \u00a350,000 per facility \u2014 confirmed</data>"
        result = consistency_extract_tag(text, "data")
        assert "\u00a350,000" in result
        assert "\u2014" in result

    def test_ingestion_extract_tag_consistent(self):
        """ingestion._extract_tag behaves the same as consistency._extract_tag."""
        text = "<claim_text>Test claim about pricing</claim_text>"
        assert ingestion_extract_tag(text, "claim_text") == consistency_extract_tag(text, "claim_text")

    def test_whitespace_only_content_stripped(self):
        """Whitespace-only content is stripped to empty string."""
        text = "<tag>   \n\t  </tag>"
        result = consistency_extract_tag(text, "tag")
        assert result == ""

    def test_tag_with_surrounding_text(self):
        """Extract tag from text with content before and after."""
        text = "prefix <id>42</id> suffix"
        result = consistency_extract_tag(text, "id")
        assert result == "42"


# ---------------------------------------------------------------------------
# Whiteboard Detection Edge Cases
# ---------------------------------------------------------------------------

class TestWhiteboardDetection:
    """Test image format detection via magic bytes in process_whiteboard."""

    @patch("services.mongo_client.insert_one", return_value="mock_id")
    @patch("services.claude_client.call_sonnet")
    @patch("services.claude_client.load_prompt", return_value="mock prompt")
    def test_jpeg_magic_bytes(self, mock_load, mock_call, mock_insert):
        """JPEG magic bytes b'\\xff\\xd8\\xff' should produce media_type image/jpeg."""
        mock_call.return_value = {
            "text": "<extraction_confidence>high</extraction_confidence>",
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "claude-sonnet-4-20250514",
        }
        image_bytes = b"\xff\xd8\xff" + b"\x00" * 100
        from services.ingestion import process_whiteboard
        result = process_whiteboard(image_bytes, transcript_context="test")
        # Verify call_sonnet was called with images containing jpeg media type
        call_args = mock_call.call_args
        images = call_args.kwargs.get("images", [])
        assert len(images) == 1
        assert images[0]["media_type"] == "image/jpeg"

    @patch("services.mongo_client.insert_one", return_value="mock_id")
    @patch("services.claude_client.call_sonnet")
    @patch("services.claude_client.load_prompt", return_value="mock prompt")
    def test_png_magic_bytes(self, mock_load, mock_call, mock_insert):
        """PNG magic bytes should produce media_type image/png."""
        mock_call.return_value = {
            "text": "<extraction_confidence>medium</extraction_confidence>",
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "claude-sonnet-4-20250514",
        }
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        from services.ingestion import process_whiteboard
        result = process_whiteboard(image_bytes, transcript_context="test")
        call_args = mock_call.call_args
        images = call_args.kwargs.get("images", [])
        assert len(images) == 1
        assert images[0]["media_type"] == "image/png"

    @patch("services.mongo_client.insert_one", return_value="mock_id")
    @patch("services.claude_client.call_sonnet")
    @patch("services.claude_client.load_prompt", return_value="mock prompt")
    def test_unknown_format_defaults_to_jpeg(self, mock_load, mock_call, mock_insert):
        """Unknown image format (random bytes) defaults to image/jpeg."""
        mock_call.return_value = {
            "text": "<extraction_confidence>low</extraction_confidence>",
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "claude-sonnet-4-20250514",
        }
        image_bytes = b"\x00\x01\x02\x03\x04" + b"\x00" * 100
        from services.ingestion import process_whiteboard
        result = process_whiteboard(image_bytes, transcript_context="test")
        call_args = mock_call.call_args
        images = call_args.kwargs.get("images", [])
        assert len(images) == 1
        assert images[0]["media_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# Document Structure Edge Cases
# ---------------------------------------------------------------------------

class TestDocumentStructure:
    """Test document modification functions with missing sections."""

    def test_add_decision_missing_section_creates_it(self):
        """When Decision Log is missing, _add_decision appends it."""
        doc = "# Startup Brain\n\n## Current State\nSome content here.\n"
        result = _add_decision(doc, "### 2026-03-01 - New Decision\n**Decision:** Test\n**Why:** Test\n**Status:** Active")
        assert "## Decision Log" in result
        assert "New Decision" in result

    def test_add_feedback_missing_section_creates_it(self):
        """When Feedback Tracker is missing, _add_feedback appends it."""
        doc = "# Startup Brain\n\n## Current State\nSome content here.\n"
        result = _add_feedback(doc, "- 2026-03-01 | Test feedback")
        assert "## Feedback Tracker" in result
        assert "Test feedback" in result

    def test_add_dismissed_missing_section_creates_it(self):
        """When Dismissed Contradictions is missing, _add_dismissed appends it."""
        doc = "# Startup Brain\n\n## Current State\nSome content here.\n"
        result = _add_dismissed(doc, "- 2026-03-01: Dismissed test claim")
        assert "## Dismissed Contradictions" in result
        assert "Dismissed test claim" in result

    def test_add_dismissed_replaces_placeholder(self):
        """Placeholder '[No dismissed contradictions]' is replaced, not appended to."""
        doc = (
            "# Startup Brain\n\n"
            "## Dismissed Contradictions\n"
            "[No dismissed contradictions]\n"
        )
        result = _add_dismissed(doc, "- 2026-03-01: New dismissed item")
        assert "[No dismissed contradictions]" not in result
        assert "New dismissed item" in result

    def test_update_position_arrow_notation(self):
        """Arrow notation 'Current State -> Pricing' finds the right subsection."""
        doc = (
            "## Current State\n\n"
            "### Pricing\n"
            "**Current position:** Old pricing info here.\n"
            "**Changelog:**\n"
            "- 2026-02-01: Initial pricing\n"
        )
        new_pos = "**Current position:** New pricing: $100K per facility."
        result = _update_position(doc, "Current State \u2192 Pricing", new_pos)
        assert "New pricing: $100K" in result

    def test_update_position_nonexistent_section_returns_unchanged(self):
        """_update_position with non-matching section returns doc unchanged."""
        doc = "## Current State\n\n### Pricing\n**Current position:** Old.\n"
        result = _update_position(doc, "Current State \u2192 Nonexistent", "**Current position:** New.")
        assert result == doc

    def test_apply_diff_empty_blocks(self):
        """apply_diff with empty block list returns document unchanged."""
        doc = "# Test Document\n\nSome content."
        result = apply_diff(doc, [])
        assert result == doc

    def test_apply_diff_multiple_actions(self):
        """apply_diff handles multiple block types in sequence."""
        doc = (
            "## Current State\n\n"
            "### Pricing\n"
            "**Current position:** Old price.\n"
            "**Changelog:**\n"
            "- 2026-02-01: Initial\n\n"
            "## Decision Log\n\n"
            "### 2026-02-01 - Old Decision\n**Decision:** Old\n\n"
            "## Feedback Tracker\n\nOld feedback.\n"
        )
        blocks = [
            {"section": "Decision Log", "action": "ADD_DECISION", "content": "### 2026-03-01 - New\n**Decision:** New"},
            {"section": "Feedback Tracker", "action": "ADD_FEEDBACK", "content": "- 2026-03-01 | New feedback"},
        ]
        result = apply_diff(doc, blocks)
        assert "New feedback" in result
        assert "### 2026-03-01 - New" in result


# ---------------------------------------------------------------------------
# Dismissed Filtering Edge Cases
# ---------------------------------------------------------------------------

class TestDismissedFiltering:
    """Test check_dismissed with various dismissed section states."""

    def test_empty_dismissed_section_returns_all(self):
        """Empty Dismissed Contradictions section returns all contradictions."""
        doc = "## Dismissed Contradictions\n\n## Next Section\n"
        contradictions = [
            {"new_claim": "We should target enterprise clients with large budgets"},
            {"new_claim": "Pricing should be usage-based per document"},
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 2

    def test_no_dismissed_section_returns_all(self):
        """Document without Dismissed Contradictions section returns all."""
        doc = "# Startup Brain\n\n## Current State\nContent here.\n"
        contradictions = [
            {"new_claim": "We should target enterprise clients"},
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 1

    def test_all_claims_match_dismissed_returns_empty(self):
        """When all claims have high word overlap with dismissed, returns empty list."""
        doc = (
            "## Dismissed Contradictions\n"
            "- 2026-02-12: Claim that enterprise accounts should target "
            "larger budgets was dismissed because small nuclear operators "
            "have shorter procurement cycles.\n"
        )
        contradictions = [
            {"new_claim": "enterprise accounts should target larger budgets procurement cycles"},
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 0

    def test_no_claims_match_dismissed_returns_all(self):
        """When no claims overlap with dismissed section, all are returned."""
        doc = (
            "## Dismissed Contradictions\n"
            "- 2026-02-12: Claim about branding was dismissed.\n"
        )
        contradictions = [
            {"new_claim": "We should increase pricing to seventy-five thousand per facility"},
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 1

    def test_partial_overlap_mixed_results(self):
        """Mix of matching and non-matching claims."""
        doc = (
            "## Dismissed Contradictions\n"
            "- Claim that enterprise accounts should target larger budgets "
            "because enterprise sales cycles are faster.\n"
        )
        contradictions = [
            # High overlap with dismissed text
            {"new_claim": "enterprise accounts should target larger budgets because enterprise sales cycles"},
            # No overlap
            {"new_claim": "We should pivot to healthcare compliance software"},
        ]
        result = check_dismissed(contradictions, doc)
        # The healthcare claim should remain, enterprise claim may be filtered
        healthcare_remaining = any("healthcare" in c["new_claim"] for c in result)
        assert healthcare_remaining

    def test_placeholder_text_returns_all(self):
        """Placeholder '[No dismissed contradictions]' treated as empty."""
        doc = (
            "## Dismissed Contradictions\n"
            "[No dismissed contradictions]\n"
        )
        contradictions = [
            {"new_claim": "Any claim at all"},
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 1

    def test_empty_contradictions_list(self):
        """Empty contradictions list returns empty list."""
        doc = "## Dismissed Contradictions\nSome dismissed stuff.\n"
        result = check_dismissed([], doc)
        assert result == []

    def test_claim_with_short_words_only(self):
        """Claims with only short words (<=4 chars) pass through.

        When all words are <= 4 chars, len(words)==0, so no word-overlap
        check is possible. These claims cannot match the dismissed section
        and should be kept (not silently dropped).
        """
        doc = (
            "## Dismissed Contradictions\n"
            "- Some long dismissed text about things.\n"
        )
        contradictions = [
            {"new_claim": "we do it now"},  # all words <= 4 chars
        ]
        result = check_dismissed(contradictions, doc)
        # Short-word claims pass through — they can't match dismissed text
        assert len(result) == 1
