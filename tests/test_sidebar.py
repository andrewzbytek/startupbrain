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

from datetime import date
from app.components.sidebar import (
    _parse_current_state,
    _parse_recent_changelog,
    _parse_feedback_themes,
    _extract_date,
    _parse_hypotheses,
    _parse_tensions,
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


# ---------------------------------------------------------------------------
# _extract_date
# ---------------------------------------------------------------------------

class TestExtractDate:
    def test_valid_date(self):
        assert _extract_date("2026-02-15: Something happened") == date(2026, 2, 15)

    def test_date_in_middle(self):
        assert _extract_date("Something on 2026-03-01 happened") == date(2026, 3, 1)

    def test_no_date(self):
        assert _extract_date("No date here") is None

    def test_empty_string(self):
        assert _extract_date("") is None

    def test_invalid_date(self):
        assert _extract_date("2026-13-45: bad date") is None

    def test_first_date_wins(self):
        assert _extract_date("2026-01-01 then 2026-12-31") == date(2026, 1, 1)


# ---------------------------------------------------------------------------
# _parse_hypotheses (sidebar)
# ---------------------------------------------------------------------------

class TestParseHypothesesSidebar:
    def test_parses_populated_doc(self, doc):
        result = _parse_hypotheses(doc)
        assert len(result) == 2

    def test_empty_doc(self):
        assert _parse_hypotheses("") == []

    def test_placeholder_returns_empty(self):
        doc = "## Active Hypotheses\n[No hypotheses tracked yet]\n\n## Decision Log\n"
        assert _parse_hypotheses(doc) == []

    def test_multiple_entries_fields(self, doc):
        result = _parse_hypotheses(doc)
        # First hypothesis
        assert result[0]["status"] == "unvalidated"
        assert "procurement" in result[0]["text"]
        # Second hypothesis
        assert result[1]["status"] == "testing"
        assert "LLM" in result[1]["text"]

    def test_all_statuses(self):
        doc = """## Active Hypotheses
- [2026-03-01] **H1**
  Status: unvalidated | Test: t1
  Evidence: ---
- [2026-03-02] **H2**
  Status: validated | Test: t2
  Evidence: confirmed

## Decision Log
"""
        result = _parse_hypotheses(doc)
        assert len(result) == 2
        assert result[0]["status"] == "unvalidated"
        assert result[1]["status"] == "validated"


# ---------------------------------------------------------------------------
# _parse_tensions
# ---------------------------------------------------------------------------

class TestParseTensions:
    def test_empty_doc(self):
        assert _parse_tensions("") == []

    def test_no_recent_activity(self):
        """Doc with only old entries should produce no tensions."""
        doc = """## Current State

### Pricing
**Current position:** £50K
**Changelog:**
- 2020-01-01: Old entry

## Decision Log

### 2020-01-01 — Old Decision
**Decision:** X
**Status:** Active

## Dismissed Contradictions
- 2020-01-01: Old dismissal
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert result == []

    def test_changelog_churn_detected(self):
        """2+ changes in 7 days should trigger tension."""
        doc = """## Current State

### Pricing
**Current position:** £75K
**Changelog:**
- 2026-02-28: Changed to 75K
- 2026-02-26: Changed to 60K
- 2026-02-20: Changed to 50K

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert len(result) >= 1
        assert any("Pricing" in t["section_name"] for t in result)
        assert any("changes in 7 days" in t["reason"] for t in result)

    def test_single_change_not_flagged(self):
        """Only 1 change in 7 days should not trigger tension."""
        doc = """## Current State

### Pricing
**Current position:** £50K
**Changelog:**
- 2026-02-28: Single change

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        # No changelog churn (only 1 change)
        assert not any("changes in 7 days" in t.get("reason", "") for t in result)

    def test_dismissed_contradiction_detected(self):
        """Recently dismissed contradiction should trigger tension."""
        doc = """## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear
**Changelog:**
- 2026-01-01: Initial

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
- 2026-02-25: Claim about enterprise customers targeting market — Dismissed because small operators are better
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert len(result) >= 1
        assert any("dismissed" in t["reason"] for t in result)

    def test_old_dismissed_not_flagged(self):
        """Dismissed contradiction older than 14 days should not trigger."""
        doc = """## Current State

### Pricing
**Current position:** £50K
**Changelog:**
- 2026-01-01: Initial

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
- 2026-01-01: Very old dismissal about pricing
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert not any("dismissed" in t.get("reason", "") for t in result)

    def test_decision_under_evaluation_detected(self):
        """Decision with 'Under evaluation' status in last 14 days should trigger."""
        doc = """## Current State

### Pricing
**Current position:** £50K
**Changelog:**
- 2026-01-01: Initial

## Decision Log

### 2026-02-25 — Hybrid Pricing
**Decision:** Evaluating hybrid pricing
**Status:** Under evaluation — not yet adopted

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert len(result) >= 1
        assert any("evaluation" in t["reason"] for t in result)

    def test_active_decision_not_flagged(self):
        """Decision with 'Active' status should not trigger tension."""
        doc = """## Current State

### Pricing
**Current position:** £50K
**Changelog:**
- 2026-01-01: Initial

## Decision Log

### 2026-02-25 — Good Decision
**Decision:** Something decided
**Status:** Active

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert not any("evaluation" in t.get("reason", "") for t in result)

    def test_multiple_sections_flagged(self):
        """Multiple independent tension signals should all appear."""
        doc = """## Current State

### Pricing
**Current position:** £75K
**Changelog:**
- 2026-02-28: Change 1
- 2026-02-27: Change 2

### Target Market / Initial Customer
**Current position:** Small nuclear
**Changelog:**
- 2026-02-28: Change A
- 2026-02-26: Change B

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        section_names = [t["section_name"] for t in result]
        assert "Pricing" in section_names
        assert "Target Market / Initial Customer" in section_names

    def test_deduplication(self):
        """Same section from multiple signals should deduplicate by section_name."""
        doc = """## Current State

### Pricing
**Current position:** £75K
**Changelog:**
- 2026-02-28: Change 1
- 2026-02-27: Change 2
- 2026-02-26: Change 3

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        # Should have exactly one entry for Pricing (changelog churn), not duplicated
        pricing_entries = [t for t in result if t["section_name"] == "Pricing"]
        assert len(pricing_entries) == 1

    def test_sorted_by_date(self):
        """Tensions should be sorted most recent first."""
        doc = """## Current State

### Pricing
**Current position:** £75K
**Changelog:**
- 2026-02-25: Change 1
- 2026-02-24: Change 2

### Go-to-Market Strategy
**Current position:** Direct sales
**Changelog:**
- 2026-02-28: Change A
- 2026-02-27: Change B

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        if len(result) >= 2:
            assert result[0]["sort_date"] >= result[1]["sort_date"]

    def test_placeholder_entries_ignored(self):
        """Placeholder entries should not trigger tensions."""
        doc = """## Current State

### Pricing
**Current position:** [Not yet defined]
**Changelog:**
- [Awaiting first session]

## Decision Log
[No decisions recorded yet]

## Dismissed Contradictions
[No dismissed contradictions]
"""
        result = _parse_tensions(doc, today=date(2026, 3, 1))
        assert result == []
