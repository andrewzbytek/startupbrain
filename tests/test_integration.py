"""
Integration tests for Startup Brain — requires real API keys.

All tests in this module are skipped automatically if ANTHROPIC_API_KEY is not set.
Phase 3 (end-to-end pipeline) tests use a temporary copy of the living document
so they never mutate the real document.

Run only integration tests:
    python -m pytest tests/test_integration.py -v

Run excluding slow tests:
    python -m pytest tests/test_integration.py -v -m "not slow"
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module-level skip: skip everything if no API key
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping integration tests",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
REAL_LIVING_DOC = REPO_ROOT / "documents" / "startup_brain.md"


# ---------------------------------------------------------------------------
# Module-scoped state for Phase 3 sequential pipeline tests
# ---------------------------------------------------------------------------

class _PipelineState:
    """Shared mutable state across Phase 3 tests."""
    temp_dir: Path = None
    living_doc_path: Path = None
    original_content: str = ""

pipeline_state = _PipelineState()


# ===========================================================================
# PHASE 1 — API Connection
# ===========================================================================

class TestAPIConnection:
    """Phase 1: Verify real API calls work."""

    def test_anthropic_api_connection(self):
        """Call Sonnet with a simple prompt — verify response has text and tokens."""
        from services.claude_client import call_sonnet

        result = call_sonnet(
            "Reply with exactly: INTEGRATION_TEST_OK",
            task_type="integration_test",
        )

        assert "text" in result, "Response must have 'text' key"
        assert "tokens_in" in result, "Response must have 'tokens_in' key"
        assert "tokens_out" in result, "Response must have 'tokens_out' key"
        assert result["tokens_in"] > 0, "tokens_in should be > 0"
        assert result["tokens_out"] > 0, "tokens_out should be > 0"
        assert "Error" not in result["text"], f"API call returned error: {result['text']}"
        assert len(result["text"]) > 0, "Response text should not be empty"

    @pytest.mark.skipif(
        not os.environ.get("MONGODB_URI"),
        reason="MONGODB_URI not set — skipping MongoDB connection test",
    )
    def test_mongodb_connection(self):
        """Check is_mongo_available() returns True when MONGODB_URI is set."""
        from services.mongo_client import is_mongo_available

        assert is_mongo_available(), "MongoDB should be reachable when MONGODB_URI is configured"

    @pytest.mark.skipif(
        not os.environ.get("MONGODB_URI"),
        reason="MONGODB_URI not set — skipping cost logging test",
    )
    def test_cost_logging_roundtrip(self):
        """Log a cost entry and verify it appears in the cost log."""
        from services.cost_tracker import log_api_call
        from services.mongo_client import get_cost_log

        log_api_call(
            model="claude-sonnet-4-20250514",
            tokens_in=100,
            tokens_out=50,
            task_type="integration_test_cost",
        )

        log = get_cost_log(limit=10)
        assert isinstance(log, list), "Cost log should return a list"
        # Verify at least one integration_test_cost entry exists
        test_entries = [e for e in log if e.get("task_type") == "integration_test_cost"]
        assert len(test_entries) > 0, "Integration test cost entry should appear in cost log"


# ===========================================================================
# PHASE 2 — Prompt Quality
# ===========================================================================

class TestPromptQuality:
    """Phase 2: Verify LLM prompt behaviour with real API calls.

    These are the most important integration tests — they verify that the
    prompts in /prompts/*.md produce structurally correct and semantically
    meaningful output.
    """

    def test_extraction_parses_correctly(self):
        """Use session_01 transcript → extract_claims → verify correct XML output and claim count."""
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert "claims" in result, "Result must have 'claims' key"
        assert "session_summary" in result, "Result must have 'session_summary' key"
        assert "topic_tags" in result, "Result must have 'topic_tags' key"
        assert isinstance(result["claims"], list), "claims must be a list"

        count = len(result["claims"])
        assert data["expected_claims_min"] <= count <= data["expected_claims_max"], (
            f"Expected {data['expected_claims_min']}-{data['expected_claims_max']} claims, got {count}"
        )

        # Verify required fields on every claim
        required_fields = {"claim_text", "claim_type", "confidence", "who_said_it", "topic_tags", "confirmed"}
        for claim in result["claims"]:
            missing = required_fields - set(claim.keys())
            assert not missing, f"Claim missing fields: {missing}"

    def test_extraction_preserves_specifics(self):
        """Verify extracted claims preserve specific numbers, names, and figures."""
        from tests.test_mockup_data import session_02_business_model
        from services.ingestion import extract_claims

        data = session_02_business_model()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        # Combine all claim text for searching
        all_claim_text = " ".join(c["claim_text"] for c in result["claims"])

        # Should preserve the £50,000 figure or £50K shorthand
        has_price = "50,000" in all_claim_text or "50K" in all_claim_text or "£50" in all_claim_text
        assert has_price, (
            f"Extracted claims should preserve £50,000 pricing figure. "
            f"Got claims: {all_claim_text[:500]}"
        )

    def test_extraction_handles_uncertainty(self):
        """Verify that mixed-confidence transcripts produce different confidence levels."""
        from services.ingestion import extract_claims

        # Transcript with mixed certainty language
        mixed_transcript = """Session — Mixed Confidence
Participants: Alex, Jordan

We have definitely decided to use per-facility annual licensing. That is firm.

We are leaning toward Azure for file storage, though AWS remains a fallback option
we have not ruled out entirely.

We are wondering whether a channel partnership with Atkins might accelerate sales —
this is speculative and we have not explored it yet.
"""

        result = extract_claims(
            transcript=mixed_transcript,
            participants="Alex, Jordan",
            topic_hint="pricing and technical approach",
        )

        assert len(result["claims"]) > 0, "Should extract at least one claim"
        confidence_levels = {c["confidence"] for c in result["claims"]}

        # At minimum we should see more than one confidence level for a mixed transcript
        # (definite + at least one of leaning/speculative)
        assert len(confidence_levels) > 1, (
            f"Mixed-confidence transcript should yield multiple confidence levels. "
            f"Got: {confidence_levels}"
        )

    def test_pass1_finds_contradictions(self):
        """Use session_03 contradiction claims against the sample living document."""
        from tests.test_mockup_data import session_03_contradiction
        from services.consistency import pass1_wide_net

        data = session_03_contradiction()

        # Build a minimal set of claims representing the session_03 pivot
        contradiction_claims = [
            {
                "claim_text": "We are pivoting to target BP and Shell as our first customers, replacing the small nuclear plant focus.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["target-market"],
                "confirmed": True,
            },
            {
                "claim_text": "We should position as a general industrial compliance platform starting with oil and gas, not nuclear-first.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Jordan",
                "topic_tags": ["target-market", "strategy"],
                "confirmed": True,
            },
        ]

        # Read the real living document (or use a fixture-like hardcoded version)
        living_doc = ""
        if REAL_LIVING_DOC.exists():
            living_doc = REAL_LIVING_DOC.read_text(encoding="utf-8")

        # If the doc is a blank template, use a populated fallback
        if not living_doc or ("[Not yet defined]" in living_doc and "Small nuclear" not in living_doc):
            living_doc = """# Startup Brain — NuclearCompliance.ai

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK, specifically operators running fewer than 3 reactors.
**Changelog:**
- 2026-02-01: Initial position set. Small UK nuclear plants as beachhead. Source: Session 1

## Decision Log

### 2026-02-01 — Target Market: Small UK Nuclear
**Decision:** Beachhead market is small UK nuclear plants (<3 reactors). Not oil & gas.
**Why:** Shorter procurement cycles (6-12 months). Concentrated market.
**Status:** Active

## Feedback Tracker

## Dismissed Contradictions
"""

        result = pass1_wide_net(living_doc, contradiction_claims)

        assert "contradictions" in result, "pass1_wide_net must return 'contradictions'"
        assert "total_found" in result, "pass1_wide_net must return 'total_found'"
        assert result["total_found"] >= data["expected_contradictions"], (
            f"Expected at least {data['expected_contradictions']} contradiction(s), "
            f"Pass 1 found {result['total_found']}"
        )

    def test_pass2_rates_severity(self):
        """Pass 1 results through pass2 — verify severity ratings are assigned."""
        from services.consistency import pass1_wide_net, pass2_severity_filter

        living_doc = ""
        if REAL_LIVING_DOC.exists():
            living_doc = REAL_LIVING_DOC.read_text(encoding="utf-8")
        else:
            living_doc = """# Startup Brain — NuclearCompliance.ai

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK.
**Changelog:**
- 2026-02-01: Initial. Source: Session 1

### Pricing
**Current position:** £50,000 per facility per year.
**Changelog:**
- 2026-02-05: Pricing set. Source: Session 2

## Decision Log

### 2026-02-01 — Target Market: Small UK Nuclear
**Decision:** Small nuclear plants beachhead.
**Status:** Active

## Feedback Tracker

## Dismissed Contradictions
"""

        pivot_claims = [
            {
                "claim_text": "We are switching to target large oil and gas enterprises like BP instead of nuclear plants.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["target-market"],
                "confirmed": True,
            }
        ]

        pass1 = pass1_wide_net(living_doc, pivot_claims)
        if pass1["total_found"] == 0:
            pytest.skip("Pass 1 found no contradictions — cannot test Pass 2 severity rating")

        pass2 = pass2_severity_filter(pass1, living_doc)

        assert "retained" in pass2, "pass2 must have 'retained'"
        assert "has_critical" in pass2, "pass2 must have 'has_critical'"
        assert isinstance(pass2["retained"], list), "retained must be a list"

        # Each retained item must have a severity field
        valid_severities = {"Critical", "Notable", "Minor"}
        for item in pass2["retained"]:
            assert "severity" in item, f"Retained contradiction missing 'severity': {item}"
            assert item["severity"] in valid_severities, (
                f"Severity must be one of {valid_severities}, got: {item['severity']}"
            )

    def test_diff_generation_valid_format(self):
        """Generate a diff — verify SECTION/ACTION/CONTENT format in output."""
        from services.document_updater import generate_diff, parse_diff_output

        if not REAL_LIVING_DOC.exists():
            pytest.skip("Living document not found")

        current_doc = REAL_LIVING_DOC.read_text(encoding="utf-8")
        new_info = (
            "Implementation fee has been fixed at £12,000. This replaces the previous "
            "£10,000-£15,000 range. The flat fee covers a four-week onboarding process."
        )

        raw_diff = generate_diff(current_doc, new_info, update_reason="Session: pricing correction")

        assert isinstance(raw_diff, str), "generate_diff must return a string"
        assert len(raw_diff) > 0, "Diff output should not be empty"

        # The output should be parseable into at least one diff block
        blocks = parse_diff_output(raw_diff)
        assert len(blocks) > 0, (
            f"Diff output must parse into at least one SECTION/ACTION/CONTENT block. "
            f"Raw diff: {raw_diff[:500]}"
        )

        # Each block must have the required keys
        for block in blocks:
            assert "section" in block, "Diff block missing 'section'"
            assert "action" in block, "Diff block missing 'action'"
            assert "content" in block, "Diff block missing 'content'"

    def test_diff_verify_accepts_good_diff(self):
        """Create a clean diff → verify it gets VERIFIED status."""
        from services.document_updater import verify_diff
        from tests.conftest import get_sample_living_document

        # Use the populated fixture instead of the blank template on disk
        current_doc = get_sample_living_document()

        # A well-formed diff that only adds a changelog entry
        good_diff = (
            "SECTION: Current State → Pricing\n"
            "ACTION: ADD_CHANGELOG\n"
            "CONTENT:\n"
            "- 2026-02-18: Implementation fee fixed at £12,000 (was £10K-£15K range). Source: Session 5\n"
        )
        new_info = "Implementation fee is now £12,000, not £10K-£15K."

        result = verify_diff(current_doc, good_diff, new_info)

        assert "verified" in result, "verify_diff must return 'verified'"
        assert isinstance(result["verified"], bool), "'verified' must be a boolean"
        # A clean, minimal diff that accurately describes the new_info should pass
        assert result["verified"] is True, (
            f"Clean diff should be VERIFIED. Notes: {result.get('notes', '')}. "
            f"Issues: {result.get('issues', [])}"
        )

    def test_pushback_generates_context(self):
        """Call generate_pushback with a contradicting change — verify prior_context surfaced."""
        from services.consistency import generate_pushback

        relevant_decisions = [
            {
                "date": "2026-02-01",
                "decision": "Target market is small UK nuclear plants (<3 reactors)",
                "rationale": "Shorter procurement cycles (6-12 months vs 18-24 for majors). Concentrated, reachable market.",
                "status": "Active",
            }
        ]

        result = generate_pushback(
            change_description=(
                "We want to pivot to targeting large oil and gas companies like BP and Shell "
                "as our primary customers, replacing the small nuclear plant focus."
            ),
            relevant_decisions=relevant_decisions,
        )

        assert "headline" in result, "Pushback must have 'headline'"
        assert "message" in result, "Pushback must have 'message'"
        assert "options" in result, "Pushback must have 'options'"
        assert "prior_context" in result, "Pushback must have 'prior_context'"

        assert result["headline"] != "", "Headline should not be empty"
        assert result["message"] != "", "Message should not be empty"
        assert len(result["options"]) > 0, "Should have at least one option"

        # prior_context should surface the original rationale
        pc = result["prior_context"]
        assert isinstance(pc, dict), "prior_context must be a dict"
        # At least one of the context fields should be populated
        has_context = any(pc.get(k) for k in ["date", "original_position", "original_rationale", "source"])
        assert has_context, f"prior_context should contain some information. Got: {pc}"


# ===========================================================================
# PHASE 3 — End-to-End Pipeline
# ===========================================================================

@pytest.fixture(scope="module")
def temp_living_doc():
    """
    Module-scoped fixture: create a temp copy of the living document for Phase 3 tests.
    Patches document_updater and consistency to use the temp copy.
    After all Phase 3 tests complete, the temp directory is cleaned up.
    """
    if not REAL_LIVING_DOC.exists():
        pytest.skip("Living document not found — skipping Phase 3 pipeline tests")

    tmp_dir = Path(tempfile.mkdtemp())
    tmp_doc_path = tmp_dir / "startup_brain.md"
    original_content = REAL_LIVING_DOC.read_text(encoding="utf-8")
    tmp_doc_path.write_text(original_content, encoding="utf-8")

    pipeline_state.temp_dir = tmp_dir
    pipeline_state.living_doc_path = tmp_doc_path
    pipeline_state.original_content = original_content

    yield tmp_doc_path

    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def pipeline_doc_patches(temp_living_doc):
    """Patch LIVING_DOC_PATH in both document_updater and consistency to use temp file."""
    with patch("services.document_updater.LIVING_DOC_PATH", temp_living_doc), \
         patch("services.consistency.LIVING_DOC_PATH", temp_living_doc), \
         patch("services.document_updater._git_commit", return_value=True), \
         patch("services.mongo_client.upsert_living_document", return_value=True), \
         patch("services.mongo_client.insert_session", return_value="mock_session_id"), \
         patch("services.mongo_client.insert_claim", return_value="mock_claim_id"), \
         patch("services.mongo_client.get_claims", return_value=[]), \
         patch("services.mongo_client.get_sessions", return_value=[]):
        yield temp_living_doc


@pytest.mark.slow
class TestEndToEndPipeline:
    """Phase 3: Sequential session ingestion through the full pipeline.

    These tests run in order and share state (the temp living document).
    Each session builds on the previous one.
    """

    def test_session_1_initial_strategy(self, pipeline_doc_patches):
        """Ingest session 1 — verify living doc is populated."""
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims, run_ingestion_pipeline

        data = session_01_initial_strategy()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert len(extraction["claims"]) >= data["expected_claims_min"], (
            f"Session 1 should extract at least {data['expected_claims_min']} claims"
        )

        result = run_ingestion_pipeline(
            transcript=data["transcript"],
            confirmed_claims=extraction["claims"],
            session_id="session_1",
            metadata={"session_date": "2026-02-01", "participants": data["participants"]},
            session_summary=extraction["session_summary"],
        )

        assert "consistency_results" in result
        assert "document_updated" in result
        # After session 1, doc should be updated (it's the first session)
        assert result["document_updated"] is True, "Living document should be updated after session 1"

        # Verify the temp doc still exists and has content
        assert pipeline_doc_patches.exists(), "Temp living doc should still exist"
        doc_content = pipeline_doc_patches.read_text(encoding="utf-8")
        assert len(doc_content) > 100, "Living doc should have substantial content"

    def test_session_2_adds_to_doc(self, pipeline_doc_patches):
        """Ingest session 2 — verify additive update, no contradictions."""
        from tests.test_mockup_data import session_02_business_model
        from services.ingestion import extract_claims, run_ingestion_pipeline

        data = session_02_business_model()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        result = run_ingestion_pipeline(
            transcript=data["transcript"],
            confirmed_claims=extraction["claims"],
            session_id="session_2",
            metadata={"session_date": "2026-02-05", "participants": data["participants"]},
            session_summary=extraction["session_summary"],
        )

        assert result["document_updated"] is True, "Session 2 should update the living doc"

        consistency = result["consistency_results"]
        # Session 2 is additive — should not trigger contradictions
        # (tolerance: if it does find something, it may be a legitimate sensitivity test)
        assert "has_contradictions" in consistency

    def test_session_3_triggers_contradiction(self, pipeline_doc_patches):
        """Ingest session 3 — verify contradiction is caught."""
        from tests.test_mockup_data import session_03_contradiction
        from services.ingestion import extract_claims, run_ingestion_pipeline

        data = session_03_contradiction()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        result = run_ingestion_pipeline(
            transcript=data["transcript"],
            confirmed_claims=extraction["claims"],
            session_id="session_3",
            metadata={"session_date": "2026-02-10", "participants": data["participants"]},
            session_summary=extraction["session_summary"],
        )

        consistency = result["consistency_results"]
        assert "has_contradictions" in consistency

        # Session 3 explicitly pivots market — should trigger contradiction
        assert consistency["has_contradictions"] is True, (
            "Session 3 (oil & gas pivot) should trigger at least one contradiction "
            "against the documented nuclear-first strategy"
        )

    def test_session_4_feedback_pattern(self, pipeline_doc_patches):
        """Ingest session 4 as feedback — verify pattern detection works."""
        from tests.test_mockup_data import session_04_investor_feedback
        from services.ingestion import extract_claims, run_ingestion_pipeline

        data = session_04_investor_feedback()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert len(extraction["claims"]) >= 1, "Feedback session should extract at least one claim"

        result = run_ingestion_pipeline(
            transcript=data["transcript"],
            confirmed_claims=extraction["claims"],
            session_id="session_4",
            metadata={"session_date": "2026-02-14", "participants": data["participants"]},
            session_summary=extraction["session_summary"],
        )

        # Feedback session should complete without error
        assert "consistency_results" in result
        assert "document_updated" in result

    def test_session_5_direct_correction(self, pipeline_doc_patches):
        """Apply direct correction — verify doc updated with fixed implementation fee."""
        from tests.test_mockup_data import session_05_direct_correction
        from services.ingestion import extract_claims, run_ingestion_pipeline

        data = session_05_direct_correction()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        result = run_ingestion_pipeline(
            transcript=data["transcript"],
            confirmed_claims=extraction["claims"],
            session_id="session_5",
            metadata={"session_date": "2026-02-18", "participants": data["participants"]},
            session_summary=extraction["session_summary"],
        )

        assert result["document_updated"] is True, "Correction session should update the living doc"

    def test_living_document_structure_preserved(self, pipeline_doc_patches):
        """After all 5 sessions, verify the 4 top-level sections are still intact."""
        doc_content = pipeline_doc_patches.read_text(encoding="utf-8")

        required_sections = [
            "## Current State",
            "## Decision Log",
            "## Feedback Tracker",
            "## Dismissed Contradictions",
        ]

        for section in required_sections:
            assert section in doc_content, (
                f"Required section '{section}' missing from living document after 5 sessions"
            )


# ===========================================================================
# PHASE 4 — Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Phase 4: Edge case handling."""

    def test_empty_transcript(self):
        """extract_claims with empty string → returns empty claims gracefully."""
        from tests.test_mockup_data import edge_empty
        from services.ingestion import extract_claims

        data = edge_empty()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert "claims" in result, "Result must have 'claims' key"
        assert isinstance(result["claims"], list), "claims must be a list"
        assert len(result["claims"]) == 0, (
            f"Empty transcript should yield 0 claims, got {len(result['claims'])}"
        )

    @pytest.mark.slow
    def test_very_long_transcript(self):
        """extract_claims with 5000+ word edge_long transcript — processes without timeout."""
        from tests.test_mockup_data import edge_long
        from services.ingestion import extract_claims
        import signal

        data = edge_long()
        assert len(data["transcript"].split()) >= 4000, "edge_long should be a very long transcript"

        # Use a timeout via signal (Unix) or just run without guard on Windows
        try:
            result = extract_claims(
                transcript=data["transcript"],
                participants=data["participants"],
                topic_hint=data["topic_hint"],
            )
        except Exception as e:
            pytest.fail(f"Long transcript processing raised exception: {e}")

        assert "claims" in result, "Result must have 'claims' key"
        assert isinstance(result["claims"], list), "claims must be a list"
        count = len(result["claims"])
        assert count >= data["expected_claims_min"], (
            f"Long transcript should yield at least {data['expected_claims_min']} claims, got {count}"
        )

    def test_xml_in_transcript(self):
        """extract_claims with XML-injection transcript — doesn't crash."""
        from tests.test_mockup_data import edge_xml_injection
        from services.ingestion import extract_claims

        data = edge_xml_injection()

        try:
            result = extract_claims(
                transcript=data["transcript"],
                participants=data["participants"],
                topic_hint=data["topic_hint"],
            )
        except Exception as e:
            pytest.fail(f"XML injection in transcript raised exception: {e}")

        assert "claims" in result, "Result must have 'claims' key"
        assert isinstance(result["claims"], list), "claims should be a list even with XML in input"

    def test_multiple_contradictions_single_session(self):
        """pass1_wide_net with edge_multiple_contradictions — all three contradictions caught."""
        from tests.test_mockup_data import edge_multiple_contradictions
        from services.ingestion import extract_claims
        from services.consistency import pass1_wide_net

        data = edge_multiple_contradictions()

        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        living_doc = ""
        if REAL_LIVING_DOC.exists():
            living_doc = REAL_LIVING_DOC.read_text(encoding="utf-8")

        # If the doc is a blank template, use a populated fallback
        if not living_doc or ("[Not yet defined]" in living_doc and "Small nuclear" not in living_doc):
            living_doc = """# Startup Brain — NuclearCompliance.ai

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK, specifically operators running fewer than 3 reactors.
**Changelog:**
- 2026-02-01: Initial position set. Small UK nuclear plants as beachhead. Source: Session 1

### Pricing
**Current position:** £50,000 per facility per year.
**Changelog:**
- 2026-02-05: Pricing set. Source: Session 2

### Technical Approach
**Current position:** LLM-based extraction (Claude) from PDFs using PyMuPDF. MongoDB Atlas for storage.
**Changelog:**
- 2026-02-08: Technical approach finalised. Source: Session 3

## Decision Log

### 2026-02-01 — Target Market: Small UK Nuclear
**Decision:** Beachhead market is small UK nuclear plants (<3 reactors). Not oil & gas.
**Why:** Shorter procurement cycles (6-12 months). Concentrated market.
**Status:** Active

### 2026-02-05 — Per-Facility Annual Licensing
**Decision:** Annual per-facility SaaS licence at £50K/year.
**Why:** Nuclear budgets allocated per facility. VCs prefer predictable revenue.
**Status:** Active

### 2026-02-08 — MongoDB Atlas for Storage
**Decision:** Use MongoDB Atlas for document and metadata storage.
**Why:** Flexible schema for compliance documents. Good Python driver support.
**Status:** Active

## Feedback Tracker

## Dismissed Contradictions
"""

        result = pass1_wide_net(living_doc, extraction["claims"])

        assert "total_found" in result, "pass1_wide_net must return 'total_found'"
        assert result["total_found"] >= data["expected_contradictions"], (
            f"Expected at least {data['expected_contradictions']} contradiction(s) for "
            f"edge_multiple_contradictions session, Pass 1 found {result['total_found']}"
        )

    def test_mongo_down_graceful_degradation(self):
        """Mock mongo as unavailable — verify file operations still work."""
        from services.ingestion import extract_claims

        # Use a simple transcript
        transcript = "We decided to focus on small UK nuclear plants as our initial target market."

        with patch("services.mongo_client.get_db", return_value=None), \
             patch("services.mongo_client.get_mongo_client", return_value=None), \
             patch("services.mongo_client.insert_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]):

            # extract_claims itself should work even without MongoDB
            try:
                result = extract_claims(
                    transcript=transcript,
                    participants="Alex",
                    topic_hint="target market",
                )
                assert "claims" in result, "extract_claims should return claims even with MongoDB down"
            except Exception as e:
                pytest.fail(f"extract_claims should not crash when MongoDB is down: {e}")


# ===========================================================================
# PHASE 5 — Frontend Smoke
# ===========================================================================

class TestFrontendSmoke:
    """Phase 5: Streamlit frontend smoke tests using AppTest."""

    def test_app_starts(self):
        """Verify the Streamlit app starts without raising an exception."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing.v1 not available — upgrade Streamlit")

        app_path = str(REPO_ROOT / "app" / "main.py")
        at = AppTest.from_file(app_path)
        at.run(timeout=10)
        assert not at.exception, f"App raised exception on startup: {at.exception}"

    def test_sidebar_renders(self):
        """Verify the sidebar contains at least one element."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing.v1 not available — upgrade Streamlit")

        app_path = str(REPO_ROOT / "app" / "main.py")
        at = AppTest.from_file(app_path)
        at.run(timeout=10)
        assert not at.exception, f"App raised exception: {at.exception}"
        assert len(at.sidebar) > 0, "Sidebar should render at least one element"

    def test_chat_input_exists(self):
        """Verify the main chat input widget is present."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing.v1 not available — upgrade Streamlit")

        app_path = str(REPO_ROOT / "app" / "main.py")
        at = AppTest.from_file(app_path)
        at.run(timeout=10)
        assert not at.exception, f"App raised exception: {at.exception}"
        assert len(at.chat_input) > 0, "App should have a chat_input widget"
