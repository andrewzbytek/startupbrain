"""
Pure parser isolation tests for services/consistency.py.
Tests all parsing functions without API keys, MongoDB, or network access.
"""

import sys
from unittest.mock import MagicMock, patch

# Mock streamlit before any imports that might pull it in
sys.modules.setdefault("streamlit", MagicMock())

from services.consistency import (
    parse_contradictions,
    _parse_pass2_output,
    _parse_pass3_output,
    _extract_tag,
    _claims_to_xml,
    check_dismissed,
    _format_rag_evidence,
)


# ===== _extract_tag tests =====


class TestExtractTag:
    def test_basic_extraction(self):
        assert _extract_tag("<name>Alice</name>", "name") == "Alice"

    def test_no_matching_tag_returns_empty(self):
        assert _extract_tag("<name>Alice</name>", "age") == ""

    def test_empty_tag_returns_empty(self):
        assert _extract_tag("<name></name>", "name") == ""

    def test_multiline_content(self):
        text = "<desc>\nLine one\nLine two\n</desc>"
        assert _extract_tag(text, "desc") == "Line one\nLine two"

    def test_whitespace_is_stripped(self):
        assert _extract_tag("<x>  hello  </x>", "x") == "hello"

    def test_nested_tags_returns_inner_content(self):
        text = "<outer><inner>value</inner></outer>"
        result = _extract_tag(text, "outer")
        assert "<inner>value</inner>" in result

    def test_special_characters_in_content(self):
        text = "<note>Price is &amp; cost &lt; $100</note>"
        assert _extract_tag(text, "note") == "Price is &amp; cost &lt; $100"

    def test_first_match_wins(self):
        text = "<x>first</x><x>second</x>"
        assert _extract_tag(text, "x") == "first"


# ===== parse_contradictions tests =====


class TestParseContradictions:
    def test_empty_xml_returns_empty_list(self):
        assert parse_contradictions("") == []
        assert parse_contradictions("no contradictions here") == []

    def test_no_contradiction_tags_returns_empty(self):
        xml = "<output><total_found>0</total_found></output>"
        assert parse_contradictions(xml) == []

    def test_single_contradiction_parsed(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>We should pivot to enterprise</new_claim>
            <existing_position>Target small nuclear plants</existing_position>
            <existing_section>Current State</existing_section>
            <tension_description>Direct conflict with target market</tension_description>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["new_claim"] == "We should pivot to enterprise"
        assert result[0]["existing_position"] == "Target small nuclear plants"
        assert result[0]["existing_section"] == "Current State"
        assert result[0]["tension_description"] == "Direct conflict with target market"
        assert result[0]["is_revisited_rejection"] is False

    def test_multiple_contradictions(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>Claim A</new_claim>
            <existing_position>Position A</existing_position>
            <existing_section>Section A</existing_section>
            <tension_description>Tension A</tension_description>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        <contradiction>
            <id>2</id>
            <new_claim>Claim B</new_claim>
            <existing_position>Position B</existing_position>
            <existing_section>Section B</existing_section>
            <tension_description>Tension B</tension_description>
            <is_revisited_rejection>true</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    def test_missing_id_skips_item(self):
        xml = """
        <contradiction>
            <new_claim>No id here</new_claim>
            <existing_position>Position</existing_position>
            <existing_section>Section</existing_section>
            <tension_description>Tension</tension_description>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert len(result) == 0

    def test_is_revisited_rejection_true(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>Revisit usage pricing</new_claim>
            <existing_position>Rejected</existing_position>
            <existing_section>Decision Log</existing_section>
            <tension_description>Revisiting rejected decision</tension_description>
            <is_revisited_rejection>true</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert result[0]["is_revisited_rejection"] is True

    def test_is_revisited_rejection_non_true_is_false(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>Claim</new_claim>
            <existing_position>Position</existing_position>
            <existing_section>Section</existing_section>
            <tension_description>Tension</tension_description>
            <is_revisited_rejection>yes</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert result[0]["is_revisited_rejection"] is False

    def test_malformed_xml_returns_partial(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>Valid claim</new_claim>
            <existing_position>Valid position</existing_position>
            <existing_section>Section</existing_section>
            <tension_description>Tension</tension_description>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        <contradiction>
            <id>2</id>
            <new_claim>Second claim with incomplete tags
        """
        result = parse_contradictions(xml)
        # First contradiction is fully formed and should parse
        assert len(result) >= 1
        assert result[0]["id"] == "1"

    def test_unicode_characters(self):
        xml = """
        <contradiction>
            <id>1</id>
            <new_claim>Price is \u00a350,000 per year</new_claim>
            <existing_position>Original \u20ac pricing</existing_position>
            <existing_section>Pricing</existing_section>
            <tension_description>Currency mismatch</tension_description>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        """
        result = parse_contradictions(xml)
        assert len(result) == 1
        assert "\u00a3" in result[0]["new_claim"]


# ===== _parse_pass2_output tests =====


class TestParsePass2Output:
    def test_empty_returns_empty_retained(self):
        result = _parse_pass2_output("")
        assert result["retained"] == []
        assert result["has_critical"] is False
        assert result["total_retained"] == 0
        assert result["filtered_out"] == []

    def test_has_critical_true_parsed(self):
        xml = "<has_critical>true</has_critical>"
        result = _parse_pass2_output(xml)
        assert result["has_critical"] is True

    def test_has_critical_false_parsed(self):
        xml = "<has_critical>false</has_critical>"
        result = _parse_pass2_output(xml)
        assert result["has_critical"] is False

    def test_retained_items_have_severity(self):
        xml = """
        <contradiction>
            <id>1</id>
            <severity>Critical</severity>
            <new_claim>New claim</new_claim>
            <existing_position>Existing</existing_position>
            <existing_section>Section</existing_section>
            <evidence_summary>Evidence</evidence_summary>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        <has_critical>true</has_critical>
        """
        result = _parse_pass2_output(xml)
        assert len(result["retained"]) == 1
        assert result["retained"][0]["severity"] == "Critical"
        assert result["total_retained"] == 1

    def test_filtered_out_items_parsed(self):
        xml = """
        <filtered>
            <item>
                <id>3</id>
                <reason>Minor difference, no real conflict</reason>
            </item>
        </filtered>
        """
        result = _parse_pass2_output(xml)
        assert len(result["filtered_out"]) == 1
        assert result["filtered_out"][0]["id"] == "3"
        assert result["filtered_out"][0]["reason"] == "Minor difference, no real conflict"

    def test_severity_values(self):
        xml = """
        <contradiction>
            <id>1</id>
            <severity>Critical</severity>
            <new_claim>C1</new_claim>
            <existing_position>E1</existing_position>
            <existing_section>S1</existing_section>
            <evidence_summary>Ev1</evidence_summary>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        <contradiction>
            <id>2</id>
            <severity>Notable</severity>
            <new_claim>C2</new_claim>
            <existing_position>E2</existing_position>
            <existing_section>S2</existing_section>
            <evidence_summary>Ev2</evidence_summary>
            <is_revisited_rejection>false</is_revisited_rejection>
        </contradiction>
        <has_critical>true</has_critical>
        """
        result = _parse_pass2_output(xml)
        assert result["retained"][0]["severity"] == "Critical"
        assert result["retained"][1]["severity"] == "Notable"
        assert result["total_retained"] == 2

    def test_raw_preserved(self):
        xml = "<has_critical>false</has_critical>"
        result = _parse_pass2_output(xml)
        assert result["raw"] == xml


# ===== _parse_pass3_output tests =====


class TestParsePass3Output:
    def test_empty_returns_empty_list(self):
        assert _parse_pass3_output("") == []

    def test_single_analysis_all_fields(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>Market pivot conflict</headline>
            <downstream_implications>Would invalidate current pipeline</downstream_implications>
            <analyst_observation>Founders may be responding to pressure</analyst_observation>
            <original_position>
                <summary>Small UK nuclear plants</summary>
                <evidence>Session 1 and 2 confirmed</evidence>
                <original_rationale>Shorter procurement cycles</original_rationale>
            </original_position>
            <new_position>
                <summary>Large enterprise oil and gas</summary>
                <evidence>Recent investor meeting</evidence>
                <possible_reasons_for_change>Investor pressure for bigger TAM</possible_reasons_for_change>
            </new_position>
            <resolution_options>
                <option>
                    <label>Keep original</label>
                    <description>Stay focused on small nuclear</description>
                </option>
                <option>
                    <label>Adopt new</label>
                    <description>Pivot to enterprise</description>
                </option>
            </resolution_options>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        assert len(result) == 1
        a = result[0]
        assert a["contradiction_id"] == "1"
        assert a["headline"] == "Market pivot conflict"
        assert a["downstream_implications"] == "Would invalidate current pipeline"
        assert a["analyst_observation"] == "Founders may be responding to pressure"

    def test_original_position_block(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>Test</headline>
            <downstream_implications>Test</downstream_implications>
            <analyst_observation>Test</analyst_observation>
            <original_position>
                <summary>Original summary</summary>
                <evidence>Original evidence</evidence>
                <original_rationale>Original rationale</original_rationale>
            </original_position>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        op = result[0]["original_position"]
        assert op["summary"] == "Original summary"
        assert op["evidence"] == "Original evidence"
        assert op["original_rationale"] == "Original rationale"

    def test_new_position_block(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>Test</headline>
            <downstream_implications>Test</downstream_implications>
            <analyst_observation>Test</analyst_observation>
            <new_position>
                <summary>New summary</summary>
                <evidence>New evidence</evidence>
                <possible_reasons_for_change>Market shift</possible_reasons_for_change>
            </new_position>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        np = result[0]["new_position"]
        assert np["summary"] == "New summary"
        assert np["evidence"] == "New evidence"
        assert np["possible_reasons_for_change"] == "Market shift"

    def test_resolution_options_parsed(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>Test</headline>
            <downstream_implications>Test</downstream_implications>
            <analyst_observation>Test</analyst_observation>
            <resolution_options>
                <option>
                    <label>Option A</label>
                    <description>Description A</description>
                </option>
                <option>
                    <label>Option B</label>
                    <description>Description B</description>
                </option>
                <option>
                    <label>Option C</label>
                    <description>Description C</description>
                </option>
            </resolution_options>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        opts = result[0]["resolution_options"]
        assert len(opts) == 3
        assert opts[0]["label"] == "Option A"
        assert opts[1]["label"] == "Option B"
        assert opts[2]["description"] == "Description C"

    def test_multiple_analyses(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>First</headline>
            <downstream_implications>Imp1</downstream_implications>
            <analyst_observation>Obs1</analyst_observation>
        </analysis>
        <analysis>
            <contradiction_id>2</contradiction_id>
            <headline>Second</headline>
            <downstream_implications>Imp2</downstream_implications>
            <analyst_observation>Obs2</analyst_observation>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        assert len(result) == 2
        assert result[0]["contradiction_id"] == "1"
        assert result[1]["contradiction_id"] == "2"

    def test_analysis_without_positions(self):
        xml = """
        <analysis>
            <contradiction_id>1</contradiction_id>
            <headline>Bare analysis</headline>
            <downstream_implications>Some implications</downstream_implications>
            <analyst_observation>Some observation</analyst_observation>
        </analysis>
        """
        result = _parse_pass3_output(xml)
        assert len(result) == 1
        assert "original_position" not in result[0]
        assert "new_position" not in result[0]
        assert result[0]["resolution_options"] == []


# ===== _claims_to_xml tests =====


class TestClaimsToXml:
    def test_empty_list_returns_minimal_xml(self):
        result = _claims_to_xml([])
        assert "<new_claims>" in result
        assert "</new_claims>" in result
        assert "<claim>" not in result

    def test_single_claim_all_fields(self):
        claims = [{
            "claim_text": "We target small nuclear",
            "claim_type": "decision",
            "confidence": "definite",
            "who_said_it": "Alex",
        }]
        result = _claims_to_xml(claims)
        assert "<claim_text>We target small nuclear</claim_text>" in result
        assert "<claim_type>decision</claim_type>" in result
        assert "<confidence>definite</confidence>" in result
        assert "<who_said_it>Alex</who_said_it>" in result

    def test_claim_without_who_said_it_skips_tag(self):
        claims = [{
            "claim_text": "Some claim",
            "claim_type": "claim",
            "confidence": "definite",
        }]
        result = _claims_to_xml(claims)
        assert "<who_said_it>" not in result

    def test_claim_with_empty_who_said_it_skips_tag(self):
        claims = [{
            "claim_text": "Some claim",
            "claim_type": "claim",
            "confidence": "definite",
            "who_said_it": "",
        }]
        result = _claims_to_xml(claims)
        assert "<who_said_it>" not in result

    def test_xml_escaping_applied(self):
        claims = [{
            "claim_text": "Price < $100 & cost > $50",
            "claim_type": "claim",
            "confidence": "definite",
        }]
        result = _claims_to_xml(claims)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_defaults_for_missing_fields(self):
        claims = [{}]
        result = _claims_to_xml(claims)
        assert "<claim_type>claim</claim_type>" in result
        assert "<confidence>definite</confidence>" in result


# ===== check_dismissed tests =====


class TestCheckDismissed:
    def _make_contradiction(self, new_claim):
        return {
            "id": "1",
            "new_claim": new_claim,
            "existing_position": "Some position",
            "existing_section": "Some section",
            "tension_description": "Some tension",
            "is_revisited_rejection": False,
        }

    def test_empty_dismissed_section_returns_all(self):
        doc = "# Startup Brain\n## Current State\nSome content\n## Dismissed Contradictions\n\n"
        contradictions = [self._make_contradiction("Anything at all")]
        result = check_dismissed(contradictions, doc)
        assert len(result) == len(contradictions)

    def test_no_dismissed_section_returns_all(self):
        doc = "# Startup Brain\n## Current State\nSome content\n"
        contradictions = [self._make_contradiction("Anything at all")]
        result = check_dismissed(contradictions, doc)
        assert len(result) == len(contradictions)

    def test_placeholder_dismissed_returns_all(self):
        doc = "## Dismissed Contradictions\n[no dismissed contradictions]\n"
        contradictions = [self._make_contradiction("Any claim here")]
        result = check_dismissed(contradictions, doc)
        assert len(result) == len(contradictions)

    def test_matching_claim_is_dismissed(self):
        doc = """## Dismissed Contradictions
- 2026-02-12: Claim that enterprise accounts would close faster — Dismissed because: small nuclear operators have shorter procurement cycles.
"""
        contradictions = [
            self._make_contradiction(
                "enterprise accounts would close faster than nuclear operators with shorter procurement cycles"
            )
        ]
        result = check_dismissed(contradictions, doc)
        # The claim's significant words heavily overlap with the dismissed section
        assert len(result) == 0

    def test_non_matching_claim_kept(self):
        doc = """## Dismissed Contradictions
- 2026-02-12: Claim about enterprise accounts — Dismissed.
"""
        contradictions = [
            self._make_contradiction(
                "We should switch from Python to Rust for better performance"
            )
        ]
        result = check_dismissed(contradictions, doc)
        assert len(result) == 1

    def test_partial_overlap(self, sample_living_document):
        """With the real living document fixture, a non-matching claim should survive."""
        contradictions = [
            self._make_contradiction(
                "We should hire a marketing expert before the domain specialist"
            )
        ]
        result = check_dismissed(contradictions, sample_living_document)
        assert len(result) == 1

    def test_dismissed_match_from_fixture(self, sample_living_document):
        """The fixture's dismissed section mentions BP/Shell enterprise accounts."""
        contradictions = [
            self._make_contradiction(
                "BP/Shell enterprise accounts would close faster with shorter procurement cycles directly"
            )
        ]
        result = check_dismissed(contradictions, sample_living_document)
        # Significant words overlap with the dismissed section
        assert len(result) == 0

    def test_empty_contradictions_list(self, sample_living_document):
        result = check_dismissed([], sample_living_document)
        assert result == []


# ===== _format_rag_evidence tests =====


class TestFormatRagEvidence:
    def test_empty_list(self):
        result = _format_rag_evidence([])
        assert "<rag_evidence>" in result
        assert "</rag_evidence>" in result
        assert "<evidence_item>" not in result

    def test_single_evidence_item(self):
        evidence = [{
            "source_date": "2026-02-10",
            "source_type": "session",
            "relevant_excerpt": "We discussed pricing models",
        }]
        result = _format_rag_evidence(evidence)
        assert "<source_date>2026-02-10</source_date>" in result
        assert "<source_type>session</source_type>" in result
        assert "<relevant_excerpt>We discussed pricing models</relevant_excerpt>" in result

    def test_xml_escaping_in_evidence(self):
        evidence = [{
            "source_date": "2026-02-10",
            "source_type": "session",
            "relevant_excerpt": "Price < $100 & cost > $50",
        }]
        result = _format_rag_evidence(evidence)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_missing_fields_use_defaults(self):
        evidence = [{}]
        result = _format_rag_evidence(evidence)
        assert "<source_date></source_date>" in result
        assert "<source_type>session</source_type>" in result
        assert "<relevant_excerpt></relevant_excerpt>" in result

    def test_multiple_evidence_items(self):
        evidence = [
            {"source_date": "2026-02-10", "source_type": "session", "relevant_excerpt": "First"},
            {"source_date": "2026-02-11", "source_type": "session", "relevant_excerpt": "Second"},
        ]
        result = _format_rag_evidence(evidence)
        assert result.count("<evidence_item>") == 2
        assert result.count("</evidence_item>") == 2
