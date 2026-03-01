"""
Shared pytest fixtures for Startup Brain test suite.
All external dependencies (MongoDB, Claude API) are mocked.
Tests must run without API keys.
"""

from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_living_document():
    """Return a populated startup_brain.md string with real nuclear compliance content."""
    return """# Startup Brain — NuclearCompliance.ai
Last updated: 2026-02-15

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK, specifically operators running fewer than 3 reactors (e.g., Heysham, Hartlepool). Chosen because procurement cycles are 6-12 months vs. 18-24 months for large operators. UK-only for first 12 months.
**Changelog:**
- 2026-02-01: Initial position set. Small UK nuclear plants as beachhead. Source: Session 1
- 2026-02-05: Confirmed. No change. Source: Session 2

### Value Proposition
**Current position:** AI-powered compliance document management for nuclear operators. Automatically extracts structured metadata from PDFs (Safety Cases, Periodic Safety Reviews, Operating Rules, Maintenance Procedures) and builds a searchable compliance index. Replaces manual spreadsheet tracking.
**Changelog:**
- 2026-02-01: Initial position. Source: Session 1
- 2026-02-08: MVP scoped to PDF compliance document management. Technical drawings post-MVP. Source: Session 3

### Business Model / Revenue Model
**Current position:** Per-facility annual SaaS licence. Each nuclear site is one contract. Billing is annual in advance.
**Changelog:**
- 2026-02-05: Per-facility model confirmed. Not per-user, not usage-based. Source: Session 2

### Pricing
**Current position:** £50,000 per facility per year for initial customers. One-time implementation fee of £10,000-£15,000. Plan to raise to £75K after first 3 customers.
**Changelog:**
- 2026-02-05: Pricing anchor set at £50K/facility/year. Implementation fee £10K-£15K. Source: Session 2

### Go-to-Market Strategy
**Current position:** Direct sales to small UK nuclear operators. Target 10 paying facilities in year one = £500K ARR. First customer within 6 months of launch.
**Changelog:**
- 2026-02-05: Direct sales model confirmed. Target 10 facilities year one. Source: Session 2

### Technical Approach
**Current position:** LLM-based extraction (Claude) from PDFs using PyMuPDF for text + vision for poor OCR. MongoDB for storage. MVP is PDF compliance document management only. Azure Blob for file storage (leaning toward Azure given nuclear operator Microsoft infrastructure).
**Changelog:**
- 2026-02-08: MVP technical approach finalised. PDF-only for MVP. Source: Session 3

### Competitive Landscape
**Current position:** Competitors are rule-based OCR systems and manual spreadsheet tracking. No known direct competitor using LLM extraction for nuclear compliance specifically.
**Changelog:**
- 2026-02-08: Competitive landscape assessed. Source: Session 3

### Key Assumptions
- Nuclear operators currently use manual spreadsheets for compliance tracking
- LLM extraction accuracy is sufficient with human confirmation step
- Small operators have 6-12 month procurement cycles
- Azure infrastructure preference eases IT approval at target customers

### Open Questions
- Direct vs. channel sales (unresolved)
- How to handle multi-site licences for operators with 2-3 facilities
- Data security and data residency requirements for nuclear documents

### Key Risks
**Current position:** (1) LLM accuracy for highly technical documents. (2) Regulatory approval risk — ONR may require certification we have not scoped. (3) Procurement cycle longer than expected.
**Changelog:**
- 2026-02-08: Initial risks identified. Source: Session 3

### Team / Hiring Plans
**Current position:** First hire must be a nuclear domain expert, not a developer. Domain access is the scarcer resource. Commercial hire (sales) needed before Series A.
**Changelog:**
- 2026-02-05: First hire decision: nuclear domain expert. Source: Session 2

### Fundraising Status / Strategy
**Current position:** Pre-seed, self-funded. Targeting seed round after first paying customer. Need warm intros to nuclear-focused investors.
**Changelog:**
- 2026-02-10: Started investor outreach. No term sheets yet. Source: Investor meetings

## Decision Log

### 2026-02-05 — Per-Facility Annual Licensing Model
**Decision:** Annual per-facility SaaS licence at £50K/year. Not usage-based, not per-user.
**Why:** Nuclear budgets allocated per facility. Annual contracts give predictable revenue. VCs dislike variable MRR.
**Status:** Active

### 2026-02-05 — Rejected Usage-Based Pricing
**Decision:** Rejected usage-based pricing in favour of annual per-facility licence.
**Why rejected:** VCs dislike variable MRR. Harder to forecast. Annual contracts give predictable revenue.
**Status:** Rejected

### 2026-02-08 — MVP Scope: PDF-Only
**Decision:** MVP is limited to PDF compliance document management. Technical drawings, AI querying, and automated audit trails are post-MVP.
**Why:** Shippable in 3 months. Clear, testable value proposition.
**Status:** Active

### 2026-02-01 — Target Market: Small UK Nuclear
**Decision:** Beachhead market is small UK nuclear plants (<3 reactors). Not oil & gas, not large operators.
**Why:** Shorter procurement cycles (6-12 months). Concentrated market (reachable through direct outreach). Clear regulatory pain point (ONR compliance).
**Status:** Active

## Feedback Tracker

### Recurring Themes
- Branding/logo concerns: 2 sources (Sarah Chen - Beacon Capital 2026-02-10, Marcus Webb - Frontier Ventures 2026-02-14)

### Individual Feedback
- 2026-02-10 | Sarah Chen (Beacon Capital, investor): Positive on technical approach. Concerned about branding — name and logo feel like government contractor. Wants to see first customer before investing.
- 2026-02-14 | Marcus Webb (Frontier Ventures, investor): Questioned unit economics and onboarding costs. Same branding concern as Sarah Chen (independently raised). Wants live demo.

## Dismissed Contradictions
- 2026-02-12: Claim that BP/Shell enterprise accounts would close faster — Dismissed because: small nuclear operators have shorter procurement cycles and we can reach the whole market directly. Large enterprise sales cycles would be 18+ months.
"""


@pytest.fixture
def sample_claims():
    """Return a list of claim dicts matching the schema from SPEC Section 15.2."""
    return [
        {
            "claim_text": "We will use per-facility annual licensing at £50,000 per year.",
            "claim_type": "decision",
            "confidence": "definite",
            "who_said_it": "Alex",
            "topic_tags": ["pricing", "business-model"],
            "confirmed": True,
        },
        {
            "claim_text": "Target market is small UK nuclear plants with fewer than 3 reactors.",
            "claim_type": "decision",
            "confidence": "definite",
            "who_said_it": "",
            "topic_tags": ["target-market"],
            "confirmed": True,
        },
        {
            "claim_text": "MVP will focus exclusively on PDF compliance document management.",
            "claim_type": "decision",
            "confidence": "definite",
            "who_said_it": "Jordan",
            "topic_tags": ["technical", "mvp"],
            "confirmed": True,
        },
        {
            "claim_text": "First hire must be a nuclear domain expert, not a developer.",
            "claim_type": "decision",
            "confidence": "definite",
            "who_said_it": "",
            "topic_tags": ["hiring"],
            "confirmed": True,
        },
        {
            "claim_text": "Direct vs. channel sales model is still unresolved.",
            "claim_type": "question",
            "confidence": "speculative",
            "who_said_it": "",
            "topic_tags": ["go-to-market"],
            "confirmed": True,
        },
    ]


@pytest.fixture
def sample_session():
    """Return a sample session dict."""
    return {
        "transcript": "We decided to focus on small UK nuclear plants as our initial target market. "
                      "Pricing will be £50K per facility per year.",
        "summary": "Confirmed target market (small UK nuclear) and pricing (£50K/facility/year).",
        "topic_tags": ["target-market", "pricing"],
        "metadata": {
            "session_date": "2026-02-05",
            "participants": "Alex, Jordan",
        },
        "session_date": "2026-02-05",
    }


@pytest.fixture
def sample_contradictions():
    """Return structured contradiction results from a Pass 1 consistency check."""
    return [
        {
            "id": "1",
            "new_claim": "We should target BP and Shell as our first customers because they have larger budgets.",
            "existing_position": "Small nuclear power plants in the UK, specifically operators running fewer than 3 reactors.",
            "existing_section": "Current State → Target Market / Initial Customer",
            "tension_description": "New claim proposes large oil & gas enterprises as initial targets, "
                                   "directly contradicting the documented decision to focus on small nuclear plants.",
            "is_revisited_rejection": False,
        },
        {
            "id": "2",
            "new_claim": "We are considering usage-based pricing at £0.05 per document processed.",
            "existing_position": "Rejected usage-based pricing in favour of annual per-facility licence. VCs dislike variable MRR.",
            "existing_section": "Decision Log → 2026-02-05 — Rejected Usage-Based Pricing",
            "tension_description": "New claim revisits usage-based pricing, which was explicitly rejected in the Decision Log.",
            "is_revisited_rejection": True,
        },
    ]


@pytest.fixture
def sample_diff_output():
    """Return a valid diff in the structured SECTION/ACTION/CONTENT format."""
    return """SECTION: Current State → Pricing
ACTION: UPDATE_POSITION
CONTENT:
**Current position:** Hybrid model under consideration: £15,000-£20,000 base subscription per facility per year, plus £0.10 per document processed. Still evaluating — current position remains £50K/facility/year until decision confirmed.

SECTION: Current State → Pricing
ACTION: ADD_CHANGELOG
CONTENT:
- 2026-02-15: Hybrid pricing model (base + usage) under active evaluation based on customer feedback. Decision pending. Source: Session 5

SECTION: Decision Log
ACTION: ADD_DECISION
CONTENT:
### 2026-02-15 — Hybrid Pricing Model Under Evaluation
**Decision:** Evaluating hybrid pricing (£15K-£20K base + £0.10/document) based on customer feedback about OpEx approval processes.
**Why:** Three customers independently noted that annual subscription OpEx approval takes longer than variable cost billing.
**Status:** Under evaluation — not yet adopted
"""


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_claude_response():
    """Return a mock Claude API response dict."""
    def _make_response(text):
        return {
            "text": text,
            "tokens_in": 1000,
            "tokens_out": 500,
            "model": "claude-sonnet-4-20250514",
        }
    return _make_response


@pytest.fixture
def mock_claude_client(mock_claude_response):
    """
    Fixture that patches services.claude_client.call_sonnet and call_opus
    with configurable mock responses.
    """
    with patch("services.claude_client.call_sonnet") as mock_sonnet, \
         patch("services.claude_client.call_opus") as mock_opus:
        # Default: return empty-ish valid XML
        mock_sonnet.return_value = mock_claude_response("<extraction_output><session_summary>Mock</session_summary><topic_tags></topic_tags><claims></claims></extraction_output>")
        mock_opus.return_value = mock_claude_response("<analysis></analysis>")
        yield {"sonnet": mock_sonnet, "opus": mock_opus}


@pytest.fixture
def living_doc_path():
    """Return the path to the real living document (documents/startup_brain.md)."""
    return Path(__file__).parent.parent / "documents" / "startup_brain.md"


@pytest.fixture
def mock_mongo_client():
    """
    Fixture that patches services.mongo_client with in-memory storage.
    """
    storage = {
        "sessions": [],
        "claims": [],
        "feedback": [],
        "book_frameworks": [],
        "whiteboard_extractions": [],
        "living_document": [],
        "cost_log": [],
    }

    def _insert_one(collection, doc):
        from datetime import datetime, timezone
        doc = {**doc, "created_at": datetime.now(timezone.utc)}
        storage[collection].append(doc)
        return f"mock_id_{len(storage[collection])}"

    def _find_many(collection, query=None, sort_by="created_at", sort_order=-1, limit=100):
        return storage.get(collection, [])[:limit]

    def _find_one(collection, query):
        items = storage.get(collection, [])
        return items[0] if items else None

    def _update_one(collection, query, update, upsert=False):
        return True

    mock = MagicMock()
    mock.insert_one.side_effect = _insert_one
    mock.find_many.side_effect = _find_many
    mock.find_one.side_effect = _find_one
    mock.update_one.side_effect = _update_one
    mock._storage = storage

    with patch("services.mongo_client.insert_one", side_effect=_insert_one), \
         patch("services.mongo_client.find_many", side_effect=_find_many), \
         patch("services.mongo_client.find_one", side_effect=_find_one), \
         patch("services.mongo_client.update_one", side_effect=_update_one), \
         patch("services.mongo_client.get_db", return_value=MagicMock()), \
         patch("services.mongo_client.get_mongo_client", return_value=MagicMock()):
        yield mock, storage
