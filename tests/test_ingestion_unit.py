"""
Unit tests for services/ingestion.py.
All tests run without API keys, network access, or MongoDB.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing modules that use it
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)


# ---------------------------------------------------------------------------
# _extract_tag tests
# ---------------------------------------------------------------------------

class TestExtractTag:
    """Tests for _extract_tag: extracts content from XML-like tags."""

    def test_basic_extraction(self):
        from services.ingestion import _extract_tag
        assert _extract_tag("<name>Alice</name>", "name") == "Alice"

    def test_nested_tags(self):
        from services.ingestion import _extract_tag
        text = "<outer><inner>value</inner></outer>"
        assert _extract_tag(text, "inner") == "value"

    def test_empty_tag_content(self):
        from services.ingestion import _extract_tag
        assert _extract_tag("<name></name>", "name") == ""

    def test_no_match_returns_empty(self):
        from services.ingestion import _extract_tag
        assert _extract_tag("no tags here", "name") == ""

    def test_multiline_content(self):
        from services.ingestion import _extract_tag
        text = "<desc>\nline1\nline2\n</desc>"
        result = _extract_tag(text, "desc")
        assert "line1" in result
        assert "line2" in result

    def test_strips_whitespace(self):
        from services.ingestion import _extract_tag
        assert _extract_tag("<tag>  spaced  </tag>", "tag") == "spaced"


# ---------------------------------------------------------------------------
# extract_claims tests
# ---------------------------------------------------------------------------

class TestExtractClaims:
    """Tests for extract_claims: calls Claude to extract structured claims."""

    MOCK_EXTRACTION_XML = (
        "<extraction_output>"
        "<session_summary>We discussed pricing</session_summary>"
        "<topic_tags><tag>pricing</tag><tag>strategy</tag></topic_tags>"
        "<claims>"
        "<claim>"
        "<claim_text>Annual pricing at 50K</claim_text>"
        "<claim_type>decision</claim_type>"
        "<confidence>definite</confidence>"
        "<who_said_it>Alex</who_said_it>"
        "<topic_tags><tag>pricing</tag></topic_tags>"
        "</claim>"
        "<claim>"
        "<claim_text>Consider usage-based model</claim_text>"
        "<claim_type>question</claim_type>"
        "<confidence>speculative</confidence>"
        "<who_said_it>Jordan</who_said_it>"
        "<topic_tags><tag>pricing</tag><tag>business-model</tag></topic_tags>"
        "</claim>"
        "</claims>"
        "</extraction_output>"
    )

    def _mock_call_sonnet(self, xml_text):
        return {
            "text": xml_text,
            "tokens_in": 500,
            "tokens_out": 300,
            "model": "claude-sonnet-4-20250514",
        }

    def test_success_with_mock_response(self):
        """Should parse claims from valid XML response."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet(self.MOCK_EXTRACTION_XML)), \
             patch("services.claude_client.load_prompt", return_value="prompt template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            result = extract_claims("We talked about pricing")
            assert result["session_summary"] == "We discussed pricing"
            assert len(result["claims"]) == 2
            assert result["claims"][0]["claim_text"] == "Annual pricing at 50K"

    def test_empty_transcript_still_calls_api(self):
        """Even an empty transcript should call the API."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet("<extraction_output></extraction_output>")) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            extract_claims("")
            mock_call.assert_called_once()

    def test_whiteboard_text_included_in_prompt(self):
        """Whiteboard text should be embedded in the prompt."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet("<extraction_output></extraction_output>")) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            extract_claims("transcript", whiteboard_text="diagram notes")
            call_args = mock_call.call_args
            prompt_text = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
            assert "diagram notes" in prompt_text

    def test_topic_tags_parsed(self):
        """Topic tags should be parsed from the XML response."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet(self.MOCK_EXTRACTION_XML)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            result = extract_claims("test")
            assert "pricing" in result["topic_tags"]
            assert "strategy" in result["topic_tags"]

    def test_claim_fields_validated(self):
        """Each claim should have all required fields."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet(self.MOCK_EXTRACTION_XML)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            result = extract_claims("test")
            claim = result["claims"][0]
            assert "claim_text" in claim
            assert "claim_type" in claim
            assert "confidence" in claim
            assert "who_said_it" in claim
            assert "topic_tags" in claim
            assert "confirmed" in claim

    def test_empty_claim_text_skipped(self):
        """Claims with empty claim_text should be skipped."""
        xml_with_empty = (
            "<extraction_output>"
            "<session_summary>test</session_summary>"
            "<topic_tags></topic_tags>"
            "<claims>"
            "<claim><claim_text></claim_text><claim_type>decision</claim_type>"
            "<confidence>definite</confidence><who_said_it></who_said_it>"
            "<topic_tags></topic_tags></claim>"
            "<claim><claim_text>Real claim</claim_text><claim_type>decision</claim_type>"
            "<confidence>definite</confidence><who_said_it>Alex</who_said_it>"
            "<topic_tags></topic_tags></claim>"
            "</claims>"
            "</extraction_output>"
        )
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet(xml_with_empty)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            result = extract_claims("test")
            assert len(result["claims"]) == 1
            assert result["claims"][0]["claim_text"] == "Real claim"

    def test_raw_response_included(self):
        """The raw API response text should be included in the result."""
        with patch("services.claude_client.call_sonnet", return_value=self._mock_call_sonnet(self.MOCK_EXTRACTION_XML)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x):
            from services.ingestion import extract_claims
            result = extract_claims("test")
            assert result["raw"] == self.MOCK_EXTRACTION_XML


# ---------------------------------------------------------------------------
# process_whiteboard tests
# ---------------------------------------------------------------------------

class TestProcessWhiteboard:
    """Tests for process_whiteboard: processes whiteboard images with vision."""

    MOCK_WHITEBOARD_XML = (
        "<whiteboard_output>"
        "<extraction_confidence>high</extraction_confidence>"
        "<legibility_notes>Clear handwriting</legibility_notes>"
        "<extracted_content>"
        "<item><type>text</type><content>Target: 10 facilities</content>"
        "<location>top-left</location><legibility>high</legibility>"
        "<emphasis>underlined</emphasis></item>"
        "</extracted_content>"
        "<confirmation_message>Extracted 1 item from whiteboard.</confirmation_message>"
        "</whiteboard_output>"
    )

    def _mock_result(self, xml_text):
        return {
            "text": xml_text,
            "tokens_in": 800,
            "tokens_out": 400,
            "model": "claude-sonnet-4-20250514",
        }

    def test_jpeg_magic_bytes(self):
        """JPEG files should be detected by magic bytes."""
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 100

        with patch("services.claude_client.call_sonnet", return_value=self._mock_result(self.MOCK_WHITEBOARD_XML)) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.mongo_client.insert_whiteboard_extraction"):
            from services.ingestion import process_whiteboard
            process_whiteboard(jpeg_bytes)
            call_args = mock_call.call_args
            images = call_args[1].get("images", [])
            assert images[0]["media_type"] == "image/jpeg"

    def test_png_magic_bytes(self):
        """PNG files should be detected by magic bytes."""
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch("services.claude_client.call_sonnet", return_value=self._mock_result(self.MOCK_WHITEBOARD_XML)) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.mongo_client.insert_whiteboard_extraction"):
            from services.ingestion import process_whiteboard
            process_whiteboard(png_bytes)
            call_args = mock_call.call_args
            images = call_args[1].get("images", [])
            assert images[0]["media_type"] == "image/png"

    def test_unknown_format_defaults_jpeg(self):
        """Unknown image format should default to image/jpeg."""
        unknown_bytes = b"\x00\x01\x02\x03" + b"\x00" * 100

        with patch("services.claude_client.call_sonnet", return_value=self._mock_result(self.MOCK_WHITEBOARD_XML)) as mock_call, \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.mongo_client.insert_whiteboard_extraction"):
            from services.ingestion import process_whiteboard
            process_whiteboard(unknown_bytes)
            call_args = mock_call.call_args
            images = call_args[1].get("images", [])
            assert images[0]["media_type"] == "image/jpeg"

    def test_mongo_insert_called(self):
        """Should call insert_whiteboard_extraction with extraction data."""
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 100

        with patch("services.claude_client.call_sonnet", return_value=self._mock_result(self.MOCK_WHITEBOARD_XML)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.mongo_client.insert_whiteboard_extraction") as mock_insert:
            from services.ingestion import process_whiteboard
            process_whiteboard(jpeg_bytes, session_date="2026-02-15")
            mock_insert.assert_called_once()
            doc = mock_insert.call_args[0][0]
            assert doc["session_date"] == "2026-02-15"

    def test_returns_correct_structure(self):
        """Result should have required keys."""
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 100

        with patch("services.claude_client.call_sonnet", return_value=self._mock_result(self.MOCK_WHITEBOARD_XML)), \
             patch("services.claude_client.load_prompt", return_value="template"), \
             patch("services.claude_client.escape_xml", side_effect=lambda x: x), \
             patch("services.mongo_client.insert_whiteboard_extraction"):
            from services.ingestion import process_whiteboard
            result = process_whiteboard(jpeg_bytes)
            assert "extraction_confidence" in result
            assert "legibility_notes" in result
            assert "extracted_content" in result
            assert "confirmation_message" in result
            assert "raw" in result


# ---------------------------------------------------------------------------
# store_session tests
# ---------------------------------------------------------------------------

class TestStoreSession:
    """Tests for store_session: stores transcript sessions to MongoDB."""

    def test_inserts_to_mongodb(self):
        """Should call insert_session with the session document."""
        with patch("services.mongo_client.insert_session", return_value="session_123") as mock_insert:
            from services.ingestion import store_session
            result = store_session("transcript text")
            mock_insert.assert_called_once()
            doc = mock_insert.call_args[0][0]
            assert doc["transcript"] == "transcript text"

    def test_returns_session_id(self):
        """Should return the session_id string from MongoDB."""
        with patch("services.mongo_client.insert_session", return_value="session_abc"):
            from services.ingestion import store_session
            result = store_session("text")
            assert result == "session_abc"

    def test_metadata_added(self):
        """Metadata should be included in the stored document."""
        with patch("services.mongo_client.insert_session", return_value="id") as mock_insert:
            from services.ingestion import store_session
            store_session("text", metadata={"session_date": "2026-02-15", "participants": "Alex"})
            doc = mock_insert.call_args[0][0]
            assert doc["metadata"]["session_date"] == "2026-02-15"
            assert doc["session_date"] == "2026-02-15"

    def test_handles_none_metadata(self):
        """None metadata should default to empty dict."""
        with patch("services.mongo_client.insert_session", return_value="id") as mock_insert:
            from services.ingestion import store_session
            store_session("text", metadata=None)
            doc = mock_insert.call_args[0][0]
            assert doc["metadata"] == {}


# ---------------------------------------------------------------------------
# store_confirmed_claims tests
# ---------------------------------------------------------------------------

class TestStoreConfirmedClaims:
    """Tests for store_confirmed_claims: stores confirmed claims to MongoDB."""

    def test_skips_unconfirmed(self):
        """Claims with confirmed=False should be skipped."""
        claims = [
            {"claim_text": "a", "confirmed": True},
            {"claim_text": "b", "confirmed": False},
        ]
        with patch("services.mongo_client.insert_claim", return_value="id") as mock_insert:
            from services.ingestion import store_confirmed_claims
            result = store_confirmed_claims(claims, "session_1")
            assert mock_insert.call_count == 1

    def test_inserts_each_confirmed(self):
        """Each confirmed claim should be inserted individually."""
        claims = [
            {"claim_text": "a", "confirmed": True},
            {"claim_text": "b", "confirmed": True},
            {"claim_text": "c", "confirmed": True},
        ]
        with patch("services.mongo_client.insert_claim", return_value="id") as mock_insert:
            from services.ingestion import store_confirmed_claims
            result = store_confirmed_claims(claims, "session_1")
            assert mock_insert.call_count == 3

    def test_returns_list_of_ids(self):
        """Should return list of inserted claim IDs."""
        claims = [{"claim_text": "a", "confirmed": True}]
        with patch("services.mongo_client.insert_claim", return_value="claim_123"):
            from services.ingestion import store_confirmed_claims
            result = store_confirmed_claims(claims, "session_1")
            assert result == ["claim_123"]

    def test_empty_claims_list(self):
        """Empty claims list should return empty list."""
        with patch("services.mongo_client.insert_claim") as mock_insert:
            from services.ingestion import store_confirmed_claims
            result = store_confirmed_claims([], "session_1")
            assert result == []
            mock_insert.assert_not_called()


# ---------------------------------------------------------------------------
# run_ingestion_pipeline tests
# ---------------------------------------------------------------------------

class TestRunIngestionPipeline:
    """Tests for run_ingestion_pipeline: orchestrates full ingestion flow."""

    def test_orchestrates_all_steps(self):
        """Should call consistency check, document update, and store claims."""
        claims = [{"claim_text": "Test claim", "confirmed": True, "claim_type": "decision", "confidence": "definite"}]
        with patch("services.consistency.run_consistency_check", return_value={"contradictions": []}) as mock_consist, \
             patch("services.document_updater.update_document", return_value={"success": True, "message": "Updated"}) as mock_update, \
             patch("services.mongo_client.insert_claim", return_value="id1"):
            from services.ingestion import run_ingestion_pipeline
            result = run_ingestion_pipeline("transcript", claims, "session_123")

            mock_consist.assert_called_once_with(claims, session_type="", brain="pitch")
            mock_update.assert_called_once()
            assert result["document_updated"] is True
            assert result["claims_stored"] == 1
            assert result["session_id"] == "session_123"

    def test_returns_correct_structure(self):
        """Result should have all expected keys."""
        claims = [{"claim_text": "Test", "confirmed": True}]
        with patch("services.consistency.run_consistency_check", return_value={}), \
             patch("services.document_updater.update_document", return_value={"success": False, "message": "fail"}), \
             patch("services.mongo_client.insert_claim", return_value="id"):
            from services.ingestion import run_ingestion_pipeline
            result = run_ingestion_pipeline("transcript", claims, "session_1")
            assert "consistency_results" in result
            assert "document_updated" in result
            assert "document_update_message" in result
            assert "claims_stored" in result
            assert "session_id" in result

    def test_stores_new_session_when_id_is_none(self):
        """When session_id is None/falsy, should store a new session."""
        claims = [{"claim_text": "Test", "confirmed": True}]
        with patch("services.consistency.run_consistency_check", return_value={}), \
             patch("services.document_updater.update_document", return_value={"success": True, "message": "ok"}), \
             patch("services.mongo_client.insert_session", return_value="new_session_id") as mock_store_session, \
             patch("services.mongo_client.insert_claim", return_value="id1"):
            from services.ingestion import run_ingestion_pipeline
            result = run_ingestion_pipeline("transcript", claims, session_id="")
            mock_store_session.assert_called_once()
            assert result["session_id"] == "new_session_id"
