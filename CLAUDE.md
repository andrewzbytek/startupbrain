# Startup Brain

## What This Is
AI-powered knowledge management for a 2-person startup. See `docs/SPEC.md` for full specification.

## Tech Stack
- Python 3.12+, Streamlit, MongoDB Atlas (pymongo), Anthropic API (anthropic SDK)
- NO LangChain, NO LlamaIndex, NO heavy frameworks. Direct API calls only.
- Minimal dependencies. Check requirements.txt before adding anything.

## Architecture
- Streamlit app at `app/main.py` (entry point for Streamlit Community Cloud)
- Services in `services/` — each service is a single-purpose module
- LLM prompts in `prompts/` as markdown files — loaded at runtime, never hardcoded
- Living document at `documents/startup_brain.md` — git-tracked, mirrored to MongoDB
- All state management via `st.session_state` — Streamlit re-runs on every interaction
- State machine: `chat → ingesting → confirming_claims → checking_consistency → resolving_contradiction → done`

## Key Conventions
- Use `@st.cache_resource` for MongoDB connections
- Every Claude API call goes through `services/claude_client.py` which handles cost tracking and Sonnet/Opus routing
- Prompts are markdown files in `/prompts` — read them with open(), never inline them
- Use XML tags for structured LLM input/output
- Git commit `documents/startup_brain.md` after every update with descriptive message
- Session types (defined in `app/state.py:SESSION_TYPES`) flow through extraction, consistency, pushback, audit, and storage
- All new service function parameters must default to empty string/None for backward compatibility

## File Ownership (for parallel agent work)
When splitting tasks across agents, avoid overlapping file edits:
- **Frontend**: `app/main.py`, `app/state.py`, `app/components/*.py`
- **Backend services**: `services/*.py`
- **Prompts**: `prompts/*.md`
- **Tests**: `tests/test_*.py`

## Testing
- Test transcripts in `tests/test_transcripts/`
- Run unit tests: `python -m pytest tests/ -m "not integration"`
- Run integration tests: `python -m pytest tests/ -m integration` (requires API key + MongoDB)
- 647 unit tests + 28 integration tests, all unit tests run fully offline with mocks

## Deployment
- Streamlit Community Cloud from this repo
- Secrets via `st.secrets` (configured in Cloud dashboard, not in repo)
- Entry point: `app/main.py`
- Required secrets: `ANTHROPIC_API_KEY`, `MONGODB_URI`

## Current Status (as of 2026-03-02)

### Implementation: Complete
All 24 sections of `docs/SPEC.md` are implemented. The system is production-ready for daily use.

**Core pipeline:** Full ingestion (transcript → claim extraction → human confirmation → consistency check → doc update), 3-pass consistency engine (P1+P2 Sonnet, P3 Opus on Critical only), diff-and-verify living document updates, git auto-commit after every update. Living document has 17 sections under Current State, ordered for pitch narrative flow (Kamps cross-check).

**UI:** Conversational chat with query classification and streaming, sidebar dashboard (Current View, External Feedback by source, Recent Changes, Actions with download button, Topic Evolution, API Cost, RAG Health), step indicators across 4-stage ingestion flow, claim editor with inline editing.

**Features:** Session type categorization through entire pipeline, whiteboard photo processing (vision), feedback pattern detection, evolution narratives, pitch material generation (Opus), cost tracking with budget alerts, book framework cross-check via .md upload in chat, direct corrections with informational consistency check, contradiction resolution writing Decision Log and Dismissed Contradictions entries, quick notes via chat prefix (`note:`, `remember:`, `jot:`, `fyi:`) for lightweight doc updates without full pipeline.

**Infrastructure:** Vector search code ready (`vector_search_text()`, upgraded `_get_rag_evidence()`), time-based fallback on free tier, RAG health monitor (warns at 200 claims).

**Tests:** 647 unit tests, 28 integration tests across 22 test files. All unit tests run fully offline with mocks.

### Decided Against

- **Dedicated feedback ingestion UI** — feedback enters via chat (paste email + commentary) or ingestion flow (select "Investor meeting" session type). No extra UI needed.
- **Persistent book framework storage** — temporary .md upload in chat is the permanent solution. No MongoDB persistence for book content.
- **Atlas M10+ upgrade (for now)** — autoEmbed requires paid tier ($57/mo). Time-based retrieval works fine until ~200 claims. Sidebar monitors this automatically.
- **MongoDB backup script** — optional extra for the future. Atlas has its own backup and data volume is tiny.
- **Delete claim chat command** — edge case; if a bad claim slips through, delete directly in MongoDB.

### Spec Deviations (intentional, no action needed)
- Session metadata stored in nested `metadata` dict rather than flat top-level fields — functionally equivalent, MongoDB queries nested fields fine with dot notation.
- Sessions store `summary` (2-3 sentences) rather than a separate `one_line_summary` — serves the same purpose.
- Claims don't store `confirmed_by_user` boolean — redundant since only confirmed claims are ever stored.

### Living Document Sections (17 under Current State)
Problem We're Solving, Target Market / Initial Customer, Value Proposition, Why Now, Traction / Milestones, Business Model / Revenue Model, Pricing, Go-to-Market Strategy, Technical Approach, Competitive Landscape, Moat / Defensibility, Key Assumptions, Open Questions, Key Risks, Team / Hiring Plans, Key Contacts / Prospects, Fundraising Status / Strategy.

Sections from Kamps pitch guide cross-check: Problem We're Solving, Why Now, Traction / Milestones, Moat / Defensibility. Key Contacts / Prospects from user request.

### Next Steps
1. **Use the system daily** — ingest real transcripts, build up the living document, see how consistency engine performs on real data.
2. **When sidebar says "RAG upgrade needed"** (~200 claims) — upgrade Atlas to M10+ and create vector search indexes per `scripts/bootstrap.py`.
