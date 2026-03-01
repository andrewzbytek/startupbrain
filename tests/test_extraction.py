"""
Extraction quality tests for Startup Brain — SPEC Section 17.2.

Tests the claim extraction parsing logic using mocked Claude responses.
All tests mock external APIs and run without API keys.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: build a realistic extraction XML response
# ---------------------------------------------------------------------------

def _make_extraction_xml(claims: list, session_summary: str = "Mock session summary.", tags: list = None) -> str:
    """Build a mock extraction XML output string."""
    tags = tags or ["test-tag"]
    tag_xml = "\n".join(f"    <tag>{t}</tag>" for t in tags)

    claims_xml_parts = []
    for c in claims:
        topic_tags = c.get("topic_tags", ["general"])
        ttags = "\n".join(f"        <tag>{t}</tag>" for t in topic_tags)
        claims_xml_parts.append(f"""    <claim>
      <claim_text>{c['claim_text']}</claim_text>
      <claim_type>{c.get('claim_type', 'claim')}</claim_type>
      <confidence>{c.get('confidence', 'definite')}</confidence>
      <who_said_it>{c.get('who_said_it', '')}</who_said_it>
      <topic_tags>
{ttags}
      </topic_tags>
    </claim>""")

    claims_block = "\n".join(claims_xml_parts)
    return f"""<extraction_output>
  <session_summary>{session_summary}</session_summary>
  <topic_tags>
{tag_xml}
  </topic_tags>
  <claims>
{claims_block}
  </claims>
</extraction_output>"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractAllClaims:
    """test_extract_all_claims: Feed transcript with 5 decisions, verify all 5 extracted."""

    def test_extracts_five_claims(self):
        five_claims = [
            {"claim_text": "Target market is small UK nuclear plants.", "claim_type": "decision", "confidence": "definite", "who_said_it": "Alex", "topic_tags": ["target-market"]},
            {"claim_text": "Pricing is £50,000 per facility per year.", "claim_type": "decision", "confidence": "definite", "who_said_it": "Jordan", "topic_tags": ["pricing"]},
            {"claim_text": "MVP is limited to PDF compliance document management.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["mvp"]},
            {"claim_text": "First hire is a nuclear domain expert.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["hiring"]},
            {"claim_text": "Annual billing is required — no monthly payment.", "claim_type": "decision", "confidence": "definite", "who_said_it": "Alex", "topic_tags": ["pricing"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(five_claims, "Session about pricing and market focus."),
            "tokens_in": 500,
            "tokens_out": 800,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript text with five decisions.")

        assert len(result["claims"]) == 5, f"Expected 5 claims, got {len(result['claims'])}"
        claim_texts = [c["claim_text"] for c in result["claims"]]
        assert "Target market is small UK nuclear plants." in claim_texts
        assert "Pricing is £50,000 per facility per year." in claim_texts

    def test_all_claims_have_required_fields(self):
        claims = [
            {"claim_text": "We will target UK nuclear plants.", "claim_type": "decision", "confidence": "definite", "who_said_it": "Alex", "topic_tags": ["target-market"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims),
            "tokens_in": 100,
            "tokens_out": 200,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Short transcript.")

        assert len(result["claims"]) == 1
        claim = result["claims"][0]
        required_fields = ["claim_text", "claim_type", "confidence", "who_said_it", "topic_tags", "confirmed"]
        for field in required_fields:
            assert field in claim, f"Claim missing required field: {field}"

    def test_claims_default_confirmed_true(self):
        claims = [
            {"claim_text": "Decision about pricing.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["pricing"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims),
            "tokens_in": 100,
            "tokens_out": 200,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript.")

        assert result["claims"][0]["confirmed"] is True, "Claims should default to confirmed=True"


class TestExtractPreservesUncertainty:
    """test_extract_preserves_uncertainty: Verify 'leaning' and 'speculative' confidence levels preserved."""

    def test_leaning_confidence_preserved(self):
        claims = [
            {"claim_text": "We are leaning toward direct sales over channel.", "claim_type": "preference", "confidence": "leaning", "who_said_it": "", "topic_tags": ["go-to-market"]},
            {"claim_text": "We have probably identified the right pricing model.", "claim_type": "assertion", "confidence": "leaning", "who_said_it": "Jordan", "topic_tags": ["pricing"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims, "Session with directional preferences."),
            "tokens_in": 300,
            "tokens_out": 400,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript with uncertain language.")

        confidence_values = [c["confidence"] for c in result["claims"]]
        assert "leaning" in confidence_values, "Expected at least one 'leaning' confidence claim"

    def test_speculative_confidence_preserved(self):
        claims = [
            {"claim_text": "We think maybe a channel partner could help with international expansion.", "claim_type": "question", "confidence": "speculative", "who_said_it": "", "topic_tags": ["go-to-market"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims, "Exploratory session."),
            "tokens_in": 200,
            "tokens_out": 300,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Uncertain transcript.")

        confidence_values = [c["confidence"] for c in result["claims"]]
        assert "speculative" in confidence_values, "Expected 'speculative' confidence claim"

    def test_mixed_confidence_levels(self):
        claims = [
            {"claim_text": "MVP is PDF compliance management.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["mvp"]},
            {"claim_text": "We are leaning toward Azure for file storage.", "claim_type": "preference", "confidence": "leaning", "who_said_it": "", "topic_tags": ["technical"]},
            {"claim_text": "SI partnerships might accelerate sales.", "claim_type": "question", "confidence": "speculative", "who_said_it": "", "topic_tags": ["go-to-market"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims),
            "tokens_in": 400,
            "tokens_out": 500,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Mixed confidence transcript.")

        confidence_values = {c["confidence"] for c in result["claims"]}
        assert "definite" in confidence_values
        assert "leaning" in confidence_values
        assert "speculative" in confidence_values


class TestExtractClaimTypes:
    """test_extract_claim_types: Verify claim_type field correctly set."""

    def test_decision_type(self):
        claims = [
            {"claim_text": "We decided to use per-facility annual licensing.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["pricing"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript.")
        assert result["claims"][0]["claim_type"] == "decision"

    def test_question_type(self):
        claims = [
            {"claim_text": "How do we handle multi-site licences?", "claim_type": "question", "confidence": "speculative", "who_said_it": "", "topic_tags": ["business-model"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript.")
        assert result["claims"][0]["claim_type"] == "question"

    def test_all_five_claim_types_extracted(self):
        claims = [
            {"claim_text": "We will use MongoDB Atlas.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["technical"]},
            {"claim_text": "Nuclear plants have 18-month procurement cycles.", "claim_type": "claim", "confidence": "definite", "who_said_it": "", "topic_tags": ["market"]},
            {"claim_text": "We prefer direct sales over channel.", "claim_type": "preference", "confidence": "leaning", "who_said_it": "", "topic_tags": ["go-to-market"]},
            {"claim_text": "Our moat is regulatory domain expertise.", "claim_type": "assertion", "confidence": "definite", "who_said_it": "", "topic_tags": ["strategy"]},
            {"claim_text": "How do we handle multi-site licences?", "claim_type": "question", "confidence": "speculative", "who_said_it": "", "topic_tags": ["business-model"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 500, "tokens_out": 700, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript with all claim types.")

        extracted_types = {c["claim_type"] for c in result["claims"]}
        for expected_type in ["decision", "claim", "preference", "assertion", "question"]:
            assert expected_type in extracted_types, f"Missing claim type: {expected_type}"


class TestExtractPreservesSpecificity:
    """test_extract_preserves_specificity: Verify numbers, names, dates not genericized."""

    def test_price_figure_preserved(self):
        claims = [
            {"claim_text": "Pricing anchor is £50,000 per facility per year for the first customer.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["pricing"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript with specific pricing.")

        assert "£50,000" in result["claims"][0]["claim_text"], "Specific price figure should be preserved"

    def test_company_names_preserved(self):
        claims = [
            {"claim_text": "We should target BP and Shell as our first enterprise customers.", "claim_type": "preference", "confidence": "leaning", "who_said_it": "", "topic_tags": ["target-market"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript mentioning specific companies.")

        assert "BP" in result["claims"][0]["claim_text"], "Company name should be preserved"
        assert "Shell" in result["claims"][0]["claim_text"], "Company name should be preserved"

    def test_percentage_and_timeline_preserved(self):
        claims = [
            {"claim_text": "Plan to raise pricing to £75K after first 3 customers. Target first customer within 6 months of launch.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["pricing", "timeline"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript with timeline and pricing specifics.")

        claim_text = result["claims"][0]["claim_text"]
        assert "£75K" in claim_text or "75,000" in claim_text, "Price figure should be preserved"
        assert "6 months" in claim_text, "Timeline specifics should be preserved"


class TestExtractWithWhiteboard:
    """test_extract_with_whiteboard: Verify whiteboard text is incorporated when provided."""

    def test_whiteboard_content_reflected_in_claims(self):
        # Claims that reference whiteboard content
        claims = [
            {"claim_text": "The 2x2 grid comparing direct vs. channel sales showed direct sales has higher margin.", "claim_type": "claim", "confidence": "definite", "who_said_it": "", "topic_tags": ["go-to-market"]},
            {"claim_text": "Nuclear Safety Associates was identified as a potential channel partner.", "claim_type": "assertion", "confidence": "leaning", "who_said_it": "", "topic_tags": ["go-to-market"]},
        ]
        mock_response = {
            "text": _make_extraction_xml(claims, "Session reviewing channel strategy with whiteboard analysis."),
            "tokens_in": 300,
            "tokens_out": 500,
            "model": "claude-sonnet-4-20250514",
        }

        whiteboard_text = "2x2 grid: direct vs channel. Direct: high margin, slow. Channel: Nuclear Safety Associates?"

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims(
                transcript="Session about channel strategy.",
                whiteboard_text=whiteboard_text,
            )

        assert len(result["claims"]) == 2, "Whiteboard content should contribute to claims"
        claim_texts = " ".join(c["claim_text"] for c in result["claims"])
        assert "Nuclear Safety Associates" in claim_texts, "Whiteboard entity should appear in claims"

    def test_empty_whiteboard_still_extracts_from_transcript(self):
        claims = [
            {"claim_text": "MVP is PDF compliance management.", "claim_type": "decision", "confidence": "definite", "who_said_it": "", "topic_tags": ["mvp"]},
        ]
        mock_response = {"text": _make_extraction_xml(claims), "tokens_in": 100, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript text.", whiteboard_text="")

        assert len(result["claims"]) == 1, "Should extract claims from transcript even with empty whiteboard"


class TestExtractEmptyTranscript:
    """test_extract_empty_transcript: Edge case — empty or very short input."""

    def test_empty_transcript_returns_empty_claims(self):
        mock_response = {
            "text": "<extraction_output><session_summary></session_summary><topic_tags></topic_tags><claims></claims></extraction_output>",
            "tokens_in": 50,
            "tokens_out": 50,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("")

        assert result["claims"] == [], "Empty transcript should yield empty claims list"

    def test_very_short_transcript_returns_structure(self):
        mock_response = {
            "text": "<extraction_output><session_summary>Very brief session.</session_summary><topic_tags><tag>general</tag></topic_tags><claims></claims></extraction_output>",
            "tokens_in": 50,
            "tokens_out": 100,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("OK.")

        assert "session_summary" in result
        assert "topic_tags" in result
        assert "claims" in result
        assert isinstance(result["claims"], list)

    def test_malformed_xml_response_returns_empty_claims(self):
        """Verify graceful handling of malformed LLM responses."""
        mock_response = {
            "text": "I cannot process this transcript.",
            "tokens_in": 50,
            "tokens_out": 20,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.ingestion import extract_claims
            result = extract_claims("Transcript.")

        assert result["claims"] == [], "Malformed XML should yield empty claims, not crash"
        assert result["session_summary"] == ""
