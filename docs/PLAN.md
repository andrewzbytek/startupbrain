# Startup Brain — Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit Cloud                        │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │   Sidebar     │  │         Main Chat Panel          │ │
│  │  - Dashboard  │  │  - Conversational interface      │ │
│  │  - Controls   │  │  - Claim confirmation UI         │ │
│  │  - Cost       │  │  - Contradiction resolution      │ │
│  │  - Themes     │  │  - Progress indicators           │ │
│  └──────┬───────┘  └──────────────┬───────────────────┘ │
│         │                         │                      │
│  ┌──────┴─────────────────────────┴───────────────────┐ │
│  │              app/state.py (State Machine)           │ │
│  │  chat | ingesting | confirming_claims |             │ │
│  │  checking_consistency | resolving_contradiction     │ │
│  └────────────────────────┬───────────────────────────┘ │
│                           │                              │
│  ┌────────────────────────┴───────────────────────────┐ │
│  │                 Services Layer                      │ │
│  │  ingestion.py  consistency.py  document_updater.py  │ │
│  │  feedback.py   claude_client.py  cost_tracker.py    │ │
│  └──────────┬──────────────────────┬──────────────────┘ │
└─────────────┼──────────────────────┼────────────────────┘
              │                      │
     ┌────────┴────────┐    ┌───────┴────────┐
     │  MongoDB Atlas   │    │  Anthropic API  │
     │  - sessions      │    │  - Sonnet       │
     │  - claims        │    │  - Opus         │
     │  - feedback      │    │  (cost-routed)  │
     │  - cost_log      │    └────────────────┘
     │  + Voyage AI     │
     │    embeddings     │
     └─────────────────┘
```

## Agent Task Breakdown

### Wave 1 (Parallel, no blockers)
| Agent | Task | Files |
|-------|------|-------|
| infra-agent | MongoDB client, bootstrap, living doc template, config | services/mongo_client.py, scripts/bootstrap.py, documents/startup_brain.md, requirements.txt, .gitignore |
| prompt-engineer | All 12 LLM prompt templates | prompts/*.md |

### Wave 2 (Blocked by Wave 1)
| Agent | Task | Files | Blocked By |
|-------|------|-------|------------|
| services-agent | Claude client, cost tracker, document updater, ingestion, consistency, feedback | services/*.py | infra-agent, prompt-engineer |

### Wave 3 (Blocked by Wave 2)
| Agent | Task | Files | Blocked By |
|-------|------|-------|------------|
| ui-agent | Streamlit app, components, state machine | app/*.py, app/components/*.py | services-agent |
| test-agent | Test suite, test transcripts | tests/** | services-agent |

## Key Design Decisions

1. **Single living document** (startup_brain.md) — git-tracked, mirrored to MongoDB
2. **Diff-and-verify updates** — never full rewrite, always minimal structured diffs
3. **3-pass consistency engine** — Pass 1+2 Sonnet (always), Pass 3 Opus (only if Critical)
4. **Cost-aware routing** — Sonnet default, Opus only for deep analysis/pitch/critical contradictions
5. **XML tags** for all LLM input/output structure
6. **Prompts as markdown files** — loaded at runtime, easy to iterate
7. **State machine** in session_state — explicit modes for multi-step flows
8. **Claim confirmation step** — human-in-the-loop before anything enters the system

## Cost Model
- Daily ingestion: ~$0.20/session (Sonnet)
- Daily queries: ~$3-5/month (Sonnet)
- Occasional Opus: ~$15-30/month
- **Estimated total: $25-40/month**
- Hard cap: $400/month, alert at $300
