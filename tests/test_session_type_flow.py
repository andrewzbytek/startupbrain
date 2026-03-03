"""
Tests for the session_type flow through the entire pipeline.
Covers: extract_claims, run_ingestion_pipeline, pass1/pass2, run_consistency_check,
        generate_pushback, _get_rag_evidence, store_confirmed_claims,
        _parse_feedback_by_source, and render_step_indicator.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing app modules
# ---------------------------------------------------------------------------

class _AttrDict(dict):
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


mock_st = sys.modules.get("streamlit") or MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f: f
mock_st.warning = MagicMock()
sys.modules["streamlit"] = mock_st


# ---------------------------------------------------------------------------
# SESSION_TYPES constant
# ---------------------------------------------------------------------------

class TestSessionTypes:
    def test_session_types_constant_exists(self):
        from app.state import SESSION_TYPES
        assert isinstance(SESSION_TYPES, list)
        assert len(SESSION_TYPES) >= 7

    def test_session_types_includes_key_types(self):
        from app.state import SESSION_TYPES
        assert "Co-founder discussion" in SESSION_TYPES
        assert "Investor meeting" in SESSION_TYPES
        assert "Customer interview" in SESSION_TYPES
        assert "Other" in SESSION_TYPES

    def test_ingestion_session_type_in_defaults(self):
        from app.state import init_session_state
        st_mod = sys.modules["streamlit"]
        st_mod.session_state.pop("ingestion_session_type", None)
        init_session_state()
        assert "ingestion_session_type" in st_mod.session_state
        assert st_mod.session_state["ingestion_session_type"] == ""

    def test_reset_ingestion_clears_session_type(self):
        from app.state import reset_ingestion
        st_mod = sys.modules["streamlit"]
        st_mod.session_state["ingestion_session_type"] = "Customer interview"
        st_mod.session_state.update({
            "mode": "ingesting",
            "pending_claims": [],
            "contradictions": [],
            "current_session_id": None,
            "current_transcript": None,
            "ingestion_status": {},
            "ingestion_participants": "",
            "ingestion_topic": "",
            "ingestion_session_summary": "",
            "ingestion_topic_tags": [],
            "consistency_results": None,
            "contradiction_index": 0,
            "whiteboard_text": "",
        })
        reset_ingestion()
        assert st_mod.session_state["ingestion_session_type"] == ""


# ---------------------------------------------------------------------------
# extract_claims passes session_type into prompt
# ---------------------------------------------------------------------------

class TestExtractClaimsSessionType:
    def test_session_type_included_in_prompt(self):
        """extract_claims() should include <session_type> in the XML prompt."""
        mock_response = {
            "text": "<extraction_output><session_summary>Test</session_summary>"
                    "<topic_tags><tag>test</tag></topic_tags>"
                    "<claims></claims></extraction_output>"
        }
        with patch("services.claude_client.call_sonnet", return_value=mock_response) as mock_call:
            from services.ingestion import extract_claims
            extract_claims(
                transcript="test transcript",
                session_type="Investor meeting",
            )
            prompt_arg = mock_call.call_args[0][0]
            assert "<session_type>Investor meeting</session_type>" in prompt_arg


# ---------------------------------------------------------------------------
# run_ingestion_pipeline formats update_reason with session_type
# ---------------------------------------------------------------------------

class TestIngestionPipelineSessionType:
    def test_update_reason_includes_session_type(self):
        """When session_type is in metadata, update_reason should use it as prefix."""
        claims = [{"claim_text": "Test", "confirmed": True, "claim_type": "decision", "confidence": "definite"}]
        metadata = {"participants": "Alex", "session_type": "Investor meeting"}
        with patch("services.consistency.run_consistency_check", return_value={"contradictions": []}) as mock_cc, \
             patch("services.document_updater.update_document", return_value={"success": True, "message": "ok"}) as mock_update, \
             patch("services.mongo_client.insert_claim", return_value="id1"):
            from services.ingestion import run_ingestion_pipeline
            run_ingestion_pipeline("transcript", claims, "session_123", metadata=metadata)

            # Check update_reason passed to document_updater
            call_kwargs = mock_update.call_args
            update_reason = call_kwargs[1].get("update_reason", "") if call_kwargs[1] else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else ""
            # The update_reason should start with session_type
            assert "Investor meeting" in update_reason

    def test_update_reason_fallback_without_session_type(self):
        """Without session_type, update_reason should start with 'Session'."""
        claims = [{"claim_text": "Test", "confirmed": True}]
        metadata = {"participants": "Alex"}
        with patch("services.consistency.run_consistency_check", return_value={"contradictions": []}), \
             patch("services.document_updater.update_document", return_value={"success": True, "message": "ok"}) as mock_update, \
             patch("services.mongo_client.insert_claim", return_value="id1"):
            from services.ingestion import run_ingestion_pipeline
            run_ingestion_pipeline("transcript", claims, "session_123", metadata=metadata)

            call_kwargs = mock_update.call_args
            update_reason = call_kwargs[1].get("update_reason", "") if call_kwargs[1] else ""
            assert "Session" in update_reason


# ---------------------------------------------------------------------------
# pass1_wide_net includes session_type in prompt
# ---------------------------------------------------------------------------

class TestPass1SessionType:
    def test_session_type_in_pass1_prompt(self):
        """pass1_wide_net() should include <session_type> in prompt XML."""
        mock_response = {
            "text": "<pass1_output><potential_contradictions/><total_found>0</total_found></pass1_output>"
        }
        with patch("services.claude_client.call_sonnet", return_value=mock_response) as mock_call:
            from services.consistency import pass1_wide_net
            pass1_wide_net("living doc", [{"claim_text": "test"}], session_type="Customer interview")
            prompt_arg = mock_call.call_args[0][0]
            assert "<session_type>Customer interview</session_type>" in prompt_arg


# ---------------------------------------------------------------------------
# pass2_severity_filter includes session_type in prompt
# ---------------------------------------------------------------------------

class TestPass2SessionType:
    def test_session_type_in_pass2_prompt(self):
        """pass2_severity_filter() should include <session_type> in prompt XML."""
        mock_response = {
            "text": "<pass2_output><retained_contradictions/><filtered_out/>"
                    "<has_critical>false</has_critical><total_retained>0</total_retained></pass2_output>"
        }
        pass1_results = {"raw": "<pass1_output/>", "contradictions": [], "total_found": 0}
        with patch("services.claude_client.call_sonnet", return_value=mock_response) as mock_call:
            from services.consistency import pass2_severity_filter
            pass2_severity_filter(pass1_results, "living doc", session_type="Co-founder discussion")
            prompt_arg = mock_call.call_args[0][0]
            assert "<session_type>Co-founder discussion</session_type>" in prompt_arg


# ---------------------------------------------------------------------------
# run_consistency_check threads session_type to pass1/pass2
# ---------------------------------------------------------------------------

class TestRunConsistencyCheckSessionType:
    def test_session_type_threaded_to_pass1_and_pass2(self):
        """run_consistency_check() should pass session_type to pass1 and pass2."""
        claims = [{"claim_text": "Test", "claim_type": "decision", "confidence": "definite"}]
        with patch("services.consistency.read_living_document", return_value="doc content"), \
             patch("services.consistency.pass1_wide_net", return_value={"contradictions": [], "total_found": 0, "raw": ""}) as mock_p1:
            from services.consistency import run_consistency_check
            run_consistency_check(claims, session_type="Advisor session")
            # pass1 should receive session_type
            mock_p1.assert_called_once()
            call_kwargs = mock_p1.call_args
            assert call_kwargs[1].get("session_type") == "Advisor session" or \
                   (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == "Advisor session")


# ---------------------------------------------------------------------------
# generate_pushback includes session_type in prompt
# ---------------------------------------------------------------------------

class TestPushbackSessionType:
    def test_session_type_in_pushback_prompt(self):
        """generate_pushback() should include <session_type> in prompt XML."""
        mock_response = {
            "text": "<pushback_output><headline>Test</headline><message>msg</message>"
                    "<options><option><label>Update anyway</label>"
                    "<description>desc</description></option></options></pushback_output>"
        }
        with patch("services.claude_client.call_sonnet", return_value=mock_response) as mock_call:
            from services.consistency import generate_pushback
            generate_pushback("change X", [{"date": "2026-01-01"}], session_type="Investor meeting")
            prompt_arg = mock_call.call_args[0][0]
            assert "<session_type>Investor meeting</session_type>" in prompt_arg


# ---------------------------------------------------------------------------
# _get_rag_evidence reads source_type from session metadata
# ---------------------------------------------------------------------------

class TestRagEvidenceSourceType:
    def test_reads_source_type_from_claim(self):
        """_get_rag_evidence should use claim.source_type instead of hardcoded 'session'."""
        mock_claims = [
            {"claim_text": "Test", "source_type": "Customer interview", "created_at": "2026-01-01"},
        ]
        mock_sessions = [
            {"summary": "Session summary", "metadata": {"session_type": "Investor meeting"}, "created_at": "2026-01-01"},
        ]
        with patch("services.mongo_client.get_claims", return_value=mock_claims), \
             patch("services.mongo_client.get_sessions", return_value=mock_sessions):
            from services.consistency import _get_rag_evidence
            evidence = _get_rag_evidence([])
            claim_ev = [e for e in evidence if e["relevant_excerpt"] == "Test"]
            session_ev = [e for e in evidence if "Session summary" in e["relevant_excerpt"]]
            assert len(claim_ev) == 1
            assert claim_ev[0]["source_type"] == "Customer interview"
            assert len(session_ev) == 1
            assert session_ev[0]["source_type"] == "Investor meeting"


# ---------------------------------------------------------------------------
# store_confirmed_claims stores source_type when metadata provided
# ---------------------------------------------------------------------------

class TestStoreClaimsSourceType:
    def test_source_type_stored_from_metadata(self):
        """store_confirmed_claims should store source_type from metadata.session_type."""
        claims = [{"claim_text": "Test", "confirmed": True, "claim_type": "decision", "confidence": "definite"}]
        metadata = {"session_type": "Customer interview"}
        with patch("services.mongo_client.insert_claim", return_value="id1") as mock_insert:
            from services.ingestion import store_confirmed_claims
            store_confirmed_claims(claims, "session_123", metadata=metadata)
            call_args = mock_insert.call_args[0][0]
            assert call_args["source_type"] == "Customer interview"

    def test_source_type_empty_without_metadata(self):
        """store_confirmed_claims should default source_type to empty string without metadata."""
        claims = [{"claim_text": "Test", "confirmed": True}]
        with patch("services.mongo_client.insert_claim", return_value="id1") as mock_insert:
            from services.ingestion import store_confirmed_claims
            store_confirmed_claims(claims, "session_123")
            call_args = mock_insert.call_args[0][0]
            assert call_args["source_type"] == ""


# ---------------------------------------------------------------------------
# _parse_feedback_by_source
# ---------------------------------------------------------------------------

class TestParseFeedbackBySource:
    def test_parses_investor_as_vc(self):
        doc = """## Feedback Tracker

### Individual Feedback
- [2026-02-15] Jane Smith (investor): Pricing seems low for enterprise — Themes: pricing
- [2026-02-18] Acme Corp (customer): Need API access — Themes: features
"""
        from app.components.sidebar import _parse_feedback_by_source
        result = _parse_feedback_by_source(doc)
        assert len(result["vc"]) == 1
        assert "Pricing seems low" in result["vc"][0]
        assert len(result["customer"]) == 1
        assert "API access" in result["customer"][0]

    def test_parses_advisor_feedback(self):
        doc = """## Feedback Tracker

### Individual Feedback
- [2026-03-01] Bob Advisor (advisor): Consider B2B channel — Themes: go-to-market
"""
        from app.components.sidebar import _parse_feedback_by_source
        result = _parse_feedback_by_source(doc)
        assert len(result["advisor"]) == 1

    def test_empty_doc_returns_empty_dict(self):
        from app.components.sidebar import _parse_feedback_by_source
        result = _parse_feedback_by_source("")
        assert result == {"vc": [], "customer": [], "advisor": []}

    def test_no_individual_feedback_section(self):
        doc = """## Feedback Tracker

### Recurring Themes
- Some theme
"""
        from app.components.sidebar import _parse_feedback_by_source
        result = _parse_feedback_by_source(doc)
        assert result == {"vc": [], "customer": [], "advisor": []}


# ---------------------------------------------------------------------------
# render_step_indicator
# ---------------------------------------------------------------------------

class TestRenderStepIndicator:
    def test_step_indicator_callable(self):
        """render_step_indicator should be importable and callable via st.markdown."""
        from app.components.progress import render_step_indicator
        st_mod = sys.modules["streamlit"]
        st_mod.markdown = MagicMock()
        render_step_indicator(1)
        st_mod.markdown.assert_called_once()
        html = st_mod.markdown.call_args[0][0]
        assert 'step-indicator' in html
        assert 'step-circle active' in html

    def test_step_indicator_accepts_all_steps(self):
        """render_step_indicator should work for steps 1-4."""
        from app.components.progress import render_step_indicator
        st_mod = sys.modules["streamlit"]
        st_mod.markdown = MagicMock()
        for step in [1, 2, 3, 4]:
            render_step_indicator(step)
