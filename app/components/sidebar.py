"""
Dashboard sidebar for Startup Brain (legacy shell).
All parser functions moved to app.components._parsers.
Sidebar rendering replaced by top_bar.py and dashboard.py.
"""

from app.components._parsers import (  # noqa: F401
    _escape_latex,
    _parse_current_state,
    _parse_recent_changelog,
    _parse_feedback_themes,
    _parse_feedback_by_source,
    _DATE_PATTERN,
    _extract_date,
    _parse_hypotheses,
    _parse_contacts,
    _SECTION_KEYWORDS,
    _find_changelog_tensions,
    _find_dismissed_tensions,
    _find_decision_tensions,
    _parse_tensions,
    _read_living_document,
)


def render_sidebar():
    """No-op. Sidebar rendering replaced by top bar and dashboard."""
    pass
