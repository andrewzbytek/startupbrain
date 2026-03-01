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
- 561+ tests, all unit tests run fully offline with mocks

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
- 561 unit tests passing, 25 integration tests

### What's NOT Done Yet (from SPEC.md)
These sections from the spec are not yet implemented or need work:

1. **Book framework ingestion** (SPEC Section 9) — uploading startup books (e.g., Mom Test, Lean Startup) and having the system extract frameworks for pitch generation. `services/feedback.py:generate_pitch_materials()` accepts `book_frameworks` but there's no UI to upload/manage them and `services/mongo_client.py:get_book_frameworks()` returns from a collection that has no ingestion path.

2. **Voyage AI embeddings for RAG** (SPEC Section 10) — the spec calls for Voyage AI embeddings stored in MongoDB Atlas Vector Search for semantic retrieval. Currently `_get_rag_evidence()` in `consistency.py` does simple recent-document retrieval, not vector search. No embedding generation is implemented.

3. **Direct correction handling in chat** (SPEC Section 3.4) — `chat.py` has `is_direct_correction()` detection but the actual correction → document update flow isn't fully wired.

4. **Feedback ingestion UI** — `services/feedback.py:ingest_feedback()` works but there's no dedicated UI for it. Feedback currently only enters via the chat interface or as part of session claims.

5. **Living document git auto-commit** — `document_updater.py` updates the file but doesn't auto-commit to git after each update (spec says it should).

6. **Dismissed contradiction management** — the dismissal section exists in the living doc and `check_dismissed()` filters against it, but there's no UI to dismiss contradictions (the resolution flow doesn't write to the dismissed section).

7. **Decision log entries** — contradictions that are resolved should create entries in the Decision Log section of the living document. This isn't wired up yet.

### Next Steps (Priority Order)
1. **Voyage AI embeddings** — biggest impact on consistency quality. Wire up embedding generation on claim storage, add vector search to `_get_rag_evidence()`.
2. **Git auto-commit** — `document_updater.py` should commit `documents/startup_brain.md` after every successful update.
3. **Dismissed contradictions + Decision log** — wire the contradiction resolution UI to update the living document's Dismissed Contradictions and Decision Log sections.
4. **Book framework ingestion UI** — add a settings/admin page for uploading book summaries.
5. **Feedback ingestion UI** — dedicated page or chat command for adding investor/customer feedback outside of session ingestion.
