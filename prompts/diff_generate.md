# Diff Generation Prompt (Claude Sonnet)

**THIS IS THE MOST IMPORTANT PROMPT IN THE SYSTEM.**

You are updating the startup's living document (`startup_brain.md`) with new information. Your job is to output ONLY the specific changes needed — nothing else. Do NOT rewrite unchanged sections. Do NOT rephrase existing content. Do NOT summarize existing changelogs. Do NOT move content around.

## The Core Rule

If a section does not need to change, do not mention it. Your output is a diff, not a document.

## Input Format

<diff_input>
  <current_document>{{full_startup_brain_md}}</current_document>
  <new_information>{{what_needs_to_be_incorporated}}</new_information>
  <update_reason>{{session_date_and_context}}</update_reason>
</diff_input>

## Allowed Actions

- `UPDATE_POSITION` — Replace the Current Position text in a section (use when the fundamental position has changed)
- `ADD_CHANGELOG` — Add a changelog entry to a section (use when the position changed and needs history)
- `ADD_DECISION` — Add a new entry to the Decision Log section
- `ADD_FEEDBACK` — Add a new entry to the Feedback Tracker section
- `ADD_DISMISSED` — Add a new entry to the Dismissed Contradictions section
- `ADD_HYPOTHESIS` — Add a new entry to the Active Hypotheses section
- `ADD_SECTION` — Add an entirely new section to Current State (only when genuinely new topic)

## Output Format

Output ONLY structured change blocks. Each block must have exactly this format:

```
SECTION: [exact section header from the document, e.g., "Current State → Pricing"]
ACTION: [one of the allowed actions above]
CONTENT:
[exact markdown content to insert or replace — preserve all markdown formatting]
```

Separate multiple change blocks with a blank line. Output nothing else — no preamble, no explanation, no summary.

---

## Examples

### CORRECT: Minimal diff — updating one section

Input scenario: New session confirms pricing changed from £50K to £75K per facility per year, with reasoning.

```
SECTION: Current State → Pricing
ACTION: UPDATE_POSITION
CONTENT:
**Current position:** £75K per facility per year. Raised from £50K after validating willingness-to-pay with two prospects.

SECTION: Current State → Pricing
ACTION: ADD_CHANGELOG
CONTENT:
- 2026-02-28: Raised from £50K to £75K/facility/year after two prospect conversations confirmed higher willingness-to-pay. Source: Session 2026-02-28

SECTION: Decision Log
ACTION: ADD_DECISION
CONTENT:
### 2026-02-28 — Raised Initial Pricing to £75K/Facility/Year
**Decision:** Increase initial price anchor from £50K to £75K per facility per year.
**Alternatives considered:** Keep at £50K, go freemium for first customer
**Why alternatives were rejected:** Two early prospect conversations showed no price sensitivity at £50K; £75K was accepted without pushback in both cases. Freemium rejected as it undermines SaaS framing.
**Context:** Following two informal prospect conversations at nuclear industry event.
**Participants:** Alex, Jordan
```

---

### WRONG: Rewriting existing content — DO NOT DO THIS

```
SECTION: Current State → Pricing
ACTION: UPDATE_POSITION
CONTENT:
**Current position:** £75K per facility per year.
**Changelog:**
- 2026-02-28: Raised from £50K to £75K/facility/year. Source: Session 2026-02-28
- 2026-02-14: Initial pricing set at £50K/facility/year. Source: Session 1
```

**Why this is wrong:** It rewrites the entire section including pre-existing changelog entries. This introduces drift — the existing entries may have been rephrased or details subtly changed. The ADD_CHANGELOG action exists specifically to avoid this.

---

### CORRECT: Adding a new section

Input scenario: New session introduces a topic (competitive landscape) that doesn't exist yet in the document.

```
SECTION: Current State → Competitive Landscape
ACTION: ADD_SECTION
CONTENT:
### Competitive Landscape
**Current position:** No direct software competitors identified in UK nuclear compliance space. Primary alternative is manual processes and spreadsheets. One US player (name TBC) operates in nuclear quality management but not document compliance.
**Changelog:**
- 2026-02-28: Initial competitive assessment. Source: Session 2026-02-28
```

---

### CORRECT: Dismissing a contradiction

Input scenario: System flagged a contradiction but founders chose to dismiss it.

```
SECTION: Dismissed Contradictions
ACTION: ADD_DISMISSED
CONTENT:
- 2026-02-28: Claim that enterprise targets (BP-scale) would convert faster — Dismissed because: current evidence from procurement research shows small plants still have faster cycles. Will revisit if evidence changes.
```

---

### CORRECT: Adding a hypothesis

Input scenario: Founder tracks a testable assumption about their market.

```
SECTION: Active Hypotheses
ACTION: ADD_HYPOTHESIS
CONTENT:
- [2026-03-01] **Small nuclear plants have procurement cycles under 12 months**
  Status: unvalidated | Test: Ask 3 plant operators directly
  Evidence: ---
```
