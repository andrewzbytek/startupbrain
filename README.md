# Startup Brain

AI-powered knowledge management for a 2-person startup. Captures session summaries, extracts structured claims, runs multi-pass consistency checks, maintains a living document, and provides conversational querying across all accumulated knowledge.

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
│   ├── main.py                 # Entry point + page routing (state machine)
│   ├── state.py                # Session state, mode transitions, constants
│   └── components/
│       ├── chat.py             # Chat interface, quick notes, contradiction resolution
│       ├── claim_editor.py     # Claim confirmation/editing UI
│       ├── progress.py         # Pipeline progress + step indicator
│       ├── sidebar.py          # Dashboard sidebar (current view, feedback, actions, download)
│       └── styles.py           # Custom CSS injection
├── services/                   # Backend service layer
│   ├── claude_client.py        # Anthropic API wrapper (Sonnet/Opus routing, cost tracking)
│   ├── consistency.py          # 3-pass consistency engine (the core feature)
│   ├── cost_tracker.py         # Monthly cost tracking with budget alerts
│   ├── document_updater.py     # Living document diff-and-verify updates
│   ├── feedback.py             # Feedback patterns, evolution narratives, pitch generation
│   ├── ingestion.py            # Transcript → claims → storage pipeline
│   └── mongo_client.py         # MongoDB Atlas client (sessions, claims, feedback, vector search)
├── prompts/                    # LLM prompt templates (12 markdown files)
│   ├── extraction.md           # Claim extraction from session transcripts
│   ├── consistency_pass1.md    # Wide-net contradiction detection
│   ├── consistency_pass2.md    # Severity filtering (Critical/Notable/Minor)
│   ├── consistency_pass3.md    # Opus deep analysis (Critical only)
│   ├── diff_generate.md        # Structured diff generation for doc updates
│   ├── diff_verify.md          # Diff verification before applying
│   ├── pushback.md             # Informational pushback on direction changes
│   ├── audit.md                # Living document audit against session history
│   ├── evolution.md            # Topic evolution narrative generation
│   ├── feedback_pattern.md     # Feedback pattern detection
│   ├── pitch_generation.md     # Pitch material generation (Opus)
│   └── whiteboard.md           # Whiteboard photo extraction (vision)
├── documents/
│   └── startup_brain.md        # The living document (git-tracked, mirrored to MongoDB)
├── tests/                      # 647 unit tests, 28 integration tests
│   ├── conftest.py             # Shared fixtures and sample data
│   ├── test_transcripts/       # Sample transcripts for testing
│   └── test_*.py               # Test modules (one per service/component)
├── docs/
│   ├── SPEC.md                 # Full system specification (authoritative)
│   └── PLAN.md                 # Implementation plan with agent task breakdown
├── CLAUDE.md                   # Claude Code instructions
├── requirements.txt            # Python dependencies (minimal, no heavy frameworks)
└── .gitattributes              # Line ending normalization (LF)
```

## Architecture

### Data Flow: Session Ingestion

```
Paste transcript → Select session type → [Optional: upload whiteboard]
    │
    ├→ Extract claims (Sonnet + extraction.md)
    │   → Human reviews/edits claims
    │
    ├→ Store session + claims in MongoDB
    │
    ├→ 3-pass consistency check
    │   ├─ Pass 1 (Sonnet): Wide net — flag ALL potential contradictions
    │   ├─ Pass 2 (Sonnet): Severity filter — Critical / Notable / Minor
    │   └─ Pass 3 (Opus):   Deep analysis — ONLY if Critical found
    │
    ├→ Update living document (diff-and-verify, never full rewrite)
    │
    └→ Surface contradictions for founder resolution (if any)
```

### Key Design Decisions

- **Single living document** (`documents/startup_brain.md`) — git-tracked, mirrored to MongoDB
- **Diff-and-verify updates** — never full rewrite, always minimal structured diffs
- **3-pass consistency engine** — Pass 1+2 Sonnet (always), Pass 3 Opus (only if Critical)
- **Cost-aware routing** — Sonnet by default, Opus only for deep analysis and pitch generation
- **XML tags** for all structured LLM input/output
- **Prompts as markdown files** — loaded at runtime, easy to iterate
- **Session types** — categorize sessions (co-founder discussion, investor meeting, customer interview, etc.) to calibrate extraction and consistency behavior
- **Claim confirmation** — human-in-the-loop before anything enters the system
- **Informational pushback** — surfaces context on direction changes, never blocks
- **Book cross-check** — upload a .md book summary in chat for temporary framework cross-referencing
- **Semantic RAG** — Atlas Vector Search with Voyage AI automated embedding for consistency evidence (graceful fallback to time-based)
- **Direct corrections** — "no, actually X" runs a lightweight consistency check before applying (informational only)
- **Quick notes** — prefix-based (`note:`, `remember:`, `jot:`, `fyi:`) lightweight doc updates without full ingestion pipeline
- **Living document download** — one-click download from sidebar Actions
- **Explicit decision tracking** — contradiction resolution writes Decision Log and Dismissed Contradictions entries directly

### State Machine

The app uses an explicit state machine in `st.session_state`:

```
chat → ingesting → confirming_claims → checking_consistency → done
                                                ↓
                                    resolving_contradiction → done
```

## Session Types

Sessions are categorized to calibrate how the system processes them:

| Type | Effect on Pipeline |
|------|-------------------|
| Co-founder discussion | Claims may be exploratory; uncertain statements marked speculative |
| Investor meeting | Feedback attributed to external source; higher contradiction weight |
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

647 unit tests across 22 test files. All service and component tests run fully offline with mocks.

## Deployment

Deployed on **Streamlit Community Cloud** directly from this repo.

- Entry point: `app/main.py`
- Secrets: configured in the Streamlit Cloud dashboard (never in repo)
- Required secrets: `ANTHROPIC_API_KEY`, `MONGODB_URI`

## Cost Model

- Daily ingestion: ~$0.20/session (Sonnet)
- Daily queries: ~$3-5/month (Sonnet)
- Occasional Opus (deep analysis, pitch): ~$15-30/month
- **Estimated total: $25-40/month**
- Hard cap: $400/month, alert at $300

## Project Status

All 24 sections of the spec are implemented. The system is production-ready for daily use. The living document template has 17 sections under Current State, ordered for pitch narrative flow based on a Kamps pitch guide cross-check.

**Deliberate deviations from spec:**
- **Vector search**: Code is in place but Atlas free tier (M0) doesn't support Voyage AI autoEmbed. System uses time-based retrieval with a health monitor that alerts at 200 claims when upgrading to M10+ becomes worthwhile.
- **Book frameworks**: Temporary .md upload in chat replaces the spec's persistent MongoDB storage. No book framework collection is populated.
- **MongoDB backup script** (`scripts/backup_mongodb.py`): Not yet built. Optional — Atlas has its own backup.

## Full Specification

See `docs/SPEC.md` for the complete system specification (all 24 sections).
