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
- 588+ tests, all unit tests run fully offline with mocks

## Deployment
- Streamlit Community Cloud from this repo
- Secrets via `st.secrets` (configured in Cloud dashboard, not in repo)
- Entry point: `app/main.py`
- Required secrets: `ANTHROPIC_API_KEY`, `MONGODB_URI`

## Current Status (as of 2026-03-01)

### What's Built and Working
- Full ingestion pipeline: transcript → claim extraction → human confirmation → consistency check → doc update
- 3-pass consistency engine (Pass 1+2 Sonnet, Pass 3 Opus on Critical only)
- Living document with diff-and-verify updates
- Conversational chat interface with query classification and streaming
- Sidebar dashboard: Our Current View, External Feedback (split by source), Recent Changes, Actions, Topic Evolution, API Cost
- Session type categorization flowing through the entire pipeline (extraction, consistency, pushback, audit, storage)
- Whiteboard photo processing (vision) — integrated into ingestion page
- Feedback pattern detection and evolution narratives
- Pitch material generation (Opus)
- Cost tracking with budget alerts
- Step indicators across the 4-stage ingestion flow
- 588 unit tests passing, 25 integration tests
- Book framework cross-check via .md upload in chat
- Vector search code ready (`vector_search_text()`, upgraded `_get_rag_evidence()`), but requires Atlas M10+ for autoEmbed — currently using time-based fallback which works fine on free tier
- RAG health monitor: sidebar shows claim count vs threshold (200), warns when upgrade is needed
- Direct corrections run lightweight consistency check (informational only, never blocking)
- Contradiction resolution explicitly writes Decision Log and Dismissed Contradictions entries
- Git auto-commit on living document updates

### Decided Against

- **Feedback ingestion UI** — not needed. Feedback enters via chat (paste email + commentary) or ingestion flow (select "Investor email/feedback" session type). No friction.
- **Full book framework storage** — not needed. Temporary .md upload in chat is the permanent solution. No MongoDB persistence for book frameworks.
- **Atlas M10+ upgrade (for now)** — autoEmbed requires paid tier ($57/mo). Time-based retrieval works fine until ~200 claims. The sidebar monitors this and will alert when upgrade is worthwhile.

### Next Steps
1. **When sidebar says "RAG upgrade needed"** — upgrade Atlas to M10+ and create vector search indexes per `scripts/bootstrap.py`. Until then, time-based retrieval is sufficient.
