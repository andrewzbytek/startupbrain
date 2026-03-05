# Startup Brain

## What This Is
AI-powered knowledge management for a 2-person startup. See `docs/SPEC.md` for full specification.

## Tech Stack
- Python 3.12+, Streamlit, MongoDB Atlas (pymongo), Anthropic API (anthropic SDK)
- NO LangChain, NO LlamaIndex, NO heavy frameworks. Direct API calls only.
- Minimal dependencies. Check requirements.txt before adding anything.

## Architecture
- Streamlit app at `app/main.py` (entry point)
- Layout: Two-view tab navigation (Chat | Dashboard) with persistent top bar
- No sidebar — all content in main area, sidebar hidden via CSS
- Navigation via `session_state.active_view` (`st.radio` styled as tabs), not `st.tabs()`
- Parser functions shared in `app/components/_parsers.py`
- Services in `services/` — each service is a single-purpose module
- LLM prompts in `prompts/` as markdown files — loaded at runtime, never hardcoded
- Two-brain architecture: **Pitch Brain** (`documents/pitch_brain.md`) for investor narrative, **Ops Brain** (`documents/ops_brain.md`) for operational knowledge — both git-tracked, mirrored to MongoDB, auto-recovered from MongoDB on ephemeral filesystems (Render)
- Brain-aware services: all document/storage functions accept `brain="pitch"|"ops"` parameter (default "pitch" for backward compat). MongoDB queries use `$or` pattern with `{"$exists": False}` to include pre-migration docs that lack the `brain` field.
- Two brain variables with different semantics: `active_brain` is the **write target** (set by top bar toggle, always `"pitch"` or `"ops"`, never `"both"`); `chat_brain_context` is the **read scope** (set by chat context selector, can be `"pitch"`, `"ops"`, or `"both"`). Write operations must use `active_brain`; read/display operations use `chat_brain_context`.
- Pitch-only document helpers (`_add_decision`, `_add_dismissed`) accept `brain=` and skip for non-pitch — ops brain has no Decision Log or Dismissed Contradictions sections.
- All state management via `st.session_state` — Streamlit re-runs on every interaction
- Pitch state machine: `chat → ingesting → confirming_claims → checking_consistency → resolving_contradiction → done`
- Ops state machine: `chat → ops_ingesting → ops_confirming → ops_done` (no consistency check)
- `app/main.py` inserts project root into `sys.path` at startup — required because Streamlit only adds the script's directory (`app/`) to the path, not the project root
- Auth gate at top of `app/main.py` — cookie-based login when `APP_USERNAME` + `APP_PASSWORD` env vars are set, requires explicit `DISABLE_AUTH=true` to skip in production (auto-detected via `RENDER`/`PORT` env vars), skipped in local dev when env vars unset
- Ingestion lock via `services/ingestion_lock.py` — MongoDB-based atomic lock prevents concurrent ingestion, 30-min stale timeout for crash recovery
- Document write lock via `services/ingestion_lock.py` — short-lived MongoDB lock (2-min timeout) prevents concurrent read-modify-write on living document across chat corrections, feedback, hypothesis updates, and ingestion batch_commit. **Not re-entrant** — never call `update_document()` (which acquires its own lock) while holding an outer doc lock; instead, call `update_document()` first, then acquire the lock separately for additional writes.

## Session Rollback
- `from services.deferred_writer import rollback_last_session; rollback_last_session()` — rolls back the most recent session (reverts the correct brain document to previous git version first, then deletes session + claims from MongoDB, mirrors to MongoDB, git commits the revert). File write happens before MongoDB deletes so that if the write fails, MongoDB data is preserved.
- `services/mongo_client.py` also exposes `delete_many(collection, query)` and `get_latest_session(brain="")` for manual cleanup

## Key Conventions
- Use `@st.cache_resource(ttl=300)` for MongoDB connections and the Anthropic client — TTL prevents permanent `None` caching if unavailable at startup
- Every Claude API call goes through `services/claude_client.py` which handles cost tracking, Sonnet/Opus routing, and error sanitization
- Shared XML parsing utility: `from services.claude_client import extract_xml_tag` — used by ingestion.py, consistency.py, feedback.py (eliminates duplication)
- Prompts are markdown files in `/prompts` — read them with open(), never inline them
- Use XML tags for structured LLM input/output
- Git commit living documents after every update with descriptive message (no-ops gracefully when git unavailable, e.g. Render)
- Living document file writes are atomic: `tempfile.mkstemp()` + `os.replace()` prevents partial-write corruption on crash
- MongoDB mirror is written before the file (source of truth on Render's ephemeral filesystem)
- Session types (defined in `app/state.py:SESSION_TYPES`) flow through extraction, consistency, pushback, audit, and storage
- All new service function parameters must default to empty string/None for backward compatibility
- Auth: shared credentials via `APP_USERNAME` + `APP_PASSWORD` env vars. Cookie-based 7-day sessions (`streamlit-cookies-controller`). Auth skipped in local dev when env vars unset; production (Render) requires credentials or explicit `DISABLE_AUTH=true`.
- Ingestion lock: MongoDB-based (`services/ingestion_lock.py`). Only one user can ingest at a time. Lock auto-expires after 30 min (crash recovery). Top bar shows lock status.
- Document write lock: MongoDB-based (`services/ingestion_lock.py`). Short-lived lock (2-min timeout) for living document writes. Prevents concurrent corruption from chat corrections, feedback, hypothesis, and batch_commit.
- Session IDs: UUID-based (`uuid.uuid4()`), not Python memory addresses. Stored in `st.session_state._lock_session_id`.
- Error messages: sanitized for users (generic messages), full details logged server-side only. Prevents MongoDB URI / path leakage.

## File Ownership (for parallel agent work)
When splitting tasks across agents, avoid overlapping file edits:
- **Frontend layout**: `app/main.py`, `app/state.py`
- **Frontend components**: `app/components/top_bar.py`, `app/components/dashboard.py`, `app/components/ops_dashboard.py`, `app/components/chat.py`, `app/components/claim_editor.py`, `app/components/progress.py`, `app/components/login.py`
- **Theme/styles**: `app/components/styles.py`
- **Parsers**: `app/components/_parsers.py` (shared parsing functions), `app/components/sidebar.py` (legacy re-export shell)
- **Backend services**: `services/*.py`
- **Prompts**: `prompts/*.md`
- **Tests**: `tests/test_*.py`

## Testing
- Test transcripts in `tests/test_transcripts/`
- Run unit tests: `python -m pytest tests/ -m "not integration"`
- Run integration tests: `python -m pytest tests/ -m integration` (requires API key + MongoDB)
- 1011 unit tests + 45 integration tests across 29 test files, all unit tests run fully offline with mocks

## Deployment
- **Render** (primary): `render.yaml` Blueprint — free tier, auto-deploy from GitHub
  - Live at: `https://startupbrain.onrender.com`
  - Start command: `streamlit run app/main.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
  - Ephemeral filesystem: living documents auto-recover from MongoDB on restart
  - Git commits no-op (no git repo on Render)
  - Set env vars in Render dashboard: `ANTHROPIC_API_KEY`, `MONGODB_URI`, `APP_USERNAME`, `APP_PASSWORD`
  - MongoDB Atlas Network Access must allow `0.0.0.0/0` (Render uses dynamic outbound IPs)
- **Streamlit Community Cloud** (legacy): still works, secrets via Cloud dashboard
- Entry point: `app/main.py`
- Required secrets/env vars: `ANTHROPIC_API_KEY`, `MONGODB_URI`
- Optional secrets/env vars: `APP_USERNAME`, `APP_PASSWORD` (enables login gate), `DISABLE_AUTH` (set to `true` to skip auth in production)

## Current Status (as of 2026-03-05)

### Implementation: Complete
All 24 sections of `docs/SPEC.md` are implemented plus brain split architecture. The system is production-ready for daily use.

**Two-brain architecture:** Pitch Brain (`documents/pitch_brain.md`) holds the curated investor narrative (13 pitch sections + Decision Log + Dismissed Contradictions). Ops Brain (`documents/ops_brain.md`) holds operational knowledge (contacts, hypotheses, risks, assumptions, questions, feedback, hiring, scratchpad). Brain toggle in top bar switches context. Migration script at `scripts/migrate_brain_split.py`.

**Core pipeline:** Pitch Brain: full ingestion (transcript → claim extraction → human confirmation → consistency check → doc update), 3-pass consistency engine (P1+P2 Sonnet, P3 Opus on Critical only), diff-and-verify living document updates, git auto-commit after every update. Ops Brain: simplified pipeline (transcript → extraction with ops_extraction prompt → human confirmation → direct doc update using ops_diff_generate prompt, no consistency check).

**UI:** Dark command center theme (Vercel/Raycast inspired). Two-view layout: Chat (default) with quick command chips, Dashboard (brain-dependent: pitch shows 13-section card grid + panels, ops shows contacts/hypotheses/risks/feedback). Persistent top bar with Brain toggle (Pitch/Ops), Ingest button (routes to correct pipeline), Audit button (pitch only), and API cost + RAG health status pills. No sidebar. Chat has brain context selector (Pitch/Ops/Both) for system prompt routing. Conversational chat with query classification and streaming, HTML/CSS step indicators, claim editor with inline editing and `ops_mode` parameter for brain-specific button rendering.

**Features:** Session type categorization through entire pipeline, whiteboard photo processing (vision), feedback pattern detection, evolution narratives, pitch material generation (Opus), cost tracking with budget alerts, book framework cross-check via .md upload in chat, direct corrections with informational consistency check (brain-aware — routes to active brain), contradiction resolution writing Decision Log and Dismissed Contradictions entries, scratchpad notes via chat prefix (`note:`, `remember:`, `jot:`, `fyi:`) saved to MongoDB only (no doc update, surfaced in chat system prompt across all brain contexts), hypothesis tracking via chat prefix (`hypothesis:`, `validated:`, `invalidated:`) or dashboard form, Socratic system prompt with context surfacing and feedback echo, dashboard tensions indicator (changelog churn, dismissed contradictions, decisions under evaluation), 'challenge' query classification routing to Opus, 3 quick command chips (note, hypothesis, contact) below chat input for prefix discoverability, full context export (living doc + session history + claims as single MD — available for both Pitch and Ops brains via dashboard), session rollback command, shared-credential auth with cookie persistence, ingestion lock + document write lock for concurrent access.

**Security:** Auth hardened for production (requires credentials or explicit `DISABLE_AUTH=true`), HMAC cookie signing with PBKDF2-stretched key (100k iterations, app-specific salt, no fallback key), sanitized error messages (no URI/path/API key leakage — all API and MongoDB errors use `logging.error()` server-side + generic user-facing messages), UUID-based session IDs, XML-escaped living document content in all LLM prompts (system prompt, scratchpad notes, book frameworks, conversation history — including first-turn messages — all escaped via `escape_xml()`), `re.escape()` on all user-provided values in MongoDB `$regex` queries (prevents ReDoS).

**Multi-user safety:** Two-tier locking — long-lived ingestion lock (30-min timeout) for full pipeline, short-lived document write lock (2-min timeout) for individual writes (including dashboard hypothesis forms, chat hypothesis status updates, and contradiction resolution fallback path). Lock documents initialized at app startup via `ensure_lock_document()` + `doc_write_lock` upsert (prevents first-use race conditions on fresh deployments). Atomic lock operations via `find_one_and_update` with `ReturnDocument.AFTER`. DeferredWriter checkpoints track lock ownership to prevent cross-user recovery hijacking. Crash recovery detects document drift (warns if living document changed since checkpoint was saved). Dismissed contradictions properly filtered in consistency engine Pass 2. Doc lock acquisition resilient to transient MongoDB errors (try/except with retry). Ops dashboard hypothesis form shows persistent warning on lock failure (prevents silent text loss). DeferredWriter deletes checkpoint on doc-lock failure to prevent duplicate claims on resume. Orphaned sessions cleaned up on batch_commit failure.

**LLM integration hardening:** Anthropic client cached via `@st.cache_resource(ttl=300)` (re-checked every 5 min, prevents permanent `None` caching). Consistency engine detects API errors and surfaces "check failed" instead of silently producing "no contradictions". All 3 consistency passes, evolution narratives, and pitch material generation are brain-aware. Pass 2 input properly wrapped in `<pass1_output>` tags. Book framework content excluded from recall/historical query types to avoid inflating system prompts. Ops brain uses dedicated `ops_diff_verify.md` prompt for diff verification (pitch uses `diff_verify.md`). RAG health monitor is brain-aware — shows claim count for the active brain. Top bar cache invalidated on brain switch (prevents stale RAG pill).

**Data integrity, locking & security hardening (2026-03-05 review — 15 bugs fixed):** Deadlock in `_resolve_contradiction()` fixed — `update_document()` (which manages its own doc lock) no longer called inside an outer doc lock scope; each action path ("update"/"keep"/"explain") acquires the lock only for its own read-modify-write. Prompt injection on first-turn chat message fixed (`escape_xml()` applied unconditionally). Atomic file writes via `tempfile.mkstemp()` + `os.replace()` prevent partial-write corruption. MongoDB mirror written before file in both `update_document()` and `batch_commit()` (source of truth on Render's ephemeral FS). `re.escape()` applied to all user-provided values in `$regex` MongoDB queries (prevents ReDoS). Lock documents initialized at startup (prevents first-use race on fresh deployments). HMAC cookie key uses PBKDF2 with 100k iterations. Rollback reordered: file write before MongoDB deletes, session deleted before claims (safer failure ordering). Crash recovery logs errors instead of bare `pass`. Quick note checks `insert_claim` return value. Feedback themes update failure logged. Lock error messages no longer include raw exception text. Crash recovery UI warns when living document has changed since checkpoint was saved. Batch_commit cleans up orphaned sessions on failure.

**State machine & session state hardening (2026-03-04 review — 16 bugs fixed):** `@st.cache_resource(ttl=300)` on MongoDB and Anthropic clients prevents permanent `None` caching on startup failure. Cancel button added to `render_contradiction_resolution()` (was the only pipeline stage without an escape hatch). `_consistency_failed` flag prevents re-running expensive LLM calls on every Streamlit rerun after an exception (explicit Retry/Cancel instead). `_ops_commit_failed` flag prevents ops ingestion auto-retry on every rerun (explicit Retry button instead). `uploaded_file.getvalue()` instead of `.read()` for whiteboard (safe after `st.image()` consumes pointer). `evolution_result`, `_context_export_data`, `_ops_context_export_data` cleared in `reset_ingestion()` and brain switch handler (prevents stale cross-brain data). `reset_ingestion()` no longer forces `active_view = "chat"` (preserves Dashboard tab). Lock-blocked "Back to Chat" paths use `reset_ingestion()` instead of `set_mode("chat")` (cleans up stale `_lock_session_id`). Book framework file only re-decoded when filename changes (skips redundant decode on every rerun). Dead `ingestion_status` key removed. `_batch_commit_failed`, `_consistency_failed`, `_ops_commit_failed` added to `init_session_state()` defaults.

**Brain isolation integrity (2026-03-04 review — 26 bugs fixed):** DeferredWriter threads `self.brain` to all callees (`verify_diff`, `apply_diff`, `_add_decision`, `_add_dismissed`). Direct corrections use `active_brain` (write target), not `chat_brain_context` (read scope). Recall context filters feedback by brain. Feedback field reads use correct MongoDB field name (`feedback_text`). `get_recurring_themes()`/`should_alert()` accept `brain=` parameter. Crash recovery syncs both `active_brain` and `chat_brain_context`. `_add_section` has brain-aware fallback insertion (ops: before Scratchpad Notes; pitch: inside Current State). `_add_decision`/`_add_dismissed` guard against non-pitch brain (ops has no Decision Log/Dismissed Contradictions). `get_latest_session()` accepts `brain=` filter. Feedback themes written back to MongoDB after pattern detection. Dashboard hypothesis form inserts claim into MongoDB for query parity. `run_ops_ingestion()` parameterized with `brain=` (default "ops").

**Infrastructure:** Vector search code ready (`vector_search_text()`, upgraded `_get_rag_evidence()`), time-based fallback on free tier, RAG health monitor (warns at 200 claims). Render deployment live at `https://startupbrain.onrender.com` (free tier), ephemeral filesystem handled by MongoDB document recovery, git no-op when not in a repo.

**Tests:** 1011 unit tests, 45 integration tests across 29 test files. All unit tests run fully offline with mocks.

### Decided Against

- **Dedicated feedback ingestion UI** — feedback enters via chat (paste email + commentary) or ingestion flow (select "Investor meeting" session type). No extra UI needed.
- **Persistent book framework storage** — temporary .md upload in chat is the permanent solution. No MongoDB persistence for book content.
- **Atlas M10+ upgrade (for now)** — autoEmbed requires paid tier ($57/mo). Time-based retrieval works fine until ~200 claims. The top bar status pill monitors this automatically.
- **MongoDB backup script** — optional extra for the future. Atlas has its own backup and data volume is tiny.
- **Delete claim chat command** — edge case; if a bad claim slips through, delete directly in MongoDB.

### Spec Deviations (intentional, no action needed)
- Session metadata stored in nested `metadata` dict rather than flat top-level fields — functionally equivalent, MongoDB queries nested fields fine with dot notation.
- Sessions store `summary` (2-3 sentences) rather than a separate `one_line_summary` — serves the same purpose.
- Claims don't store `confirmed_by_user` boolean — redundant since only confirmed claims are ever stored.

### Pitch Brain Sections (13 under Current State)
Problem We're Solving, Target Market / Initial Customer, Value Proposition, Why Now, Traction / Milestones, Business Model / Revenue Model, Pricing, Go-to-Market Strategy, Technical Approach, Competitive Landscape, Moat / Defensibility, Team, Fundraising Status / Strategy. Plus: Decision Log, Dismissed Contradictions.

### Ops Brain Sections (8 top-level)
Contacts / Prospects, Active Hypotheses, Key Assumptions, Key Risks, Open Questions, Feedback Tracker, Hiring Plans, Scratchpad Notes.

### Next Steps
1. **Use the system daily** — ingest real transcripts, build up the living document, see how consistency engine performs on real data.
2. **When top bar says "RAG upgrade needed"** (~200 claims) — upgrade Atlas to M10+ and create vector search indexes per `scripts/bootstrap.py`.
