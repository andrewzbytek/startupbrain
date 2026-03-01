"""
Unit tests for app/components/chat.py — pure classification/detection functions.
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

from app.components.chat import (
    _is_likely_transcript,
    _is_direct_correction,
    _is_quick_note,
    _strip_quick_note_prefix,
    _classify_query,
    TRANSCRIPT_SUGGEST_LENGTH,
)


# ---------------------------------------------------------------------------
# _is_likely_transcript
# ---------------------------------------------------------------------------

class TestIsLikelyTranscript:
    def test_short_text_returns_false(self):
        assert _is_likely_transcript("Short text.") is False

    def test_below_threshold_returns_false(self):
        text = "a " * 200  # 400 chars, below 500
        assert _is_likely_transcript(text) is False

    def test_long_text_without_signals_returns_false(self):
        # Long text but only one signal (word count >100), no colons+newlines, <10 newlines
        text = "word " * 120  # > 500 chars, > 100 words, but only 0 newlines
        assert _is_likely_transcript(text) is False

    def test_long_text_with_speaker_format_and_many_lines_returns_true(self):
        # speaker:line format with many lines
        lines = [f"Speaker{i}: This is line number {i} of the transcript discussion." for i in range(20)]
        text = "\n".join(lines)
        assert len(text) >= TRANSCRIPT_SUGGEST_LENGTH
        assert _is_likely_transcript(text) is True

    def test_long_text_all_three_signals(self):
        # Colon + >5 newlines, >10 newlines, >100 words -> all 3 signals
        lines = [f"Person{i}: We discussed topic {i} in detail with context." for i in range(25)]
        text = "\n".join(lines)
        assert _is_likely_transcript(text) is True

    def test_long_text_with_only_one_signal_returns_false(self):
        # >10 newlines but no colons, not many words
        text = "\n".join(["x"] * 15)
        # Pad to reach length threshold
        text += " " * (TRANSCRIPT_SUGGEST_LENGTH - len(text) + 10)
        # Only 1 signal: >10 newlines. No colons with >5 newlines, words < 100
        assert _is_likely_transcript(text) is False

    def test_exactly_at_threshold_boundary_with_signals_returns_true(self):
        # Build text that is exactly at threshold with 2+ signals
        lines = [f"Speaker{i}: Discussion point {i} about strategy and planning for startup." for i in range(15)]
        text = "\n".join(lines)
        # Ensure at threshold
        if len(text) < TRANSCRIPT_SUGGEST_LENGTH:
            text += "x" * (TRANSCRIPT_SUGGEST_LENGTH - len(text))
        assert _is_likely_transcript(text) is True


# ---------------------------------------------------------------------------
# _is_direct_correction
# ---------------------------------------------------------------------------

class TestIsDirectCorrection:
    def test_starts_with_no_comma(self):
        assert _is_direct_correction("No, it's actually $50K") is True

    def test_starts_with_actually_comma(self):
        assert _is_direct_correction("Actually, the price is different") is True

    def test_starts_with_wait_comma(self):
        assert _is_direct_correction("Wait, that's wrong") is True

    def test_starts_with_correction_colon(self):
        assert _is_direct_correction("Correction: the target is UK only") is True

    def test_contains_its_actually(self):
        assert _is_direct_correction("I think it's actually the other way") is True

    def test_contains_it_is_actually(self):
        assert _is_direct_correction("The pricing it is actually different") is True

    def test_contains_the_correct_answer_is(self):
        assert _is_direct_correction("No no, the correct answer is 100K") is True

    def test_contains_update_that_to(self):
        assert _is_direct_correction("Can you update that to 75K?") is True

    def test_contains_change_that_to(self):
        assert _is_direct_correction("Please change that to the new amount") is True

    def test_normal_question_returns_false(self):
        assert _is_direct_correction("What is our current pricing?") is False

    def test_empty_string_returns_false(self):
        assert _is_direct_correction("") is False

    def test_case_insensitive(self):
        assert _is_direct_correction("NO, it's wrong") is True
        assert _is_direct_correction("ACTUALLY, let me fix that") is True
        assert _is_direct_correction("WAIT, hold on") is True


# ---------------------------------------------------------------------------
# _classify_query
# ---------------------------------------------------------------------------

class TestClassifyQuery:
    def test_current_state_what_is_our_current(self):
        assert _classify_query("What is our current pricing?") == "current_state"

    def test_current_state_whats_our(self):
        assert _classify_query("What's our target market?") == "current_state"

    def test_current_state_where_are_we_on(self):
        assert _classify_query("Where are we on fundraising?") == "current_state"

    def test_current_state_current_position(self):
        assert _classify_query("Give me the current position on hiring") == "current_state"

    def test_current_state_right_now(self):
        assert _classify_query("What are we doing right now?") == "current_state"

    def test_pitch_keyword(self):
        assert _classify_query("Prepare a pitch for investors") == "pitch"

    def test_investor_keyword(self):
        assert _classify_query("Draft an investor summary") == "pitch"

    def test_elevator_keyword(self):
        assert _classify_query("Give me an elevator pitch") == "pitch"

    def test_analysis_keyword_analyze(self):
        assert _classify_query("Analyze our go-to-market strategy") == "analysis"

    def test_analysis_keyword_should_we(self):
        assert _classify_query("Should we pivot to a new market?") == "analysis"

    def test_analysis_keyword_recommend(self):
        assert _classify_query("What do you recommend for pricing?") == "analysis"

    def test_historical_when_did_we(self):
        assert _classify_query("When did we change our pricing?") == "historical"

    def test_historical_evolution(self):
        assert _classify_query("Show me the evolution of our target market") == "historical"

    def test_general_fallback(self):
        assert _classify_query("Hello how are you") == "general"

    def test_case_insensitive_matching(self):
        assert _classify_query("WHAT IS OUR CURRENT pricing?") == "current_state"
        assert _classify_query("PREPARE A PITCH") == "pitch"
        assert _classify_query("ANALYZE OUR STRATEGY") == "analysis"


# ---------------------------------------------------------------------------
# _is_quick_note
# ---------------------------------------------------------------------------

class TestIsQuickNote:
    def test_note_prefix(self):
        assert _is_quick_note("note: Met Sarah at TechCrunch") is True

    def test_remember_prefix(self):
        assert _is_quick_note("remember: Shell contact is John") is True

    def test_quick_note_prefix(self):
        assert _is_quick_note("quick note: pricing feedback from advisor") is True

    def test_jot_prefix(self):
        assert _is_quick_note("jot: follow up with investor next week") is True

    def test_fyi_prefix(self):
        assert _is_quick_note("fyi: competitor launched new product") is True

    def test_case_insensitive(self):
        assert _is_quick_note("NOTE: something important") is True
        assert _is_quick_note("Remember: something") is True
        assert _is_quick_note("FYI: heads up") is True

    def test_normal_question_returns_false(self):
        assert _is_quick_note("What is our current pricing?") is False

    def test_empty_string_returns_false(self):
        assert _is_quick_note("") is False

    def test_partial_match_returns_false(self):
        assert _is_quick_note("I noted something interesting") is False
        assert _is_quick_note("Can you remember this?") is False

    def test_no_space_after_colon(self):
        assert _is_quick_note("note:no space") is True

    def test_whitespace_handling(self):
        assert _is_quick_note("  note: with leading spaces  ") is True


# ---------------------------------------------------------------------------
# _strip_quick_note_prefix
# ---------------------------------------------------------------------------

class TestStripQuickNotePrefix:
    def test_strips_note_prefix(self):
        assert _strip_quick_note_prefix("note: Met Sarah at TechCrunch") == "Met Sarah at TechCrunch"

    def test_strips_remember_prefix(self):
        assert _strip_quick_note_prefix("remember: Shell contact is John") == "Shell contact is John"

    def test_strips_quick_note_prefix(self):
        assert _strip_quick_note_prefix("quick note: pricing feedback") == "pricing feedback"

    def test_strips_jot_prefix(self):
        assert _strip_quick_note_prefix("jot: follow up next week") == "follow up next week"

    def test_strips_fyi_prefix(self):
        assert _strip_quick_note_prefix("fyi: competitor launched") == "competitor launched"

    def test_case_insensitive_stripping(self):
        assert _strip_quick_note_prefix("NOTE: something") == "something"
        assert _strip_quick_note_prefix("REMEMBER: something") == "something"

    def test_preserves_content_without_prefix(self):
        assert _strip_quick_note_prefix("no prefix here") == "no prefix here"

    def test_handles_whitespace(self):
        assert _strip_quick_note_prefix("  note:  extra spaces  ") == "extra spaces"

    def test_quick_note_prefix_matched_before_note(self):
        # "quick note:" should match before "note:" would match on "quick note: text"
        result = _strip_quick_note_prefix("quick note: test content")
        assert result == "test content"
