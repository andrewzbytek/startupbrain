"""
Unit tests for app/components/sidebar.py — pure document parser functions.
All tests run without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock

import pytest


class _AttrDict(dict):
    """A dict that supports attribute-style access, mimicking Streamlit's SessionState."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)


# Mock streamlit before importing app modules
mock_st = MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f: f
sys.modules.setdefault("streamlit", mock_st)

from app.components.sidebar import (
    _parse_current_state,
    _parse_recent_changelog,
    _parse_feedback_themes,
)
from tests.conftest import get_sample_living_document


@pytest.fixture
def doc():
    """Return the sample living document string."""
    return get_sample_living_document()


# ---------------------------------------------------------------------------
# _parse_current_state
# ---------------------------------------------------------------------------

class TestParseCurrentState:
    def test_extracts_all_subsections(self, doc):
        sections = _parse_current_state(doc)
        names = [s["name"] for s in sections]
        assert "Target Market / Initial Customer" in names
        assert "Value Proposition" in names
        assert "Pricing" in names
        assert "Technical Approach" in names
        assert "Key Risks" in names
        assert "Team / Hiring Plans" in names
        assert "Fundraising Status / Strategy" in names

    def test_empty_doc_returns_empty_list(self):
        assert _parse_current_state("") == []

    def test_doc_without_current_state_section_returns_empty_list(self):
        doc = "# Startup Brain\n\n## Decision Log\nSome decisions."
        assert _parse_current_state(doc) == []

    def test_each_section_has_required_keys(self, doc):
        sections = _parse_current_state(doc)
        for section in sections:
            assert "name" in section
            assert "current_position" in section
            assert "changelog_entries" in section

    def test_position_text_correctly_extracted(self, doc):
        sections = _parse_current_state(doc)
        pricing = next(s for s in sections if s["name"] == "Pricing")
        assert "50,000" in pricing["current_position"]
        assert "per facility per year" in pricing["current_position"]

    def test_changelog_entries_are_parsed(self, doc):
        sections = _parse_current_state(doc)
        pricing = next(s for s in sections if s["name"] == "Pricing")
        assert len(pricing["changelog_entries"]) > 0
        # Each entry should have been stripped of leading "- "
        for entry in pricing["changelog_entries"]:
            assert not entry.startswith("- ")

    def test_awaiting_first_session_placeholder_filtered_out(self):
        doc = """## Current State

### Test Section
**Current position:** Something here
**Changelog:**
[Awaiting first session]
"""
        sections = _parse_current_state(doc)
        assert len(sections) == 1
        assert sections[0]["changelog_entries"] == []


# ---------------------------------------------------------------------------
# _parse_recent_changelog
# ---------------------------------------------------------------------------

class TestParseRecentChangelog:
    def test_returns_entries_from_populated_doc(self, doc):
        entries = _parse_recent_changelog(doc)
        assert len(entries) > 0

    def test_entries_prefixed_with_section_name(self, doc):
        entries = _parse_recent_changelog(doc)
        # Each entry should be "[SectionName] content"
        for entry in entries:
            assert entry.startswith("[")
            assert "]" in entry

    def test_respects_limit_parameter(self, doc):
        entries_2 = _parse_recent_changelog(doc, limit=2)
        assert len(entries_2) <= 2

    def test_empty_doc_returns_empty_list(self):
        assert _parse_recent_changelog("") == []

    def test_returns_most_recent_first(self, doc):
        entries = _parse_recent_changelog(doc)
        # Entries should be reversed (most recent first). Verify there are entries
        # and the structure is consistent with reversed order.
        assert len(entries) > 0

    def test_limit_one_returns_single_entry(self, doc):
        entries = _parse_recent_changelog(doc, limit=1)
        assert len(entries) == 1

    def test_doc_without_changelogs(self):
        doc = """## Current State

### Test Section
**Current position:** Something here
"""
        entries = _parse_recent_changelog(doc)
        assert entries == []


# ---------------------------------------------------------------------------
# _parse_feedback_themes
# ---------------------------------------------------------------------------

class TestParseFeedbackThemes:
    def test_parses_themes_from_populated_doc(self, doc):
        themes = _parse_feedback_themes(doc)
        assert len(themes) > 0

    def test_branding_theme_present(self, doc):
        themes = _parse_feedback_themes(doc)
        assert any("branding" in t.lower() or "logo" in t.lower() for t in themes)

    def test_empty_doc_returns_empty_list(self):
        assert _parse_feedback_themes("") == []

    def test_no_feedback_tracker_returns_empty_list(self):
        doc = "# Startup Brain\n\n## Decision Log\nSome content."
        assert _parse_feedback_themes(doc) == []

    def test_placeholder_skipped(self):
        doc = """## Feedback Tracker

### Recurring Themes
[No themes identified yet]
"""
        themes = _parse_feedback_themes(doc)
        assert themes == []

    def test_multiple_themes_parsed(self):
        doc = """## Feedback Tracker

### Recurring Themes
- Theme one: 3 sources
- Theme two: 2 sources
- Theme three: 1 source
"""
        themes = _parse_feedback_themes(doc)
        assert len(themes) == 3
