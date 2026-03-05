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
    _is_hypothesis,
    _is_hypothesis_status_update,
    _get_system_prompt,
    TRANSCRIPT_SUGGEST_LENGTH,
    _extract_session_type_filter,
    _extract_date_filter,
    _extract_participant_filter,
    _format_recall_context,
    _MAX_RECALL_CHARS,
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


# ---------------------------------------------------------------------------
# _classify_query — "challenge" type
# ---------------------------------------------------------------------------

class TestClassifyQueryChallenge:
    def test_challenge_keyword(self):
        assert _classify_query("Challenge our pricing model") == "challenge"

    def test_poke_holes(self):
        assert _classify_query("Poke holes in our go-to-market") == "challenge"

    def test_devils_advocate(self):
        assert _classify_query("Play devil's advocate on our MVP scope") == "challenge"

    def test_stress_test(self):
        assert _classify_query("Stress test our assumptions") == "challenge"

    def test_what_am_i_missing(self):
        assert _classify_query("What am I missing about pricing?") == "challenge"

    def test_what_are_we_missing(self):
        assert _classify_query("What are we missing in our strategy?") == "challenge"

    def test_pushback(self):
        assert _classify_query("Give me some pushback on our target market") == "challenge"

    def test_challenge_before_analysis(self):
        # "challenge" should be detected before "analysis" keywords
        # "challenge" contains no analysis keywords, just verify priority
        assert _classify_query("challenge this strategy") == "challenge"

    def test_existing_analysis_still_works(self):
        assert _classify_query("Analyze our go-to-market strategy") == "analysis"

    def test_existing_classifications_unchanged(self):
        assert _classify_query("What is our current pricing?") == "current_state"
        assert _classify_query("Prepare a pitch") == "pitch"
        assert _classify_query("When did we change pricing?") == "historical"
        assert _classify_query("Hello") == "general"


# ---------------------------------------------------------------------------
# System prompt — Socratic content
# ---------------------------------------------------------------------------

class TestSystemPromptSocratic:
    def test_contains_socratic_pushback(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc"):
            prompt = _get_system_prompt()
            assert "Socratic Pushback" in prompt

    def test_contains_context_surfacing(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc"):
            prompt = _get_system_prompt()
            assert "Related context" in prompt

    def test_contains_feedback_echo(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc"):
            prompt = _get_system_prompt()
            assert "Feedback Echo" in prompt

    def test_contains_never_block(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc"):
            prompt = _get_system_prompt()
            assert "NEVER block" in prompt

    def test_contains_tone_calibration(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc"):
            prompt = _get_system_prompt()
            assert "Tone Calibration" in prompt

    def test_wraps_doc_in_startup_brain_tags(self):
        from unittest.mock import patch
        with patch("services.document_updater.read_living_document", return_value="test doc content"):
            prompt = _get_system_prompt()
            assert "<startup_brain>" in prompt
            assert "test doc content" in prompt
            assert "</startup_brain>" in prompt

    def test_includes_book_framework_when_loaded(self):
        from unittest.mock import patch
        import streamlit as _st
        _st.session_state["book_crosscheck_content"] = "book content here"
        with patch("services.document_updater.read_living_document", return_value="doc"):
            prompt = _get_system_prompt()
            assert "<book_framework>" in prompt
            assert "book content here" in prompt
        _st.session_state["book_crosscheck_content"] = ""

    def test_no_book_framework_when_empty(self):
        from unittest.mock import patch
        import streamlit as _st
        _st.session_state["book_crosscheck_content"] = ""
        with patch("services.document_updater.read_living_document", return_value="doc"):
            prompt = _get_system_prompt()
            assert "<book_framework>" not in prompt

    def test_system_prompt_both_brains(self):
        """When chat_brain_context is 'both', system prompt should include both documents."""
        from unittest.mock import patch
        import streamlit as _st
        _st.session_state["chat_brain_context"] = "both"
        _st.session_state["book_crosscheck_content"] = ""

        def mock_read(brain="pitch"):
            if brain == "pitch":
                return "PITCH DOCUMENT CONTENT"
            elif brain == "ops":
                return "OPS DOCUMENT CONTENT"
            return ""

        with patch("services.document_updater.read_living_document", side_effect=mock_read):
            prompt = _get_system_prompt()
            assert "PITCH DOCUMENT CONTENT" in prompt
            assert "OPS DOCUMENT CONTENT" in prompt

        # Restore default
        _st.session_state["chat_brain_context"] = "pitch"


# ---------------------------------------------------------------------------
# _is_hypothesis / _is_hypothesis_status_update in chat.py
# ---------------------------------------------------------------------------

class TestIsHypothesisChat:
    def test_hypothesis_prefix(self):
        assert _is_hypothesis("hypothesis: test") is True

    def test_normal_text_false(self):
        assert _is_hypothesis("What is our hypothesis?") is False

    def test_empty_false(self):
        assert _is_hypothesis("") is False


class TestIsHypothesisStatusUpdateChat:
    def test_validated(self):
        assert _is_hypothesis_status_update("validated: test") is True

    def test_invalidated(self):
        assert _is_hypothesis_status_update("invalidated: test") is True

    def test_normal_false(self):
        assert _is_hypothesis_status_update("test") is False


# ---------------------------------------------------------------------------
# _classify_query — "recall" type
# ---------------------------------------------------------------------------

class TestClassifyQueryRecall:
    def test_list_all_meetings(self):
        assert _classify_query("list all meetings") == "recall"

    def test_what_did_investors_say(self):
        """'what did investors say' is a recall keyword — should NOT fall through to pitch."""
        assert _classify_query("what did investors say") == "recall"

    def test_what_did_customers_say(self):
        assert _classify_query("what did customers say") == "recall"

    def test_investor_feedback(self):
        assert _classify_query("investor feedback") == "recall"

    def test_meeting_with_name(self):
        assert _classify_query("meeting with Sarah") == "recall"

    def test_recap(self):
        assert _classify_query("recap") == "recall"

    def test_all_customer_meetings(self):
        assert _classify_query("all customer meetings") == "recall"

    def test_pitch_keyword_still_works(self):
        """'Prepare a pitch for investors' has no recall keywords — falls through to pitch."""
        assert _classify_query("Prepare a pitch for investors") == "pitch"

    def test_investor_summary_still_pitch(self):
        """'Draft an investor summary' has no recall keywords — falls through to pitch."""
        assert _classify_query("Draft an investor summary") == "pitch"

    def test_existing_current_state_unchanged(self):
        assert _classify_query("What is our current pricing?") == "current_state"

    def test_existing_analysis_unchanged(self):
        assert _classify_query("Analyze our go-to-market strategy") == "analysis"

    def test_existing_challenge_unchanged(self):
        assert _classify_query("Challenge our pricing model") == "challenge"

    def test_existing_general_unchanged(self):
        assert _classify_query("Hello how are you") == "general"


# ---------------------------------------------------------------------------
# _extract_session_type_filter
# ---------------------------------------------------------------------------

class TestExtractSessionTypeFilter:
    def test_investor_keyword(self):
        assert _extract_session_type_filter("investor") == "Investor"

    def test_vc_maps_to_investor(self):
        assert _extract_session_type_filter("vc meetings") == "Investor"

    def test_customer_maps_to_customer_interview(self):
        assert _extract_session_type_filter("customer interviews") == "Customer interview"

    def test_advisor_keyword(self):
        assert _extract_session_type_filter("advisor") == "Advisor"

    def test_no_match_returns_none(self):
        assert _extract_session_type_filter("hello world") is None

    def test_cofounder_keyword(self):
        assert _extract_session_type_filter("cofounder sync") == "Co-founder"

    def test_internal_keyword(self):
        assert _extract_session_type_filter("internal discussion") == "Internal"


# ---------------------------------------------------------------------------
# _extract_date_filter
# ---------------------------------------------------------------------------

class TestExtractDateFilter:
    def test_iso_date(self):
        result = _extract_date_filter("meetings on 2026-03-05")
        assert result == {"from": "2026-03-05", "to": "2026-03-05"}

    def test_month_day_with_ordinal(self):
        from unittest.mock import patch, MagicMock
        from datetime import datetime as real_datetime, timezone

        mock_now = real_datetime(2026, 3, 15, tzinfo=timezone.utc)
        with patch("app.components.chat.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            # re-import not needed since _extract_date_filter uses datetime at call time
            result = _extract_date_filter("meetings in march 5th")
        assert result == {"from": "2026-03-05", "to": "2026-03-05"}

    def test_this_month_returns_range(self):
        result = _extract_date_filter("this month")
        assert result is not None
        assert "from" in result
        assert "to" in result
        # "from" should be first of the current month (ends with -01)
        assert result["from"].endswith("-01")

    def test_last_week_returns_range(self):
        result = _extract_date_filter("last week")
        assert result is not None
        assert "from" in result
        assert "to" in result
        # "from" should be earlier than "to"
        assert result["from"] < result["to"]

    def test_no_date_returns_none(self):
        assert _extract_date_filter("hello world") is None

    def test_iso_date_embedded_in_sentence(self):
        result = _extract_date_filter("what happened on 2026-01-15 with the investor")
        assert result == {"from": "2026-01-15", "to": "2026-01-15"}


# ---------------------------------------------------------------------------
# _extract_participant_filter
# ---------------------------------------------------------------------------

class TestExtractParticipantFilter:
    def test_meeting_with_single_name(self):
        assert _extract_participant_filter("meeting with sarah") == "sarah"

    def test_meetings_with_two_names(self):
        assert _extract_participant_filter("meetings with john doe") == "john doe"

    def test_no_match_returns_none(self):
        assert _extract_participant_filter("what happened yesterday") is None

    def test_meeting_with_at_end_of_sentence(self):
        result = _extract_participant_filter("show me the meeting with alex")
        assert result == "alex"


# ---------------------------------------------------------------------------
# _format_recall_context
# ---------------------------------------------------------------------------

class TestFormatRecallContext:
    def test_empty_sessions(self):
        result = _format_recall_context([])
        assert "<session_recall>" in result
        assert "<session_count>0</session_count>" in result
        assert "</session_recall>" in result

    def test_sessions_with_data(self):
        sessions = [
            {
                "session_date": "2026-03-01",
                "summary": "Discussed pricing strategy",
                "metadata": {
                    "session_type": "Investor",
                    "participants": "Sarah Chen",
                    "tags": ["pricing"],
                },
            }
        ]
        result = _format_recall_context(sessions)
        assert "<sessions>" in result
        assert "Investor" in result
        assert "Sarah Chen" in result
        assert "Discussed pricing strategy" in result
        assert "pricing" in result
        assert "<session_count>1</session_count>" in result

    def test_with_claims(self):
        sessions = [{"session_date": "2026-03-01", "metadata": {}}]
        claims = [
            {
                "claim_type": "decision",
                "claim_text": "Pricing set to $500/month",
                "who_said_it": "Andrew",
                "confidence": "definite",
            }
        ]
        result = _format_recall_context(sessions, claims=claims)
        assert "<claims>" in result
        assert "Pricing set to $500/month" in result
        assert "Andrew" in result
        assert "definite" in result
        assert "</claims>" in result

    def test_with_feedback(self):
        sessions = [{"session_date": "2026-03-01", "metadata": {}}]
        feedback = [
            {"source_type": "investor", "summary": "Liked the pricing model"}
        ]
        result = _format_recall_context(sessions, feedback=feedback)
        assert "<feedback>" in result
        assert "investor" in result
        assert "Liked the pricing model" in result
        assert "</feedback>" in result

    def test_respects_max_chars_limit(self):
        # Create sessions that produce a very long context
        sessions = []
        for i in range(200):
            sessions.append({
                "session_date": f"2026-01-{(i % 28) + 1:02d}",
                "summary": f"This is a very detailed summary for session number {i} " * 10,
                "metadata": {
                    "session_type": "Investor",
                    "participants": f"Person {i}",
                    "tags": [f"tag_{i}"],
                },
            })
        result = _format_recall_context(sessions)
        # Result should be truncated to _MAX_RECALL_CHARS + closing tag
        assert len(result) <= _MAX_RECALL_CHARS + len("\n</session_recall>") + 10
        # Should still end with the closing tag
        assert result.rstrip().endswith("</session_recall>")

    def test_session_with_datetime_object(self):
        from datetime import datetime, timezone
        sessions = [
            {
                "session_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "summary": "Test session",
                "metadata": {"session_type": "Internal"},
            }
        ]
        result = _format_recall_context(sessions)
        assert "2026-03-01" in result

    def test_session_falls_back_to_created_at(self):
        sessions = [
            {
                "created_at": "2026-02-15",
                "summary": "Fallback date test",
                "metadata": {"session_type": "Advisor"},
            }
        ]
        result = _format_recall_context(sessions)
        assert "2026-02-15" in result


# ---------------------------------------------------------------------------
# _resolve_contradiction Decision Log formatting
# ---------------------------------------------------------------------------

class TestResolveContradictionDecisionFormat:
    """Tests for _resolve_contradiction: structured Decision Log entries."""

    def _run_resolve(self, action, explanation=""):
        """Helper: call _resolve_contradiction and capture the decision_entry passed to _add_decision."""
        import sys
        from unittest.mock import patch, MagicMock

        st_mod = sys.modules["streamlit"]
        # Ensure session_state supports real dict .get() (not MagicMock)
        if not isinstance(st_mod.session_state, dict):
            st_mod.session_state = _AttrDict()
        st_mod.session_state["ingestion_participants"] = "Andrew, Danny"

        contradiction = {
            "existing_section": "Current State → Pricing",
            "tension_description": "Price changed from 50K to 75K",
            "new_claim": "Price is 75K",
            "existing_position": "Price is 50K",
        }

        captured = {}

        def capture_add_decision(doc, entry, brain="pitch"):
            captured["entry"] = entry
            return doc  # pass-through

        with patch("services.document_updater.update_document"), \
             patch("services.document_updater.read_living_document", return_value="## Decision Log\n"), \
             patch("services.document_updater.write_living_document"), \
             patch("services.mongo_client.upsert_living_document"), \
             patch("services.document_updater._git_commit"), \
             patch("services.document_updater._add_decision", side_effect=capture_add_decision), \
             patch("services.document_updater._add_dismissed"):
            from app.components.chat import _resolve_contradiction
            _resolve_contradiction(contradiction, action, "Price is 75K", explanation)

        return captured.get("entry", "")

    def test_update_action_has_structured_header(self):
        """'update' action decision entry should use ### header format."""
        entry = self._run_resolve("update")
        assert entry.startswith("### ")
        assert "Resolved: Current State" in entry

    def test_update_action_has_decision_fields(self):
        """'update' action decision entry should contain **Decision:** and other fields."""
        entry = self._run_resolve("update")
        assert "**Decision:**" in entry
        assert "**Alternatives considered:**" in entry
        assert "**Why alternatives were rejected:**" in entry
        assert "**Context:**" in entry
        assert "**Participants:** Andrew, Danny" in entry

    def test_explain_action_has_structured_header(self):
        """'explain' action decision entry should use ### header format."""
        entry = self._run_resolve("explain", explanation="Customer feedback changed our mind")
        assert entry.startswith("### ")
        assert "Resolved: Current State" in entry

    def test_explain_action_includes_user_explanation(self):
        """'explain' action should include the user's explanation in 'Why alternatives were rejected'."""
        entry = self._run_resolve("explain", explanation="Customer feedback changed our mind")
        assert "Customer feedback changed our mind" in entry
        assert "**Why alternatives were rejected:** Customer feedback changed our mind" in entry

    def test_explain_action_has_participants(self):
        """'explain' action decision entry should include participants."""
        entry = self._run_resolve("explain", explanation="Reason here")
        assert "**Participants:** Andrew, Danny" in entry
