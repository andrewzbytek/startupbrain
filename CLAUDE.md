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

## Key Conventions
- Use `@st.cache_resource` for MongoDB connections
- Every Claude API call goes through `services/claude_client.py` which handles cost tracking and Sonnet/Opus routing
- Prompts are markdown files in `/prompts` — read them with open(), never inline them
- Use XML tags for structured LLM input/output
- Git commit `documents/startup_brain.md` after every update with descriptive message

## Testing
- Test transcripts in `tests/test_transcripts/`
- Run tests: `python -m pytest tests/`

## Deployment
- Streamlit Community Cloud from this repo
- Secrets via `st.secrets` (configured in Cloud dashboard, not in repo)
- Entry point: `app/main.py`
```

### Step 2: Plan Mode first (Opus, ~15 minutes)

Follow the 4-phase workflow — Explore → Plan → Implement → Commit. It's what Anthropic recommends and what the Claude Code creator uses daily. 

Do NOT jump into agent teams or implementation. Start Claude Code in **plan mode** (Shift+Tab twice):
```
Read docs/SPEC.md completely. This is the full system specification.
Then produce a detailed implementation plan as docs/PLAN.md.
Break it into tasks with dependencies. Each task should be:
- Ownable by one agent (clear file boundaries, no overlapping edits)
- Completable independently
- Testable in isolation
Group tasks by which agent will own them.