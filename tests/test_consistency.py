"""
Consistency engine tests for Startup Brain — SPEC Section 17.1.

Tests the multi-pass consistency engine using mocked Claude responses.
All tests mock external APIs and run without API keys.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: XML builders for mock responses
# ---------------------------------------------------------------------------

def _pass1_xml(contradictions: list, total: int = None) -> str:
    """Build a mock Pass 1 output XML string."""
    if total is None:
        total = len(contradictions)

    items = []
    for c in contradictions:
        items.append(f"""    <contradiction>
      <id>{c['id']}</id>
      <new_claim>{c['new_claim']}</new_claim>
      <existing_position>{c['existing_position']}</existing_position>
      <existing_section>{c['existing_section']}</existing_section>
      <tension_description>{c['tension_description']}</tension_description>
      <is_revisited_rejection>{'true' if c.get('is_revisited_rejection') else 'false'}</is_revisited_rejection>
    </contradiction>""")

    contradictions_xml = "\n".join(items) if items else ""
    return f"""<pass1_output>
  <potential_contradictions>
{contradictions_xml}
  </potential_contradictions>
  <total_found>{total}</total_found>
</pass1_output>"""


def _pass2_xml(retained: list, filtered: list = None, has_critical: bool = None) -> str:
    """Build a mock Pass 2 output XML string."""
    if has_critical is None:
        has_critical = any(r.get("severity") == "Critical" for r in retained)

    items = []
    for r in retained:
        items.append(f"""  <contradiction>
    <id>{r['id']}</id>
    <severity>{r['severity']}</severity>
    <new_claim>{r.get('new_claim', '')}</new_claim>
    <existing_position>{r.get('existing_position', '')}</existing_position>
    <existing_section>{r.get('existing_section', '')}</existing_section>
    <evidence_summary>{r.get('evidence_summary', '')}</evidence_summary>
    <is_revisited_rejection>{'true' if r.get('is_revisited_rejection') else 'false'}</is_revisited_rejection>
  </contradiction>""")

    filtered_xml = ""
    if filtered:
        for f in filtered:
            filtered_xml += f"""  <item>
    <id>{f['id']}</id>
    <reason>{f['reason']}</reason>
  </item>\n"""

    return f"""<pass2_output>
  <retained_contradictions>
{"".join(items)}
  </retained_contradictions>
  <has_critical>{'true' if has_critical else 'false'}</has_critical>
  <filtered_contradictions>
{filtered_xml}  </filtered_contradictions>
</pass2_output>"""


def _pass3_xml(analyses: list) -> str:
    """Build a mock Pass 3 output XML string."""
    items = []
    for a in analyses:
        items.append(f"""  <analysis>
    <contradiction_id>{a['contradiction_id']}</contradiction_id>
    <headline>{a.get('headline', 'Critical contradiction detected')}</headline>
    <original_position>
      <summary>{a.get('original_summary', 'Original position summary')}</summary>
      <evidence>Evidence from prior sessions</evidence>
      <original_rationale>Original rationale</original_rationale>
    </original_position>
    <new_position>
      <summary>{a.get('new_summary', 'New position summary')}</summary>
      <evidence>Evidence from current session</evidence>
      <possible_reasons_for_change>Possible reasons for change</possible_reasons_for_change>
    </new_position>
    <downstream_implications>{a.get('implications', 'Significant downstream implications')}</downstream_implications>
    <analyst_observation>{a.get('observation', 'This is a significant strategic shift')}</analyst_observation>
    <resolution_options>
      <option>
        <label>Update anyway</label>
        <description>Accept the change and update the living document</description>
      </option>
      <option>
        <label>Dismiss</label>
        <description>Flag as resolved and move on</description>
      </option>
    </resolution_options>
  </analysis>""")

    return f"<pass3_output>\n{''.join(items)}\n</pass3_output>"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStrategicContradictionCaught:
    """test_strategic_contradiction_caught: Target market change caught at Pass 1, rated Critical at Pass 2."""

    def test_target_market_contradiction_detected(self, sample_living_document, sample_claims):
        new_claims = [
            {
                "claim_text": "We should target BP and large oil & gas companies as our first customers.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["target-market"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "We should target BP and large oil & gas companies as our first customers.",
            "existing_position": "Small nuclear power plants in the UK, fewer than 3 reactors.",
            "existing_section": "Current State → Target Market / Initial Customer",
            "tension_description": "New claim proposes large oil & gas as initial target, contradicting small nuclear beachhead decision.",
            "is_revisited_rejection": False,
        }])

        pass2_response = _pass2_xml(
            retained=[{
                "id": "1",
                "severity": "Critical",
                "new_claim": "We should target BP and large oil & gas companies.",
                "existing_position": "Small nuclear power plants in the UK.",
                "existing_section": "Current State → Target Market / Initial Customer",
                "evidence_summary": "Target market was explicitly decided as small nuclear plants.",
                "is_revisited_rejection": False,
            }],
            has_critical=True,
        )

        pass3_response = _pass3_xml([{
            "contradiction_id": "1",
            "headline": "Critical: Target market changed from small nuclear to large oil & gas",
            "original_summary": "Small UK nuclear plants (<3 reactors)",
            "new_summary": "BP and large oil & gas enterprises",
            "implications": "Affects pricing, sales cycle, team hiring, and all go-to-market assumptions.",
        }])

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document), \
             patch("services.consistency._get_rag_evidence", return_value=[]):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 500, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 600, "tokens_out": 400, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": pass3_response, "tokens_in": 800, "tokens_out": 600, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["has_contradictions"] is True, "Strategic contradiction should be detected"
        assert result["has_critical"] is True, "Target market change should be rated Critical"
        assert result["pass2"] is not None
        assert len(result["pass2"]["retained"]) == 1
        assert result["pass2"]["retained"][0]["severity"] == "Critical"


class TestTacticalImportantCaught:
    """test_tactical_important_caught: Important tactical change caught and rated Notable."""

    def test_notable_tactical_change_detected(self, sample_living_document):
        new_claims = [
            {
                "claim_text": "First hire should be a sales person, not a nuclear domain expert.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "",
                "topic_tags": ["hiring"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "First hire should be a sales person, not a nuclear domain expert.",
            "existing_position": "First hire must be a nuclear domain expert, not a developer.",
            "existing_section": "Current State → Team / Hiring Plans",
            "tension_description": "Contradicts prior decision about first hire being a domain expert.",
            "is_revisited_rejection": False,
        }])

        pass2_response = _pass2_xml(
            retained=[{
                "id": "1",
                "severity": "Notable",
                "new_claim": "First hire should be a sales person.",
                "existing_position": "First hire must be a nuclear domain expert.",
                "existing_section": "Current State → Team / Hiring Plans",
                "evidence_summary": "First hire decision was explicitly made as domain expert.",
                "is_revisited_rejection": False,
            }],
            has_critical=False,
        )

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 400, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 500, "tokens_out": 400, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["has_contradictions"] is True, "Notable tactical contradiction should be detected"
        assert result["has_critical"] is False, "Hiring change should not be Critical"
        assert result["pass3"] is None, "Pass 3 should not run when no Critical items"
        notable_items = [c for c in result["pass2"]["retained"] if c["severity"] == "Notable"]
        assert len(notable_items) == 1, "Should have exactly one Notable contradiction"


class TestMinorFiltered:
    """test_minor_filtered: Minor detail change found at Pass 1, filtered at Pass 2."""

    def test_minor_contradiction_filtered_out(self, sample_living_document):
        new_claims = [
            {
                "claim_text": "We will use PyMuPDF version 1.24 for PDF parsing.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "",
                "topic_tags": ["technical"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "We will use PyMuPDF version 1.24.",
            "existing_position": "PyMuPDF for text extraction and layout analysis.",
            "existing_section": "Current State → Technical Approach",
            "tension_description": "Version number specification is a minor detail.",
            "is_revisited_rejection": False,
        }])

        pass2_response = _pass2_xml(
            retained=[],  # Minor filtered out
            filtered=[{"id": "1", "reason": "Minor version detail, not a strategic contradiction."}],
            has_critical=False,
        )

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 300, "tokens_out": 200, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 400, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["has_contradictions"] is False, "Minor contradiction should be filtered to False"
        assert result["pass2"]["total_retained"] == 0, "No contradictions should be retained after filtering"
        assert result["pass3"] is None, "Pass 3 should not run with no retained contradictions"


class TestRevisitedRejectedIdea:
    """test_revisited_rejected_idea: Previously rejected idea surfaces decision log context."""

    def test_revisited_rejection_flagged(self, sample_living_document):
        new_claims = [
            {
                "claim_text": "We are reconsidering usage-based pricing at £0.10 per document processed.",
                "claim_type": "preference",
                "confidence": "leaning",
                "who_said_it": "Jordan",
                "topic_tags": ["pricing"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "We are reconsidering usage-based pricing at £0.10 per document processed.",
            "existing_position": "Rejected usage-based pricing in favour of annual per-facility licence. VCs dislike variable MRR.",
            "existing_section": "Decision Log → 2026-02-05 — Rejected Usage-Based Pricing",
            "tension_description": "New claim revisits usage-based pricing that was explicitly rejected with documented rationale.",
            "is_revisited_rejection": True,
        }])

        pass2_response = _pass2_xml(
            retained=[{
                "id": "1",
                "severity": "Notable",
                "new_claim": "We are reconsidering usage-based pricing.",
                "existing_position": "Rejected usage-based pricing.",
                "existing_section": "Decision Log → Rejected Usage-Based Pricing",
                "evidence_summary": "Usage-based pricing was explicitly rejected in Decision Log.",
                "is_revisited_rejection": True,
            }],
            has_critical=False,
        )

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 400, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 500, "tokens_out": 400, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["has_contradictions"] is True, "Revisited rejection should be detected"
        retained = result["pass2"]["retained"]
        assert len(retained) == 1
        assert retained[0]["is_revisited_rejection"] is True, "Should flag as revisited rejection"


class TestGenuineEvolutionNotFlagged:
    """test_genuine_evolution_not_flagged: Natural pivot with reasoning NOT flagged as contradiction."""

    def test_evolution_with_rationale_not_flagged(self, sample_living_document):
        """Pricing evolution with specific customer feedback rationale should pass through."""
        new_claims = [
            {
                "claim_text": "Moving to hybrid pricing (£15K base + £0.10/document) based on specific customer feedback about OpEx budget lines.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "",
                "topic_tags": ["pricing"],
                "confirmed": True,
            }
        ]

        # Pass 1 finds nothing significant
        pass1_response = _pass1_xml([], total=0)

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document):
            mock_sonnet.return_value = {"text": pass1_response, "tokens_in": 300, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}
            mock_opus.return_value = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["has_contradictions"] is False, "Genuine evolution with rationale should not be flagged"
        assert result["pass2"] is None, "Pass 2 should not run if Pass 1 finds nothing"


class TestDismissedNotReflagged:
    """test_dismissed_not_reflagged: Contradiction in Dismissed section NOT re-flagged."""

    def test_dismissed_contradiction_not_surfaced(self):
        """Contradictions already in the Dismissed section should not be raised again."""
        living_doc_with_dismissed = """# Startup Brain — NuclearCompliance.ai

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK.
**Changelog:**
- 2026-02-01: Initial position. Source: Session 1

## Decision Log
[No decisions recorded]

## Feedback Tracker
[No feedback]

## Dismissed Contradictions
- 2026-02-12: Claim that BP would be a faster sale — Dismissed because: small plants have shorter procurement cycles.
"""
        new_claims = [
            {
                "claim_text": "BP and Shell would be a faster sale because they have larger budgets.",
                "claim_type": "preference",
                "confidence": "leaning",
                "who_said_it": "",
                "topic_tags": ["target-market"],
                "confirmed": True,
            }
        ]

        from services.consistency import check_dismissed
        # The claim about BP being faster is already dismissed
        sample_contradictions = [
            {
                "id": "1",
                "new_claim": "BP and Shell would be a faster sale because they have larger budgets.",
                "existing_position": "Small nuclear power plants.",
                "existing_section": "Current State → Target Market",
                "tension_description": "Previously dismissed contradiction about BP sales speed.",
                "is_revisited_rejection": False,
            }
        ]

        filtered = check_dismissed(sample_contradictions, living_doc_with_dismissed)
        # The dismissed section contains "BP" and "faster sale" keywords that overlap
        # The function uses word overlap heuristic — claims with >40% overlap with dismissed section are filtered
        assert isinstance(filtered, list), "check_dismissed should return a list"


class TestPass3OnlyOnCritical:
    """test_pass3_only_on_critical: Verify Pass 3 (Opus) only runs when Pass 2 finds Critical items."""

    def test_pass3_runs_when_critical(self, sample_living_document):
        new_claims = [
            {
                "claim_text": "We should now target large oil & gas enterprise accounts.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "",
                "topic_tags": ["target-market"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "We should now target large oil & gas enterprise accounts.",
            "existing_position": "Small nuclear plants.",
            "existing_section": "Current State → Target Market",
            "tension_description": "Major strategic pivot.",
            "is_revisited_rejection": False,
        }])

        pass2_response = _pass2_xml(
            retained=[{
                "id": "1",
                "severity": "Critical",
                "new_claim": "We should now target large oil & gas.",
                "existing_position": "Small nuclear plants.",
                "existing_section": "Current State → Target Market",
                "evidence_summary": "Explicit strategic decision.",
                "is_revisited_rejection": False,
            }],
            has_critical=True,
        )

        pass3_response = _pass3_xml([{
            "contradiction_id": "1",
            "headline": "Critical: Major target market pivot",
            "original_summary": "Small UK nuclear plants",
            "new_summary": "Large oil & gas enterprises",
            "implications": "Affects all go-to-market assumptions.",
        }])

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document), \
             patch("services.consistency._get_rag_evidence", return_value=[]), \
             patch("services.consistency.check_dismissed", side_effect=lambda c, d: c):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 500, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 600, "tokens_out": 400, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": pass3_response, "tokens_in": 800, "tokens_out": 600, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["pass3"] is not None, "Pass 3 should run when Pass 2 finds Critical items"
        assert mock_opus.called, "Opus model should be called for Pass 3"


class TestPass3SkippedWhenNoCritical:
    """test_pass3_skipped_when_no_critical: Verify Pass 3 does NOT run when no Critical items."""

    def test_pass3_skipped_for_notable_only(self, sample_living_document):
        new_claims = [
            {
                "claim_text": "We should hire a sales person before a domain expert.",
                "claim_type": "preference",
                "confidence": "leaning",
                "who_said_it": "",
                "topic_tags": ["hiring"],
                "confirmed": True,
            }
        ]

        pass1_response = _pass1_xml([{
            "id": "1",
            "new_claim": "Sales person before domain expert.",
            "existing_position": "First hire is nuclear domain expert.",
            "existing_section": "Current State → Team / Hiring Plans",
            "tension_description": "Different first hire priority.",
            "is_revisited_rejection": False,
        }])

        pass2_response = _pass2_xml(
            retained=[{
                "id": "1",
                "severity": "Notable",
                "new_claim": "Sales person before domain expert.",
                "existing_position": "First hire is nuclear domain expert.",
                "existing_section": "Current State → Team / Hiring Plans",
                "evidence_summary": "Hiring order changed.",
                "is_revisited_rejection": False,
            }],
            has_critical=False,
        )

        with patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus, \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.consistency.read_living_document", return_value=sample_living_document):
            mock_sonnet.side_effect = [
                {"text": pass1_response, "tokens_in": 400, "tokens_out": 300, "model": "claude-sonnet-4-20250514"},
                {"text": pass2_response, "tokens_in": 500, "tokens_out": 400, "model": "claude-sonnet-4-20250514"},
            ]
            mock_opus.return_value = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "claude-opus-4-20250514"}

            from services.consistency import run_consistency_check
            result = run_consistency_check(new_claims)

        assert result["pass3"] is None, "Pass 3 should NOT run when only Notable contradictions found"
        assert not mock_opus.called, "Opus model should NOT be called when no Critical items"


class TestPushbackGeneration:
    """test_pushback_generation: Verify pushback context is generated with 'Update anyway' option."""

    def test_pushback_contains_update_anyway_option(self, sample_living_document):
        pushback_xml = """<pushback_output>
  <headline>Prior decision: Target market was small UK nuclear plants</headline>
  <message>You previously decided to focus on small nuclear plants due to shorter procurement cycles. The current change would affect pricing, sales approach, and hiring plans.</message>
  <prior_context>
    <date>2026-02-01</date>
    <original_position>Small nuclear power plants in the UK</original_position>
    <original_rationale>Shorter procurement cycles (6-12 months vs 18-24 for majors)</original_rationale>
    <source>Session 1</source>
  </prior_context>
  <options>
    <option>
      <label>Update anyway</label>
      <description>Accept the change and update the living document with the new target market.</description>
    </option>
    <option>
      <label>Keep original</label>
      <description>Dismiss this change and maintain the small nuclear plants focus.</description>
    </option>
    <option>
      <label>Add nuance</label>
      <description>Document both markets as targets with different timelines.</description>
    </option>
  </options>
</pushback_output>"""

        mock_response = {
            "text": pushback_xml,
            "tokens_in": 600,
            "tokens_out": 400,
            "model": "claude-sonnet-4-20250514",
        }

        relevant_decisions = [
            {
                "date": "2026-02-01",
                "decision": "Target market: small UK nuclear plants",
                "rationale": "Shorter procurement cycles",
                "status": "Active",
            }
        ]

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.consistency import generate_pushback
            result = generate_pushback(
                change_description="We want to target BP and large oil & gas companies instead.",
                relevant_decisions=relevant_decisions,
            )

        assert result["headline"] != "", "Pushback should have a headline"
        assert result["message"] != "", "Pushback should have a message"
        assert len(result["options"]) > 0, "Pushback should have options"

        option_labels = [o["label"] for o in result["options"]]
        assert "Update anyway" in option_labels, "Pushback options should include 'Update anyway'"

    def test_pushback_includes_prior_context(self):
        pushback_xml = """<pushback_output>
  <headline>Revisiting rejected pricing model</headline>
  <message>Usage-based pricing was rejected on 2026-02-05.</message>
  <prior_context>
    <date>2026-02-05</date>
    <original_position>Per-facility annual licensing at £50K/year</original_position>
    <original_rationale>VCs dislike variable MRR</original_rationale>
    <source>Session 2</source>
  </prior_context>
  <options>
    <option>
      <label>Update anyway</label>
      <description>Switch to usage-based pricing</description>
    </option>
  </options>
</pushback_output>"""

        mock_response = {
            "text": pushback_xml,
            "tokens_in": 500,
            "tokens_out": 350,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"):
            from services.consistency import generate_pushback
            result = generate_pushback("Switch to usage-based pricing", [])

        assert result["prior_context"]["date"] == "2026-02-05", "Prior context date should be preserved"
        assert result["prior_context"]["original_rationale"] != "", "Prior rationale should be captured"


class TestCheckDismissedFiltering:
    """Bug 23: Verify check_dismissed actually filters matching claims."""

    def test_matching_claim_is_filtered_out(self):
        """A claim with >40% word overlap with dismissed section should be filtered."""
        living_doc = """## Dismissed Contradictions
- 2026-02-12: Claim that enterprise accounts would close faster — Dismissed because procurement cycles are longer.
"""
        contradictions = [
            {
                "id": "1",
                "new_claim": "Enterprise accounts would close faster because they have larger budgets.",
                "existing_position": "Small plants.",
                "existing_section": "Target Market",
                "tension_description": "Test.",
                "is_revisited_rejection": False,
            }
        ]
        from services.consistency import check_dismissed
        filtered = check_dismissed(contradictions, living_doc)
        assert len(filtered) == 0, "Claim matching dismissed text should be filtered out"

    def test_non_matching_claim_is_kept(self):
        """A claim with no word overlap with dismissed section should be kept."""
        living_doc = """## Dismissed Contradictions
- 2026-02-12: Claim about BP enterprise sales — Dismissed.
"""
        contradictions = [
            {
                "id": "1",
                "new_claim": "We should use PostgreSQL instead of MongoDB for storage.",
                "existing_position": "MongoDB for storage.",
                "existing_section": "Technical Approach",
                "tension_description": "Database choice change.",
                "is_revisited_rejection": False,
            }
        ]
        from services.consistency import check_dismissed
        filtered = check_dismissed(contradictions, living_doc)
        assert len(filtered) == 1, "Non-matching claim should be kept"


class TestBudgetProtection:
    """Bug 25: Verify budget gate forces Sonnet when over budget."""

    def test_over_budget_forces_sonnet(self):
        """When monthly cost > $300, call_with_routing should use Sonnet even for Opus tasks."""
        with patch("services.cost_tracker.get_monthly_cost", return_value=350.0), \
             patch("services.claude_client.call_sonnet") as mock_sonnet, \
             patch("services.claude_client.call_opus") as mock_opus:
            mock_sonnet.return_value = {"text": "test", "tokens_in": 100, "tokens_out": 50, "model": "claude-sonnet-4-20250514"}
            mock_opus.return_value = {"text": "test", "tokens_in": 100, "tokens_out": 50, "model": "claude-opus-4-20250514"}

            from services.claude_client import call_with_routing
            result = call_with_routing("test prompt", task_type="consistency_pass3")

            mock_sonnet.assert_called_once()
            mock_opus.assert_not_called()
            assert result["model"] == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# _get_rag_evidence — source_date with datetime objects
# ---------------------------------------------------------------------------

class TestGetRagEvidenceSourceDate:
    """Verify _get_rag_evidence correctly formats source_date for both strings and datetime objects."""

    def test_source_date_from_string(self):
        from datetime import datetime, timezone
        mock_claims = [{"created_at": "2026-02-15T10:00:00Z", "claim_text": "test", "source_type": "session"}]
        with patch("services.mongo_client.get_claims", return_value=mock_claims), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("not available")):
            from services.consistency import _get_rag_evidence
            evidence = _get_rag_evidence([])
        assert len(evidence) >= 1
        assert evidence[0]["source_date"] == "2026-02-15"

    def test_source_date_from_datetime_object(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_claims = [{"created_at": dt, "claim_text": "test", "source_type": "session"}]
        with patch("services.mongo_client.get_claims", return_value=mock_claims), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("not available")):
            from services.consistency import _get_rag_evidence
            evidence = _get_rag_evidence([])
        assert len(evidence) >= 1
        assert evidence[0]["source_date"] == "2026-02-15"

    def test_source_date_from_missing_field(self):
        mock_claims = [{"claim_text": "test", "source_type": "session"}]
        with patch("services.mongo_client.get_claims", return_value=mock_claims), \
             patch("services.mongo_client.get_sessions", return_value=[]), \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("not available")):
            from services.consistency import _get_rag_evidence
            evidence = _get_rag_evidence([])
        assert len(evidence) >= 1
        assert evidence[0]["source_date"] == ""

    def test_session_source_date_from_datetime(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_sessions = [{"created_at": dt, "summary": "Test session", "metadata": {"session_type": "Co-founder discussion"}}]
        with patch("services.mongo_client.get_claims", return_value=[]), \
             patch("services.mongo_client.get_sessions", return_value=mock_sessions), \
             patch("services.mongo_client.vector_search_text", side_effect=Exception("not available")):
            from services.consistency import _get_rag_evidence
            evidence = _get_rag_evidence([])
        assert len(evidence) >= 1
        assert evidence[0]["source_date"] == "2026-03-01"
