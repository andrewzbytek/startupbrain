"""Tests for Key Contacts / Prospects CRM feature."""
import pytest
from services.document_updater import _add_contact, _update_contact, apply_diff
from app.components.sidebar import _parse_contacts
from app.components.chat import _is_contact, _strip_contact_prefix


# ---------------------------------------------------------------------------
# Minimal document snippets for unit tests
# ---------------------------------------------------------------------------

_DOC_WITH_PLACEHOLDER = """\
## Current State

### Key Contacts / Prospects
[No contacts tracked yet]

### Fundraising Status / Strategy
**Current position:** Pre-seed.
"""

_DOC_WITH_ONE_CONTACT = """\
## Current State

### Key Contacts / Prospects
- [2026-02-10] **Sarah Chen** (Beacon Capital)
  Role: Partner | Type: investor | Status: in-conversation
  Context: Met at nuclear energy conference. Interested in compliance tech.
  Last interaction: 2026-02-10 — Positive on technical approach, wants first customer before investing
  Next step: Send demo after first customer signed

### Fundraising Status / Strategy
**Current position:** Pre-seed.
"""

_DOC_WITHOUT_CONTACTS_SECTION = """\
## Current State

### Target Market / Initial Customer
**Current position:** Small UK nuclear plants.
**Changelog:**
- 2026-02-01: Initial. Source: Session 1

## Decision Log

### 2026-02-05 — Per-Facility Licensing
**Decision:** Annual per-facility SaaS licence.
**Status:** Active
"""

_NEW_CONTACT_ENTRY = """\
- [2026-03-01] **Natalie Park** (BCDC Energy)
  Role: CTO | Type: prospect | Status: identified
  Context: Introduced via LinkedIn. Runs compliance at BCDC.
  Last interaction: 2026-03-01 — Intro call scheduled
  Next step: Send product overview deck"""


# ===========================================================================
# TestAddContact
# ===========================================================================

class TestAddContact:

    def test_add_contact_replaces_placeholder(self):
        result = _add_contact(_DOC_WITH_PLACEHOLDER, _NEW_CONTACT_ENTRY)
        assert "[No contacts tracked yet]" not in result
        assert "**Natalie Park**" in result
        assert "BCDC Energy" in result

    def test_add_contact_appends_to_existing(self):
        result = _add_contact(_DOC_WITH_ONE_CONTACT, _NEW_CONTACT_ENTRY)
        assert "**Sarah Chen**" in result
        assert "**Natalie Park**" in result
        # Sarah should appear before Natalie
        assert result.index("Sarah Chen") < result.index("Natalie Park")

    def test_add_contact_creates_section_if_missing(self):
        result = _add_contact(_DOC_WITHOUT_CONTACTS_SECTION, _NEW_CONTACT_ENTRY)
        assert "### Key Contacts / Prospects" in result
        assert "**Natalie Park**" in result


# ===========================================================================
# TestUpdateContact
# ===========================================================================

class TestUpdateContact:

    def test_update_contact_by_name(self):
        updated_entry = (
            "- [2026-03-01] **Sarah Chen** (Beacon Capital)\n"
            "  Role: Partner | Type: investor | Status: engaged\n"
            "  Context: Met at nuclear energy conference. Interested in compliance tech.\n"
            "  Last interaction: 2026-03-01 — Signed LOI for pilot\n"
            "  Next step: Schedule onboarding call"
        )
        result = _update_contact(_DOC_WITH_ONE_CONTACT, "Sarah Chen", updated_entry)
        assert "Status: engaged" in result
        assert "Signed LOI for pilot" in result
        # Old content should be replaced
        assert "wants first customer before investing" not in result

    def test_update_contact_not_found(self):
        updated_entry = (
            "- [2026-03-01] **Unknown Person** (Nowhere)\n"
            "  Role: Nobody | Type: investor | Status: identified\n"
            "  Context: Does not exist.\n"
            "  Last interaction: 2026-03-01 — N/A\n"
            "  Next step: N/A"
        )
        result = _update_contact(_DOC_WITH_ONE_CONTACT, "Unknown Person", updated_entry)
        # Document should remain unchanged
        assert result == _DOC_WITH_ONE_CONTACT


# ===========================================================================
# TestParseContacts
# ===========================================================================

_DOC_WITH_TWO_CONTACTS = """\
## Current State

### Key Contacts / Prospects
- [2026-02-10] **Sarah Chen** (Beacon Capital)
  Role: Partner | Type: investor | Status: in-conversation
  Context: Met at nuclear energy conference. Interested in compliance tech.
  Last interaction: 2026-02-10 — Positive on technical approach, wants first customer before investing
  Next step: Send demo after first customer signed

- [2026-02-14] **Marcus Webb** (Frontier Ventures)
  Role: Managing Director | Type: investor | Status: identified
  Context: Warm intro from advisor network. Interested in nuclear tech startups.
  Last interaction: 2026-02-14 — Brief intro call, asked for pitch deck
  Next step: Send pitch deck and one-pager

### Fundraising Status / Strategy
**Current position:** Pre-seed.
"""


class TestParseContacts:

    def test_parse_contacts_populated(self):
        contacts = _parse_contacts(_DOC_WITH_TWO_CONTACTS)
        assert len(contacts) == 2

    def test_parse_contacts_empty(self):
        contacts = _parse_contacts(_DOC_WITH_PLACEHOLDER)
        assert contacts == []

    def test_parse_contacts_missing_section(self):
        contacts = _parse_contacts(_DOC_WITHOUT_CONTACTS_SECTION)
        assert contacts == []

    def test_parse_contacts_field_extraction(self):
        contacts = _parse_contacts(_DOC_WITH_TWO_CONTACTS)
        sarah = next(c for c in contacts if c["name"] == "Sarah Chen")
        assert sarah["date"] == "2026-02-10"
        assert sarah["org"] == "Beacon Capital"
        assert sarah["role"] == "Partner"
        assert sarah["type"] == "investor"
        assert sarah["status"] == "in-conversation"
        assert "nuclear energy conference" in sarah["context"]
        assert "2026-02-10" in sarah["last_interaction"]
        assert "first customer" in sarah["next_step"]

        marcus = next(c for c in contacts if c["name"] == "Marcus Webb")
        assert marcus["date"] == "2026-02-14"
        assert marcus["org"] == "Frontier Ventures"
        assert marcus["role"] == "Managing Director"
        assert marcus["type"] == "investor"
        assert marcus["status"] == "identified"


# ===========================================================================
# TestApplyDiffContacts
# ===========================================================================

class TestApplyDiffContacts:

    def test_apply_diff_add_contact(self):
        diff_blocks = [{
            "section": "Current State → Key Contacts / Prospects",
            "action": "ADD_CONTACT",
            "content": _NEW_CONTACT_ENTRY,
        }]
        result = apply_diff(_DOC_WITH_PLACEHOLDER, diff_blocks)
        assert "[No contacts tracked yet]" not in result
        assert "**Natalie Park**" in result

    def test_apply_diff_update_contact(self):
        updated_entry = (
            "- [2026-03-01] **Sarah Chen** (Beacon Capital)\n"
            "  Role: Partner | Type: investor | Status: engaged\n"
            "  Context: Met at nuclear energy conference. Interested in compliance tech.\n"
            "  Last interaction: 2026-03-01 — Signed LOI for pilot\n"
            "  Next step: Schedule onboarding call"
        )
        diff_blocks = [{
            "section": "Current State → Key Contacts / Prospects",
            "action": "UPDATE_CONTACT",
            "content": updated_entry,
        }]
        result = apply_diff(_DOC_WITH_ONE_CONTACT, diff_blocks)
        assert "Status: engaged" in result
        assert "Signed LOI for pilot" in result


# ===========================================================================
# TestContactChatPrefix
# ===========================================================================

class TestContactChatPrefix:

    def test_is_contact_true(self):
        assert _is_contact("contact: Natalie from BCDC") is True

    def test_is_contact_prospect(self):
        assert _is_contact("prospect: Natalie") is True

    def test_is_contact_lead(self):
        assert _is_contact("lead: Natalie") is True

    def test_is_contact_false(self):
        assert _is_contact("hello") is False

    def test_is_contact_case_insensitive(self):
        assert _is_contact("Contact: Someone") is True
        assert _is_contact("PROSPECT: Someone") is True

    def test_strip_contact_prefix(self):
        assert _strip_contact_prefix("contact: Natalie from BCDC") == "Natalie from BCDC"

    def test_strip_prospect_prefix(self):
        assert _strip_contact_prefix("prospect: Natalie") == "Natalie"

    def test_strip_lead_prefix(self):
        assert _strip_contact_prefix("lead: Natalie") == "Natalie"

    def test_strip_no_prefix(self):
        assert _strip_contact_prefix("hello world") == "hello world"
