"""
Integration tests for Startup Brain — requires real API keys.

All tests in this module are skipped automatically if ANTHROPIC_API_KEY is not set.
Tests marked @pytest.mark.slow involve multiple LLM calls or Opus routing.
Tests requiring MongoDB are individually skipped if MONGODB_URI is not set.

Run only integration tests:
    python -m pytest tests/ -m integration -v
    python -m pytest tests/test_integration.py -v

Run excluding slow tests:
    python -m pytest tests/test_integration.py -v -m "not slow"
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module-level skip: skip everything if no API key
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — skipping integration tests",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _mongo_skip():
    return pytest.mark.skipif(
        not os.environ.get("MONGODB_URI"),
        reason="MONGODB_URI not set",
    )


# ===========================================================================
# 1. TestAPIConnection (3 tests)
# ===========================================================================

class TestAPIConnection:
    """Verify real API calls work."""

    def test_anthropic_sonnet_connection(self):
        """call_sonnet returns text + tokens."""
        from services.claude_client import call_sonnet

        result = call_sonnet(
            "Reply with exactly: INTEGRATION_TEST_OK",
            task_type="integration_test",
        )

        assert "text" in result
        assert result["tokens_in"] > 0
        assert result["tokens_out"] > 0
        assert len(result["text"]) > 0

    @_mongo_skip()
    def test_mongodb_connection(self):
        """is_mongo_available() True when MONGODB_URI is set."""
        from services.mongo_client import is_mongo_available

        assert is_mongo_available()

    @_mongo_skip()
    def test_cost_logging_roundtrip(self):
        """log_api_call + get_cost_log roundtrip."""
        from services.cost_tracker import log_api_call
        from services.mongo_client import get_cost_log

        log_api_call(
            model="claude-sonnet-4-20250514",
            tokens_in=100,
            tokens_out=50,
            task_type="integration_test_cost",
        )

        log = get_cost_log(limit=10)
        assert isinstance(log, list)
        test_entries = [e for e in log if e.get("task_type") == "integration_test_cost"]
        assert len(test_entries) > 0


# ===========================================================================
# 2. TestPitchExtraction (5 tests)
# ===========================================================================

class TestPitchExtraction:
    """Verify pitch claim extraction prompt quality."""

    def test_extraction_parses_correctly(self):
        """session_01 -> extract_claims -> correct structure and claim count."""
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert isinstance(result["claims"], list)
        assert "session_summary" in result
        assert "topic_tags" in result
        count = len(result["claims"])
        assert data["expected_claims_min"] <= count <= data["expected_claims_max"] * 2, (
            f"Expected {data['expected_claims_min']}-{data['expected_claims_max']*2} claims, got {count}"
        )

        # Each claim has required fields
        for claim in result["claims"]:
            assert "claim_text" in claim
            assert "claim_type" in claim
            assert "confidence" in claim

    def test_extraction_preserves_specifics(self):
        """session_02 mentions £50,000 — verify specific figures preserved."""
        from tests.test_mockup_data import session_02_business_model
        from services.ingestion import extract_claims

        data = session_02_business_model()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        all_text = " ".join(c["claim_text"] for c in result["claims"]).lower()
        assert "50" in all_text or "£50" in all_text.replace(",", ""), (
            f"£50,000 figure should be preserved in claims. Got: {all_text[:500]}"
        )

    def test_extraction_handles_uncertainty(self):
        """Mixed-confidence transcript yields multiple confidence levels."""
        from tests.test_mockup_data import session_04_investor_feedback
        from services.ingestion import extract_claims

        data = session_04_investor_feedback()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        confidence_levels = {c.get("confidence", "unknown") for c in result["claims"]}
        assert len(confidence_levels) > 1, (
            f"Mixed-confidence transcript should yield multiple confidence levels. Got: {confidence_levels}"
        )

    def test_extraction_produces_entities(self):
        """Entity extraction produces non-empty entities with recognizable names."""
        from tests.test_mockup_data import edge_entity_extraction
        from services.ingestion import extract_claims

        data = edge_entity_extraction()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        # At least one claim should have entities
        claims_with_entities = [c for c in result["claims"] if c.get("entities")]
        assert len(claims_with_entities) > 0, (
            "Entity-dense transcript should produce at least one claim with entities"
        )

        # Check that some recognizable entities appear
        all_entities = []
        for c in result["claims"]:
            all_entities.extend(c.get("entities", []))
        all_entities_lower = [e.lower() for e in all_entities]
        known_entities = {"sarah chen", "marcus webb", "atomica", "compliancedb", "onr", "iso 27001", "alarp"}
        found = {e for e in known_entities if any(e in ent for ent in all_entities_lower)}
        assert len(found) >= 2, (
            f"Expected at least 2 known entities, found: {found}. All entities: {all_entities}"
        )

    def test_extraction_session_type_flows(self):
        """session_type parameter accepted without error."""
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            session_type="Investor meeting",
        )

        assert len(result["claims"]) >= 1


# ===========================================================================
# 3. TestOpsExtraction (3 tests)
# ===========================================================================

class TestOpsExtraction:
    """Verify ops brain claim extraction."""

    def test_ops_extraction_parses_correctly(self):
        """ops_session_01 -> extract_claims with ops prompt -> claims."""
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from services.ingestion import extract_claims

        data = ops_session_01_contacts_and_risks()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )

        assert isinstance(result["claims"], list)
        count = len(result["claims"])
        assert count >= data["expected_claims_min"], (
            f"Expected at least {data['expected_claims_min']} ops claims, got {count}"
        )

    def test_ops_extraction_captures_contacts(self):
        """ops_session_01 should capture contact-related claims."""
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from services.ingestion import extract_claims

        data = ops_session_01_contacts_and_risks()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )

        all_text = " ".join(c["claim_text"] for c in result["claims"]).lower()
        # Should mention at least one of the contacts
        assert "sarah" in all_text or "david" in all_text or "atomica" in all_text, (
            f"Ops extraction should capture contact names. Got: {all_text[:500]}"
        )

    def test_ops_extraction_captures_risks(self):
        """ops_session_01 mentions ONR approval risk — should appear in claims."""
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from services.ingestion import extract_claims

        data = ops_session_01_contacts_and_risks()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )

        all_text = " ".join(c["claim_text"] for c in result["claims"]).lower()
        assert "onr" in all_text or "approval" in all_text or "certification" in all_text or "risk" in all_text, (
            f"Ops extraction should capture risk-related claims. Got: {all_text[:500]}"
        )


# ===========================================================================
# 4. TestConsistencyEngine (5 tests)
# ===========================================================================

class TestConsistencyEngine:
    """Verify consistency check prompt quality."""

    def test_pass1_finds_contradictions(self):
        """Pivot claims vs sample doc -> at least 1 contradiction."""
        from services.consistency import pass1_wide_net
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        pivot_claims = [
            {
                "claim_text": "We are pivoting to target BP and Shell as our first customers, replacing the small nuclear plant focus.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["target-market"],
                "confirmed": True,
            },
        ]

        result = pass1_wide_net(living_doc, pivot_claims)
        assert result["total_found"] >= 1, (
            f"Pivot claim should trigger at least 1 contradiction, found {result['total_found']}"
        )

    def test_pass2_rates_severity(self):
        """Pass 1 -> Pass 2 produces severity ratings."""
        from services.consistency import pass1_wide_net, pass2_severity_filter
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
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
            pytest.skip("Pass 1 found no contradictions — cannot test Pass 2")

        pass2 = pass2_severity_filter(pass1, living_doc)
        assert isinstance(pass2["retained"], list)

        valid_severities = {"Critical", "Notable", "Minor"}
        for item in pass2["retained"]:
            assert item["severity"] in valid_severities, (
                f"Severity must be in {valid_severities}, got: {item['severity']}"
            )

    @pytest.mark.slow
    def test_pass3_deep_analysis(self):
        """Pass 2 critical -> Pass 3 Opus deep analysis."""
        from services.consistency import pass1_wide_net, pass2_severity_filter, pass3_deep_analysis
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        pivot_claims = [
            {
                "claim_text": "We are abandoning the nuclear market entirely and pivoting to pharmaceutical GMP compliance.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["target-market", "strategy"],
                "confirmed": True,
            }
        ]

        pass1 = pass1_wide_net(living_doc, pivot_claims)
        if pass1["total_found"] == 0:
            pytest.skip("Pass 1 found no contradictions")

        pass2 = pass2_severity_filter(pass1, living_doc)
        critical_items = [item for item in pass2["retained"] if item.get("severity") == "Critical"]
        if not critical_items:
            pytest.skip("Pass 2 found no Critical items")

        pass3 = pass3_deep_analysis(critical_items, living_doc, rag_evidence=[])
        assert "analyses" in pass3
        assert len(pass3["analyses"]) >= 1

    def test_consistency_with_speculative_claims(self):
        """Hypothesis claims that contradict doc should be detected."""
        from services.consistency import pass1_wide_net
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        speculative_claims = [
            {
                "claim_text": "We think usage-based pricing at £0.05 per document might work better than annual licensing.",
                "claim_type": "hypothesis",
                "confidence": "speculative",
                "who_said_it": "Jordan",
                "topic_tags": ["pricing"],
                "confirmed": True,
            }
        ]

        result = pass1_wide_net(living_doc, speculative_claims)
        # Usage-based pricing was explicitly rejected in the Decision Log
        assert result["total_found"] >= 1, (
            "Speculative claim about usage-based pricing should trigger contradiction with Decision Log"
        )

    def test_pushback_generates_context(self):
        """generate_pushback returns structured pushback with prior_context."""
        from services.consistency import generate_pushback

        relevant_decisions = [
            {
                "date": "2026-02-01",
                "decision": "Target market is small UK nuclear plants (<3 reactors)",
                "rationale": "Shorter procurement cycles (6-12 months vs 18-24 for majors).",
                "status": "Active",
            }
        ]

        result = generate_pushback(
            change_description="We want to pivot to targeting large oil and gas companies like BP.",
            relevant_decisions=relevant_decisions,
        )

        assert result["headline"] != ""
        assert result["message"] != ""
        assert len(result["options"]) > 0
        assert isinstance(result["prior_context"], dict)


# ===========================================================================
# 5. TestDiffEngine (5 tests)
# ===========================================================================

class TestDiffEngine:
    """Verify diff generation, verification, and application."""

    def test_pitch_diff_generation(self):
        """New info vs sample pitch doc -> SECTION/ACTION/CONTENT blocks."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_living_document

        current_doc = get_sample_living_document()
        new_info = (
            "Implementation fee has been fixed at £12,000. This replaces the previous "
            "£10,000-£15,000 range. The flat fee covers a four-week onboarding process."
        )

        raw_diff = generate_diff(current_doc, new_info, update_reason="Session: pricing correction")
        blocks = parse_diff_output(raw_diff)
        assert len(blocks) > 0, f"Should produce at least one diff block. Raw: {raw_diff[:500]}"

        for block in blocks:
            assert "section" in block
            assert "action" in block
            assert "content" in block

    def test_pitch_diff_verify_good(self):
        """Well-formed ADD_CHANGELOG diff passes verification."""
        from services.document_updater import verify_diff
        from tests.conftest import get_sample_living_document

        current_doc = get_sample_living_document()
        good_diff = (
            "SECTION: Current State → Pricing\n"
            "ACTION: ADD_CHANGELOG\n"
            "CONTENT:\n"
            "- 2026-02-18: Implementation fee fixed at £12,000 (was £10K-£15K range). Source: Session 5\n"
        )
        new_info = "Implementation fee is now £12,000, not £10K-£15K."

        result = verify_diff(current_doc, good_diff, new_info)
        assert result["verified"] is True, (
            f"Clean diff should be VERIFIED. Notes: {result.get('notes', '')}. Issues: {result.get('issues', [])}"
        )

    def test_pitch_diff_verify_catches_detail_loss(self):
        """Diff that drops specific numbers should fail verification."""
        from services.document_updater import verify_diff
        from tests.conftest import get_sample_living_document

        current_doc = get_sample_living_document()
        # This diff loses the £50K figure from the current position
        bad_diff = (
            "SECTION: Current State → Pricing\n"
            "ACTION: UPDATE_POSITION\n"
            "CONTENT:\n"
            "**Current position:** Annual per-facility SaaS licence. Implementation fee applies.\n"
        )
        new_info = "Implementation fee is now £12,000."

        result = verify_diff(current_doc, bad_diff, new_info)
        assert result["verified"] is False, (
            "Diff that drops specific pricing figures should fail verification"
        )

    def test_ops_diff_generation(self):
        """Contact info vs sample ops doc -> diff blocks with brain='ops'."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "New contact: Elena Vasquez from Nuclear Skills Organisation. "
            "She runs their digital transformation programme. "
            "Interested in AI adoption across nuclear sector."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="New contact from NIA conference",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        assert len(blocks) > 0, f"Should produce at least one diff block for ops. Raw: {raw_diff[:500]}"

    def test_diff_preserves_specifics(self):
        """UPDATE_POSITION preserves existing numbers from original doc."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_living_document

        current_doc = get_sample_living_document()
        new_info = (
            "We confirmed with two more operators that £50,000 per facility per year is "
            "within their budget. The implementation fee remains at £10,000-£15,000."
        )

        raw_diff = generate_diff(current_doc, new_info, update_reason="Session: pricing confirmation")
        blocks = parse_diff_output(raw_diff)

        # If any UPDATE_POSITION block targets Pricing, it should contain £50
        for block in blocks:
            if block.get("action") == "UPDATE_POSITION" and "Pricing" in block.get("section", ""):
                assert "50" in block["content"], (
                    f"UPDATE_POSITION on Pricing should preserve £50K figure. Got: {block['content'][:300]}"
                )


# ===========================================================================
# 6. TestDeferredWriterPipeline (3 tests, slow)
# ===========================================================================

@pytest.mark.slow
class TestDeferredWriterPipeline:
    """Verify DeferredWriter with real LLM calls but mocked MongoDB."""

    def test_deferred_writer_update_in_memory(self):
        """initialize + apply_document_update_deferred -> changes_applied > 0."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_living_document
        from tests.test_mockup_data import session_05_direct_correction
        from services.ingestion import extract_claims

        data = session_05_direct_correction()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )
        claims = extraction["claims"]
        assert len(claims) >= 1, "Need at least 1 claim for pipeline test"

        writer = DeferredWriter()
        with patch("services.document_updater.read_living_document", return_value=get_sample_living_document()), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-02-18", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                session_type="Co-founder sync",
                brain="pitch",
            )

            new_info = " | ".join(c["claim_text"] for c in claims)
            result = writer.apply_document_update_deferred(
                new_info=new_info,
                update_reason="Session: pricing correction",
            )

            assert result["changes_applied"] > 0, (
                f"Should apply at least one change. Message: {result.get('message', '')}"
            )

    def test_deferred_writer_batch_commit(self):
        """Full pipeline with mocked MongoDB -> success with claims_stored."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_living_document
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )
        claims = extraction["claims"]

        writer = DeferredWriter()
        doc_content = get_sample_living_document()

        with patch("services.document_updater.read_living_document", return_value=doc_content), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.insert_session", return_value="mock_session_id") as mock_session, \
             patch("services.mongo_client.insert_claim", return_value="mock_claim_id") as mock_claim, \
             patch("services.mongo_client.find_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]), \
             patch("services.ingestion_lock.check_lock", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"), \
             patch("services.deferred_writer.save_checkpoint", return_value=True), \
             patch("services.deferred_writer.delete_checkpoint"):

            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-02-01", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                brain="pitch",
            )

            new_info = " | ".join(c["claim_text"] for c in claims)
            writer.apply_document_update_deferred(
                new_info=new_info,
                update_reason="Session: initial strategy",
            )

            result = writer.batch_commit()

            assert result["success"] is True, f"batch_commit should succeed. Message: {result.get('message', '')}"
            assert result["claims_stored"] > 0
            assert result["session_id"] is not None

    def test_deferred_writer_checkpoint_roundtrip(self):
        """to_checkpoint() -> from_checkpoint() preserves all fields."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_living_document
        from services.ingestion import extract_claims
        from tests.test_mockup_data import session_01_initial_strategy

        data = session_01_initial_strategy()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        writer = DeferredWriter()
        with patch("services.document_updater.read_living_document", return_value=get_sample_living_document()):
            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=extraction["claims"],
                metadata={"session_date": "2026-02-01"},
                session_summary=extraction["session_summary"],
                brain="pitch",
            )

        checkpoint = writer.to_checkpoint()
        assert isinstance(checkpoint, dict)

        restored = DeferredWriter.from_checkpoint(checkpoint)
        assert restored.brain == writer.brain
        assert restored.transcript == writer.transcript
        assert len(restored.confirmed_claims) == len(writer.confirmed_claims)
        assert restored.session_summary == writer.session_summary
        assert restored.original_doc == writer.original_doc


# ===========================================================================
# 7. TestOpsIngestionPipeline (2 tests, slow)
# ===========================================================================

@pytest.mark.slow
class TestOpsIngestionPipeline:
    """Verify ops ingestion pipeline with real LLM calls."""

    def test_ops_ingestion_updates_document(self):
        """Ops claims -> run_ops_ingestion -> document_updated."""
        from services.ops_ingestion import run_ops_ingestion
        from services.ingestion import extract_claims
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from tests.conftest import get_sample_ops_document

        data = ops_session_01_contacts_and_risks()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )
        claims = extraction["claims"]
        assert len(claims) >= 1

        with patch("services.document_updater.read_living_document", return_value=get_sample_ops_document()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.insert_session", return_value="mock_session_id"), \
             patch("services.mongo_client.insert_claim", return_value="mock_claim_id"), \
             patch("services.mongo_client.find_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"):

            result = run_ops_ingestion(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-03-01", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                brain="ops",
            )

            assert result["document_updated"] is True, (
                f"Ops ingestion should update document. Message: {result.get('message', '')}"
            )

    def test_ops_ingestion_no_consistency(self):
        """Ops ingestion should NOT call consistency engine."""
        from services.ops_ingestion import run_ops_ingestion
        from services.ingestion import extract_claims
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from tests.conftest import get_sample_ops_document

        data = ops_session_01_contacts_and_risks()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )

        with patch("services.document_updater.read_living_document", return_value=get_sample_ops_document()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.insert_session", return_value="mock_session_id"), \
             patch("services.mongo_client.insert_claim", return_value="mock_claim_id"), \
             patch("services.mongo_client.find_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"), \
             patch("services.consistency.pass1_wide_net") as mock_pass1:

            run_ops_ingestion(
                transcript=data["transcript"],
                confirmed_claims=extraction["claims"],
                metadata={"session_date": "2026-03-01"},
                session_summary=extraction["session_summary"],
                brain="ops",
            )

            mock_pass1.assert_not_called()


# ===========================================================================
# 8. TestContactCRM (4 tests)
# ===========================================================================

class TestContactCRM:
    """Verify contact handling targets Ops brain."""

    def test_contact_add_ops(self):
        """generate_diff with contact info + brain='ops' -> ADD_CONTACT block."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "New contact: Elena Vasquez from Nuclear Skills Organisation. "
            "Role: Digital Transformation Lead. Met at NIA conference. "
            "Interested in AI adoption across nuclear sector."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="New contact from conference",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        assert len(blocks) > 0, f"Should produce diff blocks for new contact. Raw: {raw_diff[:500]}"

        # At least one block should reference contacts
        contact_blocks = [b for b in blocks if "contact" in b.get("section", "").lower()
                          or "contact" in b.get("action", "").lower()]
        assert len(contact_blocks) > 0, (
            f"Should have at least one contact-related block. Blocks: {blocks}"
        )

    def test_batch_contacts_ops(self):
        """Multiple contacts -> multiple diff blocks."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "Met three new contacts at the NIA conference:\n"
            "1. Elena Vasquez, Nuclear Skills Organisation, Digital Transformation Lead\n"
            "2. James Thornton, CTO of ComplianceDB, competitive intel contact\n"
            "3. Lisa Park, Head of Safety Documentation at GridPoint Energy Torness site"
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="NIA conference contacts",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        # Should produce multiple blocks (at least 2 contact additions)
        assert len(blocks) >= 2, (
            f"3 contacts should produce at least 2 diff blocks. Got {len(blocks)}: {blocks}"
        )

    def test_update_contact_ops(self):
        """Existing contact update -> UPDATE action, not duplicate ADD."""
        from services.document_updater import generate_diff, parse_diff_output
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        # Sarah Chen already exists in the ops document
        new_info = (
            "Follow-up with Sarah Chen from Entergy. She confirmed interest in a pilot "
            "starting April 2026. Her team will allocate 2 weeks for document preparation. "
            "Next step: send formal pilot agreement by March 15."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="Contact update: Sarah Chen follow-up",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        assert len(blocks) > 0

        # The diff should update the existing contact, not add a duplicate
        all_content = " ".join(b.get("content", "") for b in blocks).lower()
        assert "sarah" in all_content or "chen" in all_content, (
            f"Diff should reference Sarah Chen. Got: {all_content[:500]}"
        )

    def test_contact_end_to_end(self):
        """generate + parse + apply -> contact appears in updated doc."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "New contact: Dr. Rachel Kim from Sellafield Ltd. "
            "Role: Chief Compliance Officer. Met via warm intro from Sarah Chen."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="New contact from referral",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        if not blocks:
            pytest.skip("Diff generation produced no blocks")

        updated_doc = apply_diff(current_doc, blocks, brain="ops")
        assert "Rachel Kim" in updated_doc or "rachel" in updated_doc.lower(), (
            "New contact should appear in updated document"
        )


# ===========================================================================
# 9. TestLLMEdgeCases (6 tests)
# ===========================================================================

class TestLLMEdgeCases:
    """Verify LLM behavior on edge-case inputs."""

    def test_prompt_injection(self):
        """XML injection transcript -> no HACKER-attributed claims."""
        from tests.test_mockup_data import edge_xml_injection
        from services.ingestion import extract_claims

        data = edge_xml_injection()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        for claim in result["claims"]:
            assert claim.get("who_said_it", "").upper() != "HACKER", (
                f"Injection should not produce HACKER-attributed claims: {claim}"
            )

    def test_unicode_and_special_chars(self):
        """Euro, accents, Yen preserved through extraction."""
        from services.ingestion import extract_claims

        transcript = (
            "Session: International Pricing\n"
            "Date: 2026-03-01\nParticipants: Alex\n\n"
            "Pricing for European markets: €45,000 per facility. "
            "Japanese market entry at ¥7,500,000. "
            "Meeting with François Müller from Électricité de Strasbourg confirmed interest."
        )

        result = extract_claims(
            transcript=transcript,
            participants="Alex",
            topic_hint="international pricing",
        )

        all_text = " ".join(c["claim_text"] for c in result["claims"])
        # At least one special character should survive
        has_special = any(ch in all_text for ch in ["€", "¥", "ç", "ü", "é"])
        assert has_special, (
            f"Special characters (€, ¥, accents) should be preserved. Got: {all_text[:500]}"
        )

    def test_self_contradicting_session(self):
        """Session with internal price discussion -> captures the discussion."""
        from services.ingestion import extract_claims

        transcript = (
            "Session: Pricing Debate\n"
            "Date: 2026-03-02\nParticipants: Alex, Jordan\n\n"
            "Alex proposed raising the price to £75,000 per facility. Jordan argued "
            "we should keep it at £50,000 until we have 3 customers. After discussion, "
            "we agreed to keep £50,000 for now but revisit after customer #3."
        )

        result = extract_claims(
            transcript=transcript,
            participants="Alex, Jordan",
            topic_hint="pricing debate",
        )

        assert len(result["claims"]) >= 1, "Should extract at least 1 claim from pricing debate"

    def test_very_short_transcript(self):
        """Single sentence -> at least 1 claim."""
        from services.ingestion import extract_claims

        result = extract_claims(
            transcript="We decided to target small UK nuclear plants.",
            participants="Alex",
            topic_hint="strategy",
        )

        assert len(result["claims"]) >= 1, "Even a single sentence should extract at least 1 claim"

    def test_empty_transcript(self):
        """Empty transcript -> 0 claims."""
        from services.ingestion import extract_claims

        result = extract_claims(
            transcript="",
            participants="",
            topic_hint="",
        )

        assert len(result["claims"]) == 0, (
            f"Empty transcript should produce 0 claims, got {len(result['claims'])}"
        )

    @pytest.mark.slow
    def test_very_long_transcript(self):
        """5000+ word transcript processes without error."""
        from tests.test_mockup_data import edge_long
        from services.ingestion import extract_claims

        data = edge_long()
        result = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )

        assert len(result["claims"]) >= data["expected_claims_min"], (
            f"Long transcript should extract at least {data['expected_claims_min']} claims, got {len(result['claims'])}"
        )


# ===========================================================================
# 10. TestChatBehavior (4 tests)
# ===========================================================================

class TestChatBehavior:
    """Verify chat query classification and response quality."""

    def test_current_state_cites_document(self):
        """Pricing query -> response includes £50K figure from living doc."""
        from services.claude_client import call_with_routing
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        system_prompt = (
            "You are the AI assistant for a startup called NuclearCompliance.ai. "
            "Here is the current living document:\n\n"
            f"<living_document>\n{living_doc}\n</living_document>\n\n"
            "Answer the user's question based on the document content."
        )

        result = call_with_routing(
            prompt="What is our current pricing?",
            task_type="general",
            system=system_prompt,
        )

        assert "50" in result["text"], (
            f"Response should cite £50K pricing from document. Got: {result['text'][:500]}"
        )

    def test_challenge_routes_to_opus(self):
        """strategic_analysis task type -> substantive response."""
        from services.claude_client import call_with_routing
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        system_prompt = (
            "You are the AI assistant for NuclearCompliance.ai. "
            f"<living_document>\n{living_doc}\n</living_document>"
        )

        result = call_with_routing(
            prompt="Challenge our target market assumption. What are we missing?",
            task_type="strategic_analysis",
            system=system_prompt,
        )

        assert len(result["text"]) > 200, (
            f"Challenge response should be substantive (>200 chars). Got {len(result['text'])} chars"
        )

    def test_feedback_echo_surfaces_names(self):
        """Query about feedback -> response includes investor/contact names from doc."""
        from services.claude_client import call_with_routing
        from tests.conftest import get_sample_living_document

        living_doc = get_sample_living_document()
        # Add some feedback context to the system prompt
        feedback_context = (
            "Feedback Tracker:\n"
            "- Marcus Webb (Frontier Ventures): wants to see traction before investing\n"
            "- Tom Bradley (Hartlepool Nuclear): needs 4-week PoC, not 2 weeks\n"
        )
        system_prompt = (
            "You are the AI assistant for NuclearCompliance.ai.\n"
            f"<living_document>\n{living_doc}\n</living_document>\n"
            f"<feedback>\n{feedback_context}\n</feedback>"
        )

        result = call_with_routing(
            prompt="What feedback have we received from investors and customers?",
            task_type="general",
            system=system_prompt,
        )

        text_lower = result["text"].lower()
        has_name = any(name in text_lower for name in ["marcus", "webb", "tom", "bradley", "frontier"])
        assert has_name, (
            f"Feedback query should surface contact names. Got: {result['text'][:500]}"
        )

    def test_casual_greeting_is_brief(self):
        """Casual greeting -> brief response, no document dump."""
        from services.claude_client import call_with_routing

        result = call_with_routing(
            prompt="Hey, how's it going?",
            task_type="general",
            system="You are a helpful startup assistant. Keep casual responses brief.",
        )

        assert len(result["text"]) < 500, (
            f"Casual greeting should get brief response (<500 chars). Got {len(result['text'])} chars"
        )


# ===========================================================================
# 11. TestBrainIsolation (3 tests)
# ===========================================================================

class TestBrainIsolation:
    """Verify that pitch and ops operations don't cross-contaminate."""

    def test_pitch_diff_does_not_affect_ops_doc(self):
        """Pitch diff applied to pitch doc -> ops doc completely unchanged."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_living_document, get_sample_ops_document

        pitch_doc = get_sample_living_document()
        ops_doc = get_sample_ops_document()

        new_info = (
            "We decided to raise implementation fee to £60,000 per facility. "
            "This replaces the previous £50,000 figure after customer validation."
        )

        raw_diff = generate_diff(
            current_doc=pitch_doc,
            new_info=new_info,
            update_reason="pricing update from customer validation",
            brain="pitch",
        )

        diff_blocks = parse_diff_output(raw_diff)
        assert len(diff_blocks) >= 1, "Should produce at least 1 diff block"

        updated_pitch = apply_diff(pitch_doc, diff_blocks, brain="pitch")

        # Pitch doc should have changed
        assert updated_pitch != pitch_doc, "Pitch doc should be modified by pitch diff"

        # Ops doc must be completely unchanged (apply_diff is pure — no side effects)
        assert ops_doc == get_sample_ops_document(), (
            "Ops document must be completely unchanged after pitch diff operation"
        )

    def test_ops_diff_does_not_affect_pitch_doc(self):
        """Ops diff applied to ops doc -> pitch doc completely unchanged."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_living_document, get_sample_ops_document

        pitch_doc = get_sample_living_document()
        ops_doc = get_sample_ops_document()

        new_info = (
            "New contact: Elena Vasquez from Nuclear Skills Organisation. "
            "Met at NIA conference. Interested in workforce training collaboration."
        )

        raw_diff = generate_diff(
            current_doc=ops_doc,
            new_info=new_info,
            update_reason="new contact from NIA conference",
            brain="ops",
        )

        diff_blocks = parse_diff_output(raw_diff)
        assert len(diff_blocks) >= 1, "Should produce at least 1 diff block"

        updated_ops = apply_diff(ops_doc, diff_blocks, brain="ops")

        # Ops doc should have changed
        assert updated_ops != ops_doc, "Ops doc should be modified by ops diff"

        # Pitch doc must be completely unchanged
        assert pitch_doc == get_sample_living_document(), (
            "Pitch document must be completely unchanged after ops diff operation"
        )

    def test_claims_tagged_with_correct_brain(self):
        """Claims stored via store_confirmed_claims carry the correct brain tag."""
        from services.ingestion import extract_claims, store_confirmed_claims

        # Extract pitch claims
        pitch_extraction = extract_claims(
            transcript="We decided to target UK nuclear plants with £50K annual SaaS.",
            participants="Alex",
            topic_hint="pricing strategy",
            prompt_name="extraction",
        )
        pitch_claims = pitch_extraction["claims"]
        assert len(pitch_claims) >= 1, "Should extract at least 1 pitch claim"

        # Extract ops claims
        ops_extraction = extract_claims(
            transcript="Met Sarah Chen from EDF Energy. She wants a demo next week.",
            participants="Alex",
            topic_hint="contact from conference",
            prompt_name="ops_extraction",
        )
        ops_claims = ops_extraction["claims"]
        assert len(ops_claims) >= 1, "Should extract at least 1 ops claim"

        # Mark all claims as confirmed
        for c in pitch_claims:
            c["confirmed"] = True
        for c in ops_claims:
            c["confirmed"] = True

        # Mock MongoDB and store claims with respective brains
        with patch("services.mongo_client.insert_claim", return_value="mock_claim_id") as mock_insert:
            pitch_ids = store_confirmed_claims(
                claims=pitch_claims,
                session_id="pitch-session-001",
                brain="pitch",
            )
            ops_ids = store_confirmed_claims(
                claims=ops_claims,
                session_id="ops-session-001",
                brain="ops",
            )

        assert len(pitch_ids) >= 1, "Should store at least 1 pitch claim"
        assert len(ops_ids) >= 1, "Should store at least 1 ops claim"

        # Verify each call passed the correct brain kwarg
        calls = mock_insert.call_args_list
        pitch_call_count = sum(
            1 for call in calls if call.kwargs.get("brain") == "pitch"
        )
        ops_call_count = sum(
            1 for call in calls if call.kwargs.get("brain") == "ops"
        )

        assert pitch_call_count == len(pitch_claims), (
            f"Expected {len(pitch_claims)} pitch-tagged insert_claim calls, got {pitch_call_count}"
        )
        assert ops_call_count == len(ops_claims), (
            f"Expected {len(ops_claims)} ops-tagged insert_claim calls, got {ops_call_count}"
        )


# ===========================================================================
# 12. TestDirectCorrectionBrainRouting (3 tests)
# ===========================================================================

class TestDirectCorrectionBrainRouting:
    """Verify direct corrections route correctly per brain."""

    def test_pitch_correction_triggers_consistency(self):
        """Pitch brain: consistency check fires and returns pass1 results."""
        from services.consistency import run_consistency_check
        from tests.conftest import get_sample_living_document

        correction_claims = [
            {
                "claim_text": "We changed pricing to £75K per facility, replacing the previous £50K figure.",
                "claim_type": "decision",
                "confidence": "definite",
                "who_said_it": "Alex",
                "topic_tags": ["pricing"],
                "confirmed": True,
            },
        ]

        # run_consistency_check reads the living doc internally — mock it
        with patch(
            "services.consistency.read_living_document",
            return_value=get_sample_living_document(),
        ):
            result = run_consistency_check(
                claims=correction_claims,
                session_type="Pitch review",
                brain="pitch",
            )

        # pass1 must be populated (not None) — proves the LLM was called
        assert result["pass1"] is not None, (
            f"Pitch correction should trigger Pass 1 consistency check. Got: {result}"
        )
        # pass1 should have the standard structure
        assert "total_found" in result["pass1"], (
            f"pass1 should contain total_found key. Got keys: {list(result['pass1'].keys())}"
        )

    def test_ops_update_document_works(self):
        """Ops brain: update_document goes through full diff-verify-apply cycle."""
        from services.document_updater import update_document
        from tests.conftest import get_sample_ops_document

        new_risk = (
            "New risk identified: key dependency on single cloud provider (AWS). "
            "If AWS has an outage in eu-west-2, our entire platform goes down. "
            "Should investigate multi-cloud failover strategy."
        )

        with patch("services.document_updater.read_living_document", return_value=get_sample_ops_document()), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"):

            result = update_document(
                new_info=new_risk,
                update_reason="New infrastructure risk from architecture review",
                brain="ops",
            )

        assert result["success"] is True, (
            f"Ops update_document should succeed. Got: {result}"
        )
        assert result["changes_applied"] > 0, (
            f"Ops update should apply at least 1 change. Got: {result}"
        )

    def test_decision_log_skipped_for_ops(self):
        """_add_decision and _add_dismissed are pitch-only — no-op for ops."""
        from services.document_updater import _add_decision, _add_dismissed
        from tests.conftest import get_sample_ops_document

        ops_doc = get_sample_ops_document()

        # _add_decision should return the ops doc unchanged
        result_decision = _add_decision(ops_doc, "### Decision entry\nWe decided X.", brain="ops")
        assert result_decision == ops_doc, (
            "_add_decision should return ops doc unchanged — Decision Log is pitch-only"
        )

        # _add_dismissed should return the ops doc unchanged
        result_dismissed = _add_dismissed(ops_doc, "- Dismissed entry: contradiction Y", brain="ops")
        assert result_dismissed == ops_doc, (
            "_add_dismissed should return ops doc unchanged — Dismissed Contradictions is pitch-only"
        )


# ===========================================================================
# 13. TestConsistencyBrainGuards (3 tests)
# ===========================================================================

class TestConsistencyBrainGuards:
    """Verify consistency engine brain-specific guards."""

    def test_audit_returns_early_for_ops(self):
        """run_audit(brain='ops') returns early-exit result without LLM calls."""
        from services.consistency import run_audit

        result = run_audit(brain="ops")

        assert result == {
            "discrepancies": [],
            "overall_assessment": "healthy",
            "summary_message": "Audit is only available for Pitch Brain.",
            "raw": "",
        }

    def test_consistency_check_reads_correct_brain_doc(self):
        """run_consistency_check passes brain='pitch' through to read_living_document."""
        from services.consistency import run_consistency_check
        from tests.conftest import get_sample_living_document

        claim = {
            "claim_text": "Our pricing is £50K per year for enterprise licenses.",
            "claim_type": "pricing",
            "confidence": "high",
            "confirmed": True,
        }

        with patch(
            "services.consistency.read_living_document",
            return_value=get_sample_living_document(),
        ) as mock_read:
            result = run_consistency_check([claim], brain="pitch")
            mock_read.assert_called_with(brain="pitch")

        # Should have produced some result (not the empty-claims early exit)
        assert result is not None
        assert "has_contradictions" in result

    def test_check_dismissed_handles_ops_doc_without_section(self):
        """Ops doc has no Dismissed Contradictions — all contradictions pass through."""
        from services.consistency import check_dismissed
        from tests.conftest import get_sample_ops_document

        ops_doc = get_sample_ops_document()
        contradictions = [
            {
                "id": "1",
                "new_claim": "Nuclear utilities prefer building compliance tools in-house",
                "existing_position": "Utilities prefer vendor-managed solutions",
                "severity": "High",
            },
            {
                "id": "2",
                "new_claim": "Sales cycles are only 2-3 months for nuclear enterprise",
                "existing_position": "Long sales cycles 6-12 months",
                "severity": "Critical",
            },
        ]

        filtered = check_dismissed(contradictions, ops_doc)

        assert len(filtered) == len(contradictions), (
            f"All contradictions should pass through ops doc (no Dismissed section), "
            f"but {len(contradictions) - len(filtered)} were filtered out"
        )
        assert filtered == contradictions


# ===========================================================================
# 14. TestFreshnessCheck (2 tests, slow)
# ===========================================================================

@pytest.mark.slow
class TestFreshnessCheck:
    """Verify DeferredWriter freshness check detects concurrent changes."""

    def test_freshness_check_detects_modified_document(self):
        """batch_commit detects hash mismatch and re-diffs against current doc."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_living_document
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )
        claims = extraction["claims"]
        assert len(claims) >= 1, "Need at least 1 claim for freshness test"

        writer = DeferredWriter()
        original_doc = get_sample_living_document()
        # Modified doc simulates a concurrent write during the pipeline
        modified_doc = original_doc + "\n- 2026-03-01: New concurrent change. Source: Another user\n"

        # Initialize with original doc
        with patch("services.document_updater.read_living_document", return_value=original_doc):
            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-02-01", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                brain="pitch",
            )

        # Apply deferred update (real LLM call) with original doc
        with patch("services.document_updater.read_living_document", return_value=original_doc), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True):

            new_info = " | ".join(c["claim_text"] for c in claims)
            writer.apply_document_update_deferred(
                new_info=new_info,
                update_reason="Session: initial strategy",
            )

        # batch_commit: read_living_document returns MODIFIED doc -> hash mismatch -> re-diff
        with patch("services.document_updater.read_living_document", return_value=modified_doc), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.insert_session", return_value="mock_session_id"), \
             patch("services.mongo_client.insert_claim", return_value="mock_claim_id"), \
             patch("services.mongo_client.find_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]), \
             patch("services.ingestion_lock.check_lock", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"), \
             patch("services.deferred_writer.save_checkpoint", return_value=True), \
             patch("services.deferred_writer.delete_checkpoint"):

            result = writer.batch_commit()

            assert result["success"] is True, (
                f"batch_commit should succeed after re-diff. Message: {result.get('message', '')}"
            )

    def test_freshness_check_unchanged_document_skips_rediff(self):
        """batch_commit with unchanged doc -> success without re-diff."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_living_document
        from tests.test_mockup_data import session_01_initial_strategy
        from services.ingestion import extract_claims

        data = session_01_initial_strategy()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
        )
        claims = extraction["claims"]
        assert len(claims) >= 1, "Need at least 1 claim for freshness test"

        writer = DeferredWriter()
        doc_content = get_sample_living_document()

        # Initialize and apply with same doc — then batch_commit also sees same doc
        with patch("services.document_updater.read_living_document", return_value=doc_content), \
             patch("services.document_updater.write_living_document"), \
             patch("services.document_updater._git_commit", return_value=True), \
             patch("services.mongo_client.upsert_living_document", return_value=True), \
             patch("services.mongo_client.insert_session", return_value="mock_session_id"), \
             patch("services.mongo_client.insert_claim", return_value="mock_claim_id"), \
             patch("services.mongo_client.find_one", return_value=None), \
             patch("services.mongo_client.find_many", return_value=[]), \
             patch("services.ingestion_lock.check_lock", return_value=True), \
             patch("services.ingestion_lock.acquire_doc_lock", return_value="mock_lock_id"), \
             patch("services.ingestion_lock.release_doc_lock"), \
             patch("services.deferred_writer.save_checkpoint", return_value=True), \
             patch("services.deferred_writer.delete_checkpoint"):

            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-02-01", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                brain="pitch",
            )

            new_info = " | ".join(c["claim_text"] for c in claims)
            writer.apply_document_update_deferred(
                new_info=new_info,
                update_reason="Session: initial strategy",
            )

            result = writer.batch_commit()

            assert result["success"] is True, (
                f"batch_commit should succeed with unchanged doc. Message: {result.get('message', '')}"
            )
            assert result["document_updated"] is True, (
                "Document should be updated when hash matches (no re-diff needed)"
            )


# ===========================================================================
# 15. TestOpsCheckpointRoundTrip (1 test)
# ===========================================================================

class TestOpsCheckpointRoundTrip:
    """Verify ops brain checkpoint serialization."""

    def test_ops_checkpoint_preserves_brain(self):
        """to_checkpoint -> from_checkpoint preserves ops brain and all fields."""
        from services.deferred_writer import DeferredWriter
        from tests.conftest import get_sample_ops_document
        from tests.test_mockup_data import ops_session_01_contacts_and_risks
        from services.ingestion import extract_claims

        data = ops_session_01_contacts_and_risks()
        extraction = extract_claims(
            transcript=data["transcript"],
            participants=data["participants"],
            topic_hint=data["topic_hint"],
            prompt_name="ops_extraction",
        )
        claims = extraction["claims"]
        assert len(claims) >= 1, "Need at least 1 ops claim for checkpoint test"

        writer = DeferredWriter()
        with patch("services.document_updater.read_living_document", return_value=get_sample_ops_document()):
            writer.initialize(
                transcript=data["transcript"],
                confirmed_claims=claims,
                metadata={"session_date": "2026-03-01", "participants": data["participants"]},
                session_summary=extraction["session_summary"],
                topic_tags=extraction.get("topic_tags", []),
                brain="ops",
            )

        checkpoint = writer.to_checkpoint()
        restored = DeferredWriter.from_checkpoint(checkpoint)

        assert restored.brain == "ops", (
            f"Restored brain should be 'ops', got '{restored.brain}'"
        )
        assert restored.transcript == writer.transcript, (
            "Restored transcript should match original"
        )
        assert len(restored.confirmed_claims) == len(writer.confirmed_claims), (
            f"Restored claims count ({len(restored.confirmed_claims)}) should match original ({len(writer.confirmed_claims)})"
        )
        assert restored.original_doc == writer.original_doc, (
            "Restored original_doc should match"
        )
        assert restored.original_doc_hash == writer.original_doc_hash, (
            "Restored original_doc_hash should match"
        )


# ===========================================================================
# 16. TestOpsStructuralDiff (4 tests)
# ===========================================================================

class TestOpsStructuralDiff:
    """Verify ops brain diff application uses correct document structure."""

    def test_ops_add_changelog_uses_top_level_headers(self):
        """Ops diff should place new info under ## top-level headers, not ### with **Changelog:**."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "Key risk update: NRC has announced a new AI oversight framework "
            "for nuclear facilities, expected to take effect in Q4 2026. "
            "This changes our regulatory timeline assumptions significantly."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="Regulatory risk update",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        if not blocks:
            pytest.skip("Diff generation produced no blocks")

        updated_doc = apply_diff(current_doc, blocks, brain="ops")

        # The new info should appear under a ## top-level section (e.g. Key Risks)
        assert "AI oversight" in updated_doc or "NRC" in updated_doc.lower() or "regulatory" in updated_doc.lower(), (
            f"Updated doc should contain the new risk info. Doc tail: {updated_doc[-500:]}"
        )
        # Ops brain should NOT use the pitch pattern of ### subsection + **Changelog:**
        # Check that no **Changelog:** label was introduced
        changelog_count_before = current_doc.count("**Changelog:**")
        changelog_count_after = updated_doc.count("**Changelog:**")
        assert changelog_count_after == changelog_count_before, (
            f"Ops doc should not gain **Changelog:** entries (pitch pattern). "
            f"Before: {changelog_count_before}, After: {changelog_count_after}"
        )

    def test_ops_feedback_inserts_under_individual_feedback(self):
        """Feedback in ops brain should appear under ### Individual Feedback, not at ## level."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "Feedback from Dave Morrison at GridPoint Energy: "
            "They want a read-only compliance dashboard before committing to full automation. "
            "Concerned about giving AI write access to safety-critical documents."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="Customer feedback from GridPoint Energy",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        if not blocks:
            pytest.skip("Diff generation produced no blocks")

        updated_doc = apply_diff(current_doc, blocks, brain="ops")

        # Find the Individual Feedback section and verify new feedback is there
        individual_idx = updated_doc.find("### Individual Feedback")
        assert individual_idx != -1, "### Individual Feedback section should still exist"

        # Find the next ## section after Individual Feedback
        next_section_idx = updated_doc.find("\n## ", individual_idx)
        if next_section_idx == -1:
            next_section_idx = len(updated_doc)

        individual_section = updated_doc[individual_idx:next_section_idx]

        # The feedback should be within the Individual Feedback subsection
        has_feedback = (
            "morrison" in individual_section.lower()
            or "gridpoint" in individual_section.lower()
            or "dashboard" in individual_section.lower()
            or "read-only" in individual_section.lower()
        )
        assert has_feedback, (
            f"Feedback should appear under ### Individual Feedback. "
            f"Section content: {individual_section[:500]}"
        )

    def test_ops_hypothesis_addition(self):
        """New hypothesis info should appear under ## Active Hypotheses in ops brain."""
        from services.document_updater import generate_diff, parse_diff_output, apply_diff
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_info = (
            "New hypothesis: Small modular reactor (SMR) operators will adopt "
            "compliance tooling faster than traditional large plant operators because "
            "they have smaller teams and less institutional inertia. "
            "Test: Interview 3 SMR operators by end of Q2."
        )

        raw_diff = generate_diff(
            current_doc, new_info,
            update_reason="New hypothesis from market research",
            brain="ops",
        )
        blocks = parse_diff_output(raw_diff)
        if not blocks:
            pytest.skip("Diff generation produced no blocks")

        updated_doc = apply_diff(current_doc, blocks, brain="ops")

        # Find the Active Hypotheses section
        hyp_idx = updated_doc.find("## Active Hypotheses")
        assert hyp_idx != -1, "## Active Hypotheses section should still exist"

        # Find the next ## section after Active Hypotheses
        next_section_idx = updated_doc.find("\n## ", hyp_idx + 1)
        if next_section_idx == -1:
            next_section_idx = len(updated_doc)

        hyp_section = updated_doc[hyp_idx:next_section_idx]

        has_hypothesis = (
            "smr" in hyp_section.lower()
            or "small modular" in hyp_section.lower()
            or "modular reactor" in hyp_section.lower()
        )
        assert has_hypothesis, (
            f"New hypothesis should appear under ## Active Hypotheses. "
            f"Section content: {hyp_section[:500]}"
        )

    def test_ops_add_section_inserts_before_scratchpad(self):
        """_add_section with brain='ops' should insert new section before ## Scratchpad Notes."""
        from services.document_updater import _add_section
        from tests.conftest import get_sample_ops_document

        current_doc = get_sample_ops_document()
        new_section_content = "## Partnerships\n\n- Exploring partnership with NRC-certified auditors\n"

        updated_doc = _add_section(
            current_doc,
            section="Partnerships",
            section_content=new_section_content,
            brain="ops",
        )

        # New section should exist in the document
        assert "## Partnerships" in updated_doc, "New section should be added"

        # It should appear BEFORE ## Scratchpad Notes
        partnerships_idx = updated_doc.find("## Partnerships")
        scratchpad_idx = updated_doc.find("## Scratchpad Notes")
        assert scratchpad_idx != -1, "## Scratchpad Notes should still exist"
        assert partnerships_idx < scratchpad_idx, (
            f"New section should be inserted before Scratchpad Notes. "
            f"Partnerships at {partnerships_idx}, Scratchpad at {scratchpad_idx}"
        )

        # Verify existing content is preserved
        assert "## Active Hypotheses" in updated_doc
        assert "## Key Risks" in updated_doc
        assert "Sarah Chen" in updated_doc
