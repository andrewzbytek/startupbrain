# Startup Brain

AI-powered knowledge management for a 2-person startup. Two-brain architecture: **Pitch Brain** maintains the investor-facing narrative (curated, Kamps-aligned), while **Ops Brain** tracks internal operational data (CRM, hypotheses, risks, feedback). Both are living documents with claim extraction, structured updates, and conversational querying.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app locally
streamlit run app/main.py

# Run tests
python -m pytest tests/ -m "not integration"
```

## Prerequisites

- Python 3.12+
- MongoDB Atlas cluster (connection string in secrets)
- Anthropic API key (for Claude Sonnet/Opus)

Secrets are configured via Streamlit's `st.secrets` (dashboard for Cloud, `.streamlit/secrets.toml` for local dev). Never commit secrets to the repo.

## Project Structure

```
startupbrain/
├── app/                        # Streamlit UI layer
│   ├── main.py                 # Entry point + auth gate + page routing (state machine)
│   ├── state.py                # Session state, mode transitions, constants
│   └── components/
│       ├── _parsers.py         # Shared document parsing functions
│       ├── chat.py             # Chat interface, quick notes, hypothesis tracking, contradiction resolution
│       ├── claim_editor.py     # Claim confirmation/editing UI
│       ├── dashboard.py        # Pitch Brain dashboard (card grid of all sections)
│       ├── login.py            # Shared-credential login with cookie-based sessions
│       ├── ops_dashboard.py    # Ops Brain dashboard (CRM, hypotheses, risks, feedback)
│       ├── progress.py         # Pipeline progress + step indicator
│       ├── sidebar.py          # Legacy re-export shell (delegates to _parsers.py)
│       ├── styles.py           # Custom CSS injection (incl. brain toggle styling)
│       └── top_bar.py          # Top bar with brain toggle, Ingest/Audit buttons, status pills
├── services/                   # Backend service layer
│   ├── __init__.py             # Package marker
│   ├── claude_client.py        # Anthropic API wrapper (Sonnet/Opus routing, cost tracking)
│   ├── consistency.py          # 3-pass consistency engine (Pitch Brain only)
│   ├── cost_tracker.py         # Monthly cost tracking with budget alerts
│   ├── deferred_writer.py      # Batched writes, crash recovery, session rollback
│   ├── document_updater.py     # Brain-aware living document diff-and-verify updates + MongoDB recovery
│   ├── export.py               # Full context export (living doc + sessions + claims)
│   ├── feedback.py             # Feedback patterns, evolution narratives, pitch generation
│   ├── ingestion.py            # Transcript → claims → storage pipeline (Pitch Brain)
│   ├── ingestion_lock.py       # MongoDB-based ingestion lock + document write lock
│   ├── mongo_client.py         # MongoDB Atlas client (sessions, claims, feedback, vector search)
│   └── ops_ingestion.py        # Simplified ingestion pipeline (Ops Brain, no consistency check)
├── prompts/                    # LLM prompt templates (14 markdown files)
│   ├── extraction.md           # Claim extraction from session transcripts (pitch)
│   ├── ops_extraction.md       # Claim extraction for operational items (ops)
│   ├── consistency_pass1.md    # Wide-net contradiction detection
│   ├── consistency_pass2.md    # Severity filtering (Critical/Notable/Minor)
│   ├── consistency_pass3.md    # Opus deep analysis (Critical only)
│   ├── diff_generate.md        # Structured diff generation (pitch)
│   ├── ops_diff_generate.md    # Structured diff generation (ops)
│   ├── diff_verify.md          # Diff verification before applying
│   ├── pushback.md             # Informational pushback on direction changes
│   ├── audit.md                # Living document audit against session history
│   ├── evolution.md            # Topic evolution narrative generation
│   ├── feedback_pattern.md     # Feedback pattern detection
│   ├── pitch_generation.md     # Pitch material generation (Opus)
│   └── whiteboard.md           # Whiteboard photo extraction (vision)
├── documents/
│   ├── pitch_brain.md          # Pitch Brain living document (investor narrative, git-tracked)
│   └── ops_brain.md            # Ops Brain living document (operational data, git-tracked)
├── scripts/
│   ├── bootstrap.py            # Vector search index bootstrap
│   └── migrate_brain_split.py  # One-time MongoDB migration for brain split
├── render.yaml                 # Render Blueprint deployment config
├── tests/                      # 1012 unit tests, 45 integration tests
│   ├── conftest.py             # Shared fixtures and sample data
│   ├── test_transcripts/       # Sample transcripts for testing
│   └── test_*.py               # 29 test modules (one per service/component)
├── docs/
│   ├── SPEC.md                 # Full system specification (authoritative)
│   └── PLAN.md                 # Implementation plan with agent task breakdown
├── CLAUDE.md                   # Claude Code instructions
├── requirements.txt            # Python dependencies (minimal, no heavy frameworks)
└── .gitattributes              # Line ending normalization (LF)
```

## Architecture

### Two-Brain Architecture

**Pitch Brain** (`documents/pitch_brain.md`) — curated investor narrative with 13 sections under Current State, plus Decision Log and Dismissed Contradictions. Full ingestion pipeline with 3-pass consistency checks. Kamps pitch guide alignment.

**Ops Brain** (`documents/ops_brain.md`) — internal operational knowledge: Contacts/CRM, Active Hypotheses, Key Assumptions, Key Risks, Open Questions, Feedback Tracker, Hiring Plans, Scratchpad Notes. Simplified ingestion (no consistency check).

Both documents are git-tracked, mirrored to MongoDB, and auto-recovered from MongoDB on ephemeral filesystems. All backend services accept a `brain="pitch"|"ops"` parameter (defaulting to `"pitch"` for backward compatibility).

### Data Flow: Session Ingestion

**Pitch Brain pipeline** (full rigor):
```
Paste transcript → Select session type → [Optional: upload whiteboard]
    │
    ├→ Extract claims (Sonnet + extraction.md)
    │   → Human reviews/edits claims
    │
    ├→ Store session + claims in MongoDB (brain="pitch")
    │
    ├→ 3-pass consistency check
    │   ├─ Pass 1 (Sonnet): Wide net — flag ALL potential contradictions
    │   ├─ Pass 2 (Sonnet): Severity filter — Critical / Notable / Minor
    │   └─ Pass 3 (Opus):   Deep analysis — ONLY if Critical found
    │
    ├→ Update pitch_brain.md (diff-and-verify, never full rewrite)
    │
    └→ Surface contradictions for founder resolution (if any)
```

**Ops Brain pipeline** (lightweight):
```
Paste transcript → Select session type
    │
    ├→ Extract claims (Sonnet + ops_extraction.md)
    │   → Human reviews/edits claims
    │
    ├→ Store session + claims in MongoDB (brain="ops")
    │
    └→ Update ops_brain.md (diff-and-verify, no consistency check)
```

### Key Design Decisions

- **Two-brain architecture** — Pitch Brain for investor narrative, Ops Brain for operational data. Keeps the pitch clean and focused.
- **Brain-aware services** — all document/storage functions accept `brain` parameter, defaulting to `"pitch"` for backward compatibility
- **Diff-and-verify updates** — never full rewrite, always minimal structured diffs
- **3-pass consistency engine** — Pass 1+2 Sonnet (always), Pass 3 Opus (only if Critical). Pitch Brain only.
- **Cost-aware routing** — Sonnet by default, Opus only for deep analysis and pitch generation
- **XML tags** for all structured LLM input/output
- **Prompts as markdown files** — loaded at runtime, easy to iterate
- **Session types** — categorize sessions (co-founder discussion, investor meeting, customer interview, etc.) to calibrate extraction and consistency behavior
- **Claim confirmation** — human-in-the-loop before anything enters the system
- **Informational pushback** — surfaces context on direction changes, never blocks
- **Book cross-check** — upload a .md book summary in chat for temporary framework cross-referencing
- **Semantic RAG** — Atlas Vector Search with Voyage AI automated embedding for consistency evidence (graceful fallback to time-based)
- **Cached Anthropic client** — `@st.cache_resource` avoids creating a new client per API call
- **Shared XML utilities** — `extract_xml_tag()` and `escape_xml()` in `claude_client.py`, used by all LLM response parsers
- **Direct corrections** — "no, actually X" runs a lightweight consistency check before applying (informational only)
- **Scratchpad notes** — prefix-based (`note:`, `remember:`, `jot:`, `fyi:`) saved to MongoDB as scratchpad entries (no living document update); surfaced in chat system prompt so the AI can reference them
- **Hypothesis tracking** — prefix-based (`hypothesis:`, `validated:`, `invalidated:`) testable assumption tracking with dashboard status management
- **Brain-aware chat** — context toggle (Pitch / Ops / Both) determines which document(s) feed the system prompt
- **Full context export** — exports living document + all session history with claims as a single MD file
- **Session rollback** — `rollback_last_session()` one-command rollback of the most recent session (MongoDB cleanup + git revert)
- **Socratic chat** — system prompt references Decision Log dates, dismissed contradictions, and Feedback Tracker entries for context-rich responses
- **Dashboard tensions** — surfaces areas of active instability (changelog churn, recent dismissals, decisions under evaluation)
- **Explicit decision tracking** — contradiction resolution writes Decision Log and Dismissed Contradictions entries directly
- **Enrichment-based updates** — diff engine enriches existing positions by adding new information while preserving all existing specific details (numbers, names, amounts)

### State Machines

The app uses explicit state machines in `st.session_state`:

**Pitch Brain:**
```
chat → ingesting → confirming_claims → checking_consistency → done
                                               ↓
                                   resolving_contradiction → done
```

**Ops Brain:**
```
chat → ops_ingesting → ops_confirming → ops_done
```

## Session Types

Sessions are categorized to calibrate how the system processes them:

| Type | Effect on Pipeline |
|------|-------------------|
| Co-founder discussion | Claims may be exploratory; uncertain statements marked speculative |
| Investor meeting | Feedback attributed to external source; higher contradiction weight |
| Investor email/feedback | Feedback from investor correspondence |
| Customer interview | Market claims are high-value; exact language preserved |
| Advisor session | Strategic advice flagged as preference unless explicitly adopted |
| Internal notes | Lighter pushback; may represent thinking-out-loud |
| Other (custom) | Free-text type for edge cases |

## Testing

```bash
# All unit tests (no API keys or MongoDB needed)
python -m pytest tests/ -m "not integration"

# Integration tests (requires API key + MongoDB)
python -m pytest tests/ -m integration

# Verbose with short tracebacks
python -m pytest tests/ -v --tb=short -m "not integration"
```

1012 unit tests + 45 integration tests across 29 test files. All service and component tests run fully offline with mocks.

## Deployment

### Render (primary)

Deployed on **Render** free tier via `render.yaml` Blueprint. Live at **https://startupbrain.onrender.com**.

```bash
# Push to GitHub → Render auto-deploys
# Or: Render dashboard → New → Blueprint → connect this repo
```

- Entry point: `app/main.py`
- Env vars (set in Render dashboard): `ANTHROPIC_API_KEY`, `MONGODB_URI`, `APP_USERNAME`, `APP_PASSWORD`
- MongoDB Atlas Network Access must allow `0.0.0.0/0` (Render uses dynamic outbound IPs)
- Ephemeral filesystem: living documents auto-recover from MongoDB on restart
- Git commits no-op gracefully (no repo on Render)

### Streamlit Community Cloud (legacy)

Still supported. Secrets via Cloud dashboard.

- Required secrets: `ANTHROPIC_API_KEY`, `MONGODB_URI`
- Optional secrets: `APP_USERNAME`, `APP_PASSWORD`

### Authentication

Set `APP_USERNAME` and `APP_PASSWORD` env vars to enable login. In production (detected via `RENDER`/`PORT` env vars), credentials are required — set `DISABLE_AUTH=true` to explicitly skip. In local dev, auth is skipped when env vars are unset. Login uses HMAC-signed cookies for 7-day session persistence.

### Concurrent Access

Two-tier MongoDB-based locking ensures multi-user safety:

- **Ingestion lock** — prevents two users from ingesting simultaneously. 30-minute stale timeout handles browser close / crash. Top bar shows "Ingestion in progress..." when locked.
- **Document write lock** — short-lived lock (2-minute timeout) prevents concurrent read-modify-write corruption on the living document across chat corrections, feedback, hypothesis updates, and batch commits.

## Cost Model

- Daily ingestion: ~$0.20/session (Sonnet)
- Daily queries: ~$3-5/month (Sonnet)
- Occasional Opus (deep analysis, pitch): ~$15-30/month
- **Estimated total: $25-40/month**
- Budget alert at $300/month (forces Sonnet for all requests)

## Project Status

All 24 sections of the spec are implemented plus the two-brain architecture extension. The system is **deployed and running in production** on Render.

**Two-brain architecture:**
- **Pitch Brain** — 13 sections under Current State (investor narrative, Kamps-aligned), Decision Log, Dismissed Contradictions. Full ingestion pipeline with consistency checks.
- **Ops Brain** — 8 sections for internal operations (CRM, hypotheses, risks, feedback, hiring). Simplified ingestion without consistency checks.
- Brain toggle in top bar switches between Pitch and Ops views throughout the UI (dashboard, chat context, ingestion pipeline).

**Security and multi-user safety:**
- Auth hardened for production (requires credentials or explicit opt-out)
- Two-tier MongoDB locking (ingestion lock + document write lock) — all document write paths protected
- Atomic lock operations (`ReturnDocument.AFTER`), UUID-based session IDs, sanitized error messages
- API error messages sanitized — no exception details, API keys, or internal paths leak to users (logged server-side via `logging.error()`)
- XML-escaped living document content in all LLM prompts (system prompt, scratchpad, book frameworks, conversation history) prevents prompt boundary confusion
- All MongoDB errors sanitized (generic user messages, full details server-side only)
- Consistency engine properly filters dismissed contradictions (including short-word claims)
- Consistency engine detects API errors and surfaces "check failed" instead of silently producing "no contradictions"
- Brain isolation hardened: `active_brain` (write target) vs `chat_brain_context` (read scope) correctly separated across all write/read paths; 26 cross-brain data integrity bugs fixed via targeted review

**Deliberate deviations from spec:**
- **Vector search**: Code is in place but Atlas free tier (M0) doesn't support Voyage AI autoEmbed. System uses time-based retrieval with a health monitor that alerts at 200 claims when upgrading to M10+ becomes worthwhile.
- **Book frameworks**: Temporary .md upload in chat replaces the spec's persistent MongoDB storage. No book framework collection is populated.
- **MongoDB backup script** (`scripts/backup_mongodb.py`): Not yet built. Optional — Atlas has its own backup.

## Full Specification

See `docs/SPEC.md` for the complete system specification (all 24 sections).
