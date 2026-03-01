# STARTUP BRAIN v3 (FINAL) — Complete System Specification for Claude Code

## Instructions for Claude Code

You are being given an extremely detailed specification for a system called "Startup Brain." This specification was produced through an extended multi-hour conversation between two technical co-founders and an AI advisor, then critiqued twice and revised. Every detail below reflects a deliberate decision. Your job is to formulate a comprehensive, multi-agent build plan for this entire system. Do NOT start building yet — produce the plan first, covering architecture, file structure, implementation order, prompt design, and testing strategy.

Read this entire document carefully before producing the plan. There are subtle interdependencies between sections.

**KEY SECTIONS TO PAY SPECIAL ATTENTION TO:**
- Section 3.2: Ingestion pipeline with claim confirmation step
- Section 4: Single living document design with diff-and-verify update strategy
- Section 5: Multi-pass consistency engine (the #1 feature)
- Section 6: Informational pushback (NEVER blocking)
- Section 11: Streamlit-specific technical guidance
- Section 13: Cost-aware Sonnet/Opus routing
- Section 22: Failure handling (every component must degrade gracefully)
- Section 24: Deployment (Streamlit Community Cloud from GitHub)

---

## 1. PROJECT OVERVIEW

### 1.1 What This Is

A centralized AI-powered knowledge system for a two-person early-stage startup. It serves as the "central brain" of the startup — capturing, organizing, analyzing, and querying all knowledge generated during the ideation phase. The startup is in the compliance space for nuclear, oil & gas, and power generation, working primarily with PDFs and technical drawings.

### 1.2 Core Value Proposition

The founders have daily brainstorming sessions (sometimes twice daily) where they talk, draw on a whiteboard, and generate ideas. After each session, they trigger Wispr Flow and record a clean summary of conclusions — not raw brainstorming, but deliberate, post-discussion summaries of what they agreed on. They then have a clean transcript and optionally a whiteboard photo.

They want a system that:

1. Ingests these clean summaries with minimal friction (friction of input is the #1 reason they would abandon the system)
2. Automatically extracts key decisions, claims, and ideas (with a quick human confirmation step)
3. Checks new information against everything that came before for internal consistency
4. Maintains a living, evolving representation of the startup's current state
5. Allows conversational querying across all accumulated knowledge
6. Detects patterns in external feedback (investors, customers)
7. Can generate outputs like pitch talking points, using frameworks from reference books
8. Surfaces relevant context (informationally, never blocking) when the founders change direction
9. Records the evolution of thinking — not just current state but how they got there

### 1.3 Users

Two technical co-founders (engineers, not software engineers). Both use Claude Code daily, know Python and C++, and are comfortable with APIs and cloud deployment. One person will operate the system; the other will send transcripts and photos that get pasted in.

### 1.4 Non-Goals

- This is NOT a CRM, though it has light feedback-tracking features
- This is NOT a project management tool
- This is NOT a wiki or corporate intranet (they explicitly want to avoid anything that feels like Notion, old-school intranets, or corporate Wikipedias)
- No multi-user auth or role-based access needed
- No need for time-travel/rollback to past states (but evolution history is needed)
- No real-time collaboration features
- No integration with Wispr Flow or other tools (copy-paste is fine)

### 1.5 Input Convention (IMPORTANT)

The system's reliability depends on input quality. Inputs are NOT raw brainstorming transcripts with jokes, tangents, and devil's advocate positions. They are:
- **Session summaries**: Clean, deliberate post-session recordings where the founders summarize what they agreed on
- **Investor/customer feedback**: Either post-meeting summaries recorded via Wispr Flow, or pasted emails
- **Whiteboard photos**: Supplementary visual context

This means the extraction problem is simplified — everything in the transcript IS a real conclusion or decision, not noise to be filtered. The system should assume inputs are clean and deliberate.

---

## 2. TECHNICAL STACK (DECIDED)

These decisions are final. Do not suggest alternatives.

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Vector Database + Document Store | MongoDB Atlas (free tier) | Unified platform with Voyage AI integration, automated embedding, managed cloud |
| Embedding Model | Voyage AI (via MongoDB Atlas) | Acquired by MongoDB, integrated natively — automated embedding on insert/update, state-of-the-art retrieval accuracy, 200M free tokens on Atlas |
| LLM — Routine Tasks | Claude Sonnet (via Anthropic API) | Summarizing, extracting, first-pass consistency checks, document updates |
| LLM — Complex Reasoning | Claude Opus (via Anthropic API) | Used SPARINGLY — only for Critical contradictions, strategic analysis, and pitch generation. See Section 13 for routing. |
| Frontend + Hosting | Streamlit on Streamlit Community Cloud | Free, deploys from GitHub, zero DevOps. See Sections 11 and 24. |
| Living Document | Single markdown file (`startup_brain.md`) | Contains current state, decision log, and feedback tracker in one atomic document. See Section 4. |
| Version Control / Backup | GitHub repository | Code hosting, auto-deployment trigger, living document history |
| Code Hosting | GitHub | Both founders have experience, Streamlit Community Cloud deploys directly from GitHub |

### 2.1 Why MongoDB Atlas + Voyage AI (Not ChromaDB)

The founders specifically chose this over ChromaDB with local sentence-transformers because:
- Automated embedding removes the need to write/maintain embedding pipelines and sync code
- "Same company" integration between MongoDB and Voyage AI means tighter, more reliable integration
- Voyage 4 models are state-of-the-art for retrieval
- Atlas free tier (512MB) is more than sufficient for months
- Setting up APIs with Claude Code is easy for these founders
- They explicitly preferred this "LLM maximalist" approach over local-first simplicity

### 2.2 Why Not Just Context Stuffing

Even though the corpus is small (~50K words/month, ~65K tokens/month), RAG was chosen because:
- Context rot / "lost in the middle" problem is real and dangerous for the consistency-checking use case (the #1 priority feature)
- At 120K+ tokens, models lose fidelity on content in the middle of the context window
- The consistency engine can't afford to silently miss contradictions — that's the worst failure mode
- RAG keeps query costs low (retrieve 3-5 relevant chunks vs. sending everything)
- However: the living document (`startup_brain.md`) is always loaded in FULL context — it's small enough and it's the primary surface for consistency checks

### 2.3 Chunking Strategy (IMPORTANT)

MongoDB + Voyage AI automated embedding generates one embedding per document. Storing an entire 2,000-word transcript as a single document produces one embedding that's too coarse for retrieval. The solution:

**Store whole transcripts AND extracted claims as separate documents.**

- Each raw transcript is stored as one document in the `sessions` collection (for archival and full-text queries)
- During extraction, the LLM produces a list of discrete claims/decisions. Each confirmed claim is stored as a separate document in the `claims` collection with metadata linking it back to the source session
- Voyage AI auto-embeds each claim individually, giving fine-grained retrieval
- This means the extraction prompt does double duty: it extracts structure for the consistency engine AND produces the chunks for RAG
- This approach avoids writing manual chunking code while getting good retrieval granularity

### 2.4 Corpus Size Projections

- ~2,000 words/day transcripts (clean summaries, not raw brainstorming)
- ~25 working days/month
- = ~50,000 words/month = ~65K tokens/month
- After 6 months: ~400K tokens of transcripts
- Plus 2-3 book framework summaries (~30K tokens each)
- Plus living document (~10-20K tokens)
- Total after 6 months: ~600K tokens
- MongoDB Atlas free tier (512MB) can handle this easily

### 2.5 Budget

- $400/month maximum for all API costs
- Estimated actual cost: $100-200/month (see Section 13 for detailed breakdown)
- Need a cost tracking mechanism to prevent runaway API calls
- No background processes that burn tokens — each interaction is a discrete API call
- Founders may apply for Anthropic API credits

---

## 3. ARCHITECTURE

### 3.1 Three-Layer Architecture

**Layer 1: Storage (MongoDB Atlas + GitHub)**
- MongoDB Atlas stores all raw inputs (transcripts, whiteboard extractions, feedback) as documents with metadata
- Confirmed extracted claims stored as separate documents for fine-grained RAG retrieval
- Voyage AI automated embedding handles vector indexing on insert/update
- Single living document (`startup_brain.md`) stored in the GitHub repo, version-controlled with git, and mirrored in MongoDB
- Each document in MongoDB has metadata: date, source type, participants, tags, one-line context

**Layer 2: Intelligence (Claude API)**
- Claude Sonnet handles extraction, summarization, consistency checking (Passes 1-2), and document updates
- Claude Opus reserved for genuinely hard tasks: deep contradiction analysis (Pass 3), strategic analysis, and pitch generation (see Section 13)
- All consistency checks run against the full living document loaded in context (it's always small enough)
- RAG retrieval from MongoDB is used for evidence gathering and historical queries

**Layer 3: Interface (Streamlit on Streamlit Community Cloud)**
- Main chat panel for conversational interaction
- Sidebar showing startup_brain.md rendered as a structured overview/dashboard
- File upload area for transcripts and whiteboard photos
- Buttons/triggers for consistency checks
- Progress indicators for multi-step operations

### 3.2 Data Flow — Ingestion (IMPORTANT — includes claim confirmation)

```
User pastes Wispr Flow summary + optional whiteboard photo
    ↓
System asks 2 quick optional questions:
    - "Who was in this session?"
    - "What was the rough topic?"
    (Can be skipped — system can infer from context)
    ↓
Progress indicator: "✅ Transcript received → ⏳ Extracting claims..."
    ↓
Input sent to Claude Sonnet:
    - Extract key claims, decisions, and ideas as discrete statements
    - Generate a session summary
    - Tag with topics/themes
    ↓
Progress indicator: "✅ Claims extracted (found N claims) → ⏳ Awaiting your confirmation..."
    ↓
★ CLAIM CONFIRMATION STEP ★
System shows extracted claims as an interactive list:
    "I extracted these 7 claims from today's session:
    
    ☑ 1. Our initial target customer is small nuclear power plants in the UK
    ☑ 2. Pricing will be per-facility, starting at £50K/year
    ☑ 3. MVP will focus on compliance document management only
    ☑ 4. Go-to-market through existing industry conferences
    ☑ 5. Technical approach: PDF parsing + LLM extraction
    ☑ 6. First hire will be a domain expert from nuclear industry
    ☑ 7. Targeting £500K pre-seed raise in Q2 2026
    
    [✓ Looks good, proceed] [Edit claims]"

If "Looks good" → proceed with all claims
If "Edit claims" → founder can:
    - Edit any claim's text inline (system replaces with corrected version)
    - Uncheck/remove claims that are wrong or weren't actually said
    - Add a claim that was missed (type it in, system adds it)
    Then click "Proceed with corrected claims"
    ↓
Progress indicator: "✅ Claims confirmed → ⏳ Checking consistency (Pass 1 of 2)..."
    ↓
Multi-pass consistency check (see Section 5):
    Pass 1 (Sonnet): Find ALL potential contradictions against startup_brain.md
    Pass 2 (Sonnet): Rank by severity, filter noise, check dismissed list
    Pass 3 (Opus, ONLY if Pass 2 found Critical contradictions): Deep analysis
    ↓
Progress indicator updates with each pass completion
    ↓
If contradictions found → Informational alert with action buttons (see Section 5.5)
If revisiting rejected idea → Surface prior decision context
If no issues → "✅ No inconsistencies found"
    ↓
Auto-update living document using diff-and-verify strategy (see Section 4.4)
    ↓
Raw transcript stored in MongoDB `sessions` collection
Each confirmed claim stored in MongoDB `claims` collection (separate docs, auto-embedded)
    ↓
Living document updated, committed to git, mirrored to MongoDB
    ↓
Progress indicator: "✅ All done. Session ingested, N claims stored, living document updated."
```

### 3.3 Data Flow — Querying

```
User asks a question (e.g., "What's our current pricing model?")
    ↓
System determines query type:
    - Current state query → Read from startup_brain.md (always in context)
    - Historical query → RAG retrieval from MongoDB ("what did we discuss about X on Feb 12?")
    - Analysis query → Load living doc + relevant RAG results, send to Sonnet (or Opus if complex)
    - Generation query → Load living doc + book frameworks + relevant context, send to Opus
    ↓
Response returned in chat
    ↓
If response involves an update to the startup's thinking → update living document via diff-and-verify
```

---

## 4. THE LIVING DOCUMENT (CRITICAL DESIGN)

### 4.1 Single Document: `startup_brain.md`

This is the heart of the system. Everything lives in one atomic markdown document with clear section headers. The LLM updates it as a single unit, so there's never a state where one section was updated but another wasn't.

Structure:

```markdown
# Startup Brain — [Startup Name]
Last updated: [date]

## Current State

### Target Market / Initial Customer
**Current position:** [what we currently believe]
**Changelog:**
- [date]: Changed from X to Y because [reason]. Source: [session/feedback]
- [date]: Initial position set. Source: [session]

### Value Proposition
[same structure]

### Business Model / Revenue Model
[same structure]

### Pricing
[same structure]

### Go-to-Market Strategy
[same structure]

### Technical Approach
[same structure]

### Competitive Landscape
[same structure]

### Key Assumptions
[things we believe but haven't validated]

### Open Questions
[things we need to figure out]

### Key Risks
[same structure]

### Team / Hiring Plans
[same structure]

### Fundraising Status / Strategy
[same structure]

## Decision Log

### [Date] — [Decision Title]
**Decision:** [what was decided]
**Alternatives considered:** [list]
**Why alternatives were rejected:** [reasons]
**Context:** [what prompted this decision]
**Participants:** [who was involved]

[more entries...]

## Feedback Tracker

### Recurring Themes
- **[Theme]**: Mentioned by [N] sources ([list of names]). [Status: Addressed/Unaddressed]

### Individual Feedback
#### [Date] — [Source Name] ([Type: investor/customer/advisor])
**Summary:** [what they said]
**Themes:** [tags]
**Action taken:** [what we did, or why we dismissed it]

[more entries...]

## Dismissed Contradictions
[Contradictions the system flagged but the founders explicitly dismissed — prevents re-flagging]
- [Date]: [description] — Dismissed because: [reason]
```

### 4.2 Size Management

For the MVP, don't worry about document size — it will be manageable for months. Future compaction strategy:
- When changelogs exceed ~20 entries per section, summarize older entries and archive details to MongoDB
- Prune "Dismissed Contradictions" after 30 days
- Move older individual feedback entries to MongoDB after processing into "Recurring Themes"

**DO NOT implement compaction in the MVP. Just design the structure to make future compaction possible.**

### 4.3 Living Document Audit

Every 2 weeks (or on demand via a button), the system should:
1. Retrieve the last N session transcripts from MongoDB via RAG
2. Independently assess what the Current State section should say
3. Diff this against the actual current state
4. Surface discrepancies: "I re-checked the living document against recent sessions. Here are things that might have drifted: [list]"

This is advisory, not blocking. It catches cumulative small update errors.

### 4.4 Diff-and-Verify Update Strategy (IMPORTANT)

**DO NOT have the LLM rewrite the entire document on each update.** LLMs introduce subtle drift when rewriting — rephrasing existing content, moving things around, summarizing changelogs, or dropping sections. After 20 update cycles, the document will be mangled.

Instead, use a two-step LLM approach:

**Step 1 — Generate Diff (Sonnet):**
Prompt: "Here is the current startup_brain.md and the new information to incorporate. Output ONLY the specific changes needed, in this exact format:

```
SECTION: [exact section header]
ACTION: [UPDATE_POSITION | ADD_CHANGELOG | ADD_DECISION | ADD_FEEDBACK | ADD_DISMISSED]
CONTENT: [the exact markdown content to insert or replace]
```

Do NOT output unchanged sections. Do NOT rephrase existing content."

**Step 2 — Verify Diff (Sonnet, separate call):**
Prompt: "Here is the original document and the proposed changes. Verify:
1. Do the changes accurately reflect the new information?
2. Will applying these changes preserve all existing sections and content?
3. Is anything being lost, corrupted, or unnecessarily modified?
If all checks pass, respond 'VERIFIED'. Otherwise, describe the issue."

If verified → apply the changes (the LLM merges them in a final call, or the changes are structured enough to apply programmatically)
If not verified → retry Step 1 with the verification feedback

This is all LLM, no manual Python string manipulation, but dramatically more reliable than a single unchecked rewrite. The key insight: generating an edit is hard; verifying an edit is easy.

---

## 5. CONSISTENCY CHECKING ENGINE (HIGHEST PRIORITY FEATURE)

This is the #1 most important feature. It must be reliable and well-designed.

### 5.1 What It Catches

- **Strategic contradictions**: "Yesterday we said our target is small nuclear plants, today we're saying BP" — always flagged
- **Tactical contradictions**: "We said we'd use React but now we're discussing Vue" — only flagged if previously marked as strategically important
- **Revisited rejected ideas**: If the founders start discussing something they previously decided against, surface the prior decision and rationale

### 5.2 What It Does NOT Flag

- Minor tactical changes that don't affect the core business
- Contradictions in the "Dismissed Contradictions" section (prevents re-flagging)
- The system calibrates importance based on context of what matters to the startup

### 5.3 Multi-Pass Architecture

**Pass 1 — Wide Net (Claude Sonnet)**
- Input: startup_brain.md (full) + list of confirmed claims from new session
- Task: Find ALL potential contradictions. Over-flag rather than under-flag.
- Output: List of potential contradictions with references to specific sections
- Cost: Low (~15K tokens in, ~3K out)

**Pass 2 — Severity Filter (Claude Sonnet)**
- Input: Pass 1 results + startup_brain.md
- Task: Rank each contradiction (Critical / Notable / Minor). Filter out Minor. Remove already-dismissed items.
- Output: Filtered list with severity ratings and evidence summaries
- Cost: Low (~10K tokens in, ~2K out)

**Pass 3 — Deep Analysis (Claude Opus, ONLY IF Pass 2 found Critical contradictions)**
- Input: Critical contradictions + startup_brain.md + RAG-retrieved evidence from original sessions
- Task: Deep analysis with full context, evidence, and suggested resolution
- Output: Detailed contradiction report with citations
- Cost: Higher, but only triggered for genuinely important contradictions
- **If Pass 2 found no Critical contradictions, skip Pass 3 entirely**

### 5.4 RAG's Role in Consistency Checking

RAG is NOT used for finding contradictions (that's the living document's job). RAG IS used for:
- Retrieving evidence after a contradiction is detected ("here's exactly what you said on Feb 12")
- Answering "what did we say about X" queries
- Finding related discussions across sessions
- Note: RAG has a blind spot for contradictions — semantically dissimilar statements can occupy the same conceptual slot. This is why the living document, not RAG, is the consistency-checking surface.

### 5.5 Resolution Flow (INFORMATIONAL, NEVER BLOCKING)

```
System presents the contradiction with action buttons:
    "Heads up — this seems to contradict your earlier thinking:
    
    📌 Current position (from Feb 12): Your initial target is small nuclear plants
    because they have shorter procurement cycles.
    
    🆕 Today's session: You're discussing targeting BP.
    
    [Update to BP] [Keep current target] [Let me explain the change]"
    ↓
If "Update to BP" → System updates startup_brain.md immediately, logs the change
If "Keep current target" → No change, today's discussion noted but current position preserved
If "Let me explain" → Founder types explanation, recorded in the changelog
    ↓
All paths proceed without further friction.
```

**The system NEVER refuses to update. The default path must always be easy.**

### 5.6 Extraction Quality

Since inputs are clean post-session summaries (not raw brainstorming), the extraction task is simplified. The prompt should:
- Extract every statement that is a claim, decision, preference, or assertion
- Preserve specificity ("switch to usage-based at £0.05/unit" not "discussed pricing")
- Flag uncertainty where present ("leaning toward X" vs. "decided on X")
- Include who said what, if distinguishable

Since the founders only record conclusions (not brainstorming noise), the extraction prompt does NOT need to handle hypotheticals, devil's advocate positions, jokes, or tangents. This simplifies it significantly.

### 5.7 Trigger Modes

- **Automatic on ingestion**: Every time a new transcript is ingested, the multi-pass check runs
- **On-demand**: A button to run a full consistency audit (uses the living document audit from Section 4.3)
- **Proactive suggestions**: After ingestion, the system can ask clarifying questions

---

## 6. PUSHBACK SYSTEM

The system surfaces relevant context when the founders change direction. It is NEVER blocking.

### 6.1 When It Surfaces Context

- **Revisiting rejected ideas**: "Heads up — you considered usage-based pricing on Feb 20 and rejected it because VCs dislike unpredictable revenue. [Update anyway] [Let me explain what changed]"
- **Unsupported changes**: "This changes your target market. Your earlier research seemed comprehensive. [Update anyway] [Let me explain]"
- **Pattern from feedback**: "Five investors have now raised the same concern about your logos. [Show me the feedback] [Dismiss]"

### 6.2 How It Works

- **Informational, not blocking** — always provide "Update anyway" as a one-click option
- Always provides evidence (references to specific sessions and dates)
- The founder can override with zero explanation — system logs "overridden without explanation" and moves on
- If the founder chooses to explain, the explanation is recorded in the changelog
- Dismissed contradictions go into the "Dismissed Contradictions" section to prevent re-flagging

### 6.3 Correction Friction

If the system's conclusion is wrong:
- Type "no, our target market is actually X, update it" → system updates immediately, zero pushback
- The system asks zero clarifying questions for direct corrections
- Pushback/context-surfacing is for changes that contradict prior deliberate decisions — not for correcting AI errors

---

## 7. BOOK FRAMEWORK INTEGRATION

### 7.1 Books to Incorporate

- "Pitch Anything" by Oren Klaff (frame control, neurofinance-based pitching)
- Jan Haje Kamps' pitch guide (pitch structure, unit economics emphasis)
- Possibly 1-2 more (2-3 books total max)

### 7.2 How to Incorporate

- Ingest each book once: Claude reads and produces a "frameworks and principles" summary (~3-5K tokens per book)
- Store as reference documents included in context for pitch-related queries
- This is BETTER than RAG over the full book — founders want internalized frameworks, not passage retrieval
- Example: "Your pitch violates the frame control principle from Oren Klaff"

### 7.3 Storage

- Framework summaries stored as markdown files in the repo alongside startup_brain.md
- Also stored in MongoDB for retrieval
- Included in context specifically for pitch, investor, and strategy queries

---

## 8. FEEDBACK PATTERN DETECTION

### 8.1 Input Methods

- Post-meeting summaries recorded via Wispr Flow
- Pasted investor/customer emails with context
- Both quantitative ("5 of 8 investors mentioned X") and qualitative pattern matching

### 8.2 What It Should Detect

- Recurring themes across multiple conversations
- Contradictions between feedback and current strategy
- Feedback that aligns with or contradicts book frameworks
- Changes in feedback over time

### 8.3 Integration with Living Document

- Feedback Tracker section of startup_brain.md auto-updated with each new piece
- Themes tagged and counted in "Recurring Themes" subsection
- System proactively surfaces when a theme reaches 3+ sources

---

## 9. OUTPUT GENERATION

### 9.1 Types of Outputs

- Pitch talking points and bullet points
- Scenarios for pitching to different investor types
- Current business model summary
- Evolution narrative ("tell me how our pricing thinking has evolved")
- Strategic analysis ("is our business model defensible?")
- Feedback analysis ("was this VC's feedback noise or do they have a point?")
- Consistency reports

### 9.2 How Outputs Are Generated

- Always grounded in the accumulated knowledge base
- Use book frameworks for pitch-related materials
- Include proper attribution ("based on your Feb 12 session")
- Pitch generation and strategic analysis use Opus; other outputs use Sonnet

---

## 10. WHITEBOARD PROCESSING

### 10.1 Approach

- Use Claude's vision capabilities to extract content from whiteboard photos
- Cross-reference against the transcript (founders describe whiteboard content verbally)
- Show extraction for confirmation (same pattern as claim confirmation)
- Weight transcript more heavily than whiteboard extraction
- Store both raw image reference and extracted text in MongoDB

---

## 11. USER INTERFACE (STREAMLIT)

### 11.1 Why Streamlit

We evaluated alternatives:
- **Chainlit**: Purpose-built for chat, but parent company (LiteralAI) shut down May 2025. Now community-maintained with no guarantees and unresolved sidebar bugs. Too risky.
- **Gradio**: Designed for ML model demos (input → output), not stateful multi-turn conversations.
- **Streamlit**: Backed by Snowflake (public company), actively maintained, handles chat + dashboard sidebar. Its re-run model requires careful state management but is well-understood.

### 11.2 Streamlit-Specific Technical Guidance

**State Management:** Streamlit re-runs the entire script on every interaction.
- Use `st.session_state` for ALL stateful data: conversation history, current mode, pending contradictions, claim list during confirmation
- Never store state in module-level variables — they reset on each re-run

**Connection Pooling:**
```python
@st.cache_resource
def get_mongo_client():
    return MongoClient(os.environ["MONGODB_URI"])
```

**Multi-step Flows:** The ingestion pipeline has multiple steps (extraction → claim confirmation → consistency check → resolution). Model this as an explicit state machine:
- `st.session_state.mode` = "chat" | "ingesting" | "confirming_claims" | "checking_consistency" | "resolving_contradiction" | "done"
- Each mode renders different UI elements
- Transitions are triggered by user actions (button clicks)

**Progress Indicators:** Use `st.status` for multi-step operations:
```python
with st.status("Processing session...", expanded=True) as status:
    st.write("✅ Transcript received")
    st.write("⏳ Extracting claims...")
    # ... extraction happens ...
    st.write("✅ Found 7 claims")
    status.update(label="Awaiting confirmation", state="running")
```

**Streaming:** Use `st.chat_message` and `st.chat_input` for the chat interface. Stream LLM responses using the Anthropic streaming API.

**Secrets:** Use Streamlit's built-in secrets management (`st.secrets`) for API keys — integrates with Streamlit Community Cloud.

### 11.3 Main Components

**Chat Panel (Main Area)**
- Conversational interface for all interactions
- Input area that accepts text (transcript paste) and image upload (whiteboard photo)
- Shows extracted claims for confirmation with edit/remove/approve controls
- Shows consistency check results inline with action buttons
- Shows progress indicators during multi-step operations
- Handles all queries and output generation

**Sidebar Dashboard**
- Renders the Current State section of startup_brain.md as a structured overview
- Shows key sections: target market, business model, pricing, etc.
- Shows recent changes (last N changelog entries)
- Shows feedback themes with counts
- Shows cost tracking summary (current month spend)

**Controls**
- Button: "Ingest New Session" (triggers the ingestion flow)
- Button: "Run Full Consistency Audit" (triggers living document audit)
- Button: "Show Evolution of [Topic]"
- File upload for whiteboard photos

**Ingestion UI (claim confirmation)**
- When mode = "confirming_claims", show claims as an interactive checklist
- Each claim has: checkbox (checked by default), editable text field, remove button
- "Add a claim" text input at the bottom
- "Proceed with these claims" button
- "Cancel ingestion" button

### 11.4 Design Principles

- Ugly is fine, functional is mandatory
- Minimize clicks and setup
- Always show progress during multi-step operations — the user should never wonder if the system is stuck
- The chat interface should feel like talking to a knowledgeable co-founder with perfect memory
- No complex navigation or nested menus
- Everything accessible from the main screen
- Reminder in ingestion UI: "Paste your post-session summary (not raw brainstorming)"

---

## 12. EVOLUTION TRACKING

### 12.1 What to Track

- History of how key decisions evolved
- Not time-travel — no need to reconstruct past state
- But must answer: "Tell me the evolution of our business model" → "Initially X, pivoted because of customer feedback, now Y"

### 12.2 Implementation

- Changelog entries within each section of startup_brain.md
- Each entry: date, what changed, why, what it changed from
- Decision Log section provides full decision context
- Git history of startup_brain.md provides secondary audit trail

---

## 13. COST MANAGEMENT

### 13.1 Budget Structure

- $400/month hard maximum
- Realistic expected cost: $100-200/month
- API calls logged with cost tracking (model, tokens in/out, estimated cost)
- Monthly cost summary in the sidebar
- Alert if trending above $300/month

### 13.2 Sonnet vs. Opus Routing (CRITICAL FOR BUDGET)

**Always use Sonnet:**
- Transcript extraction and claim generation
- Session summarization
- Simple queries against the living document
- Consistency check Pass 1 (wide net) and Pass 2 (severity filter)
- Living document updates (diff and verify steps)
- Feedback pattern detection
- Whiteboard extraction
- Evolution narrative generation

**Only use Opus when:**
- Consistency check Pass 3 (ONLY if Pass 2 found Critical contradictions)
- Pitch material generation (where book framework integration matters)
- Strategic analysis queries ("is our business model defensible?")
- The user explicitly requests deep analysis

**Cost Estimation:**
- Daily ingestion (Sonnet: extraction + confirmation + 2-pass consistency + update): ~25K tokens total = ~$0.20/session
- 25 sessions/month = ~$5/month for ingestion
- Daily queries (5-10 Sonnet queries): ~$3-5/month
- Occasional Opus calls (maybe 10-15/month): ~$15-30/month
- **Total estimate: $25-40/month typical** — well within budget
- Even with heavy Opus usage, should stay under $150/month

### 13.3 Implementation

- Every API call goes through a wrapper that logs: timestamp, model, tokens_in, tokens_out, estimated_cost
- Store in a `cost_log` collection in MongoDB
- Simple aggregation for the sidebar: sum cost by day/week/month
- If monthly cost > $300, disable Opus for non-critical tasks (fall back to Sonnet)

---

## 14. IMPORTANT DESIGN PRINCIPLES

### 14.1 Friction Minimization (CRITICAL)

The #1 reason the founders would abandon this system is input friction. Every design decision minimizes it:
- Paste transcript, optionally add photo, confirm claims in 10 seconds → done
- No mandatory fields, no complex forms, no required tagging
- System infers as much as possible from context
- Corrections: type "no, it's actually X" → immediate update, zero pushback
- A small reminder in the ingestion UI: "Paste your post-session summary (not raw brainstorming)" to maintain input quality

### 14.2 LLM Maximalist

- Use AI for everything: extraction, organization, contradiction detection, pattern recognition, generation
- No manual organization, tagging, or curation
- Feel like talking to an intelligent system, not managing a database
- Proactively surface insights
- Even document updates use LLM (diff-and-verify), not manual Python manipulation

### 14.3 Provenance Tracking

Every piece of information traceable to its source:
- "This came from your session on Feb 12"
- "This was feedback from Investor X on Feb 15"
- "This contradicts what you said on Feb 10"

### 14.4 Evolving Intelligence

- Better pattern detection as more feedback accumulates
- Richer consistency checking as more decisions are logged
- Living document validated by periodic audit (Section 4.3)

---

## 15. MONGODB ATLAS SPECIFICS

### 15.1 Collections Design

- `sessions` — raw transcripts with full text and metadata (whole documents, for archival)
- `claims` — individual confirmed claims/decisions, one per document (auto-embedded by Voyage AI). Each links to source session via `session_id`.
- `whiteboard_extractions` — extracted content from whiteboard photos
- `feedback` — investor and customer feedback entries (also individual docs for embedding)
- `book_frameworks` — distilled framework summaries from reference books
- `living_document` — mirror of startup_brain.md (single document, updated on each change)
- `cost_log` — API call cost tracking entries

### 15.2 Metadata Schema

Each document in `sessions` and `feedback`:
- `created_at` (datetime)
- `source_type` (transcript | whiteboard | feedback | resource | book_framework)
- `participants` (list of names)
- `topic_tags` (auto-generated)
- `session_id` (links related docs from same session)
- `one_line_summary` (auto-generated)

Each document in `claims`:
- `claim_text` (the discrete claim — this is what gets auto-embedded)
- `session_id` (link to source session)
- `created_at` (datetime)
- `claim_type` (decision | claim | preference | assertion | question)
- `topic_tags` (auto-generated)
- `confidence` (definite | leaning | speculative)
- `who_said_it` (if distinguishable)
- `confirmed_by_user` (boolean — always true since claims go through confirmation step)

### 15.3 Vector Search Configuration

- MongoDB Atlas Vector Search with Voyage AI automated embedding
- Vector search index on `claim_text` field in `claims` collection
- Also on `feedback` collection for feedback retrieval
- Voyage 4 model series
- Return top 5 most relevant claims by default

### 15.4 Connection & Security

- MongoDB Atlas connection string via environment variable / Streamlit secrets
- Anthropic API key via environment variable / Streamlit secrets
- Basic security is fine — not sensitive IP

---

## 16. PROMPT ENGINEERING

### 16.1 Core Prompts to Design

1. **Extraction Prompt** (Sonnet): Takes a clean post-session summary + optional whiteboard extraction, outputs discrete claims/decisions, session summary, and topic tags. Since inputs are clean summaries, the prompt should be aggressive about extracting every conclusion as a self-contained statement.

2. **Consistency Check Pass 1 Prompt** (Sonnet): Takes startup_brain.md + confirmed claims, finds ALL potential contradictions (wide net, no filtering)

3. **Consistency Check Pass 2 Prompt** (Sonnet): Takes Pass 1 results + startup_brain.md, ranks by severity (Critical/Notable/Minor), filters Minor, removes dismissed items

4. **Consistency Check Pass 3 Prompt** (Opus): Takes Critical contradictions + startup_brain.md + RAG evidence, provides deep analysis with citations

5. **Diff Generation Prompt** (Sonnet): Takes startup_brain.md + new information, outputs ONLY the structured changes needed (section, action, content). Must NOT rephrase existing content.

6. **Diff Verification Prompt** (Sonnet): Takes original document + proposed changes, verifies nothing is lost or corrupted. Outputs VERIFIED or describes issues.

7. **Pushback/Context Prompt** (Sonnet): Takes proposed change + relevant Decision Log entries, generates informational context (not blocking)

8. **Evolution Narrative Prompt** (Sonnet): Takes changelog entries for a topic, generates coherent narrative

9. **Feedback Pattern Prompt** (Sonnet): Takes Feedback Tracker section + new feedback, identifies recurring themes

10. **Pitch Generation Prompt** (Opus): Takes startup_brain.md + book frameworks + request, generates pitch materials

11. **Whiteboard Extraction Prompt** (Sonnet): Takes whiteboard photo + transcript context, extracts structured content

12. **Audit Prompt** (Sonnet): Takes last N transcripts + current startup_brain.md, assesses accuracy, flags discrepancies

### 16.2 Prompt Design Principles

- Always include full startup_brain.md in consistency-related prompts
- Use XML tags for structured input/output
- Include few-shot examples for extraction and consistency checking
- Consistency prompts include severity calibration guidance
- All prompts cite specific sessions/dates as evidence
- The Diff Generation Prompt is the most important prompt to get right — invest time in examples showing correct minimal diffs vs. incorrect rewrites

---

## 17. TESTING STRATEGY

### 17.1 Consistency Engine Tests

- Strategic contradiction (target market change) — caught at Pass 1, rated Critical at Pass 2
- Tactical contradiction that should be flagged (marked important) — caught
- Tactical contradiction that should NOT be flagged (minor detail) — filtered at Pass 2
- Revisiting a previously rejected idea — surfaces decision log context
- Genuine evolution (natural pivot with reasoning) — NOT flagged
- Previously dismissed contradiction — NOT re-flagged

### 17.2 Extraction and Confirmation Tests

- Feed transcript with 5 decisions → verify all 5 extracted
- Feed transcript with uncertainty → verify extraction preserves uncertainty
- Test claim editing, removal, and addition in confirmation step
- Verify only confirmed claims enter MongoDB and consistency engine

### 17.3 Living Document Update Tests

- Verify diff-and-verify produces minimal changes (doesn't rephrase existing content)
- Verify changelog entries are added correctly
- Verify verification step catches a deliberately bad diff
- Verify git commit is created after each update

### 17.4 End-to-End Tests

- Ingest 5 simulated transcripts with contradiction between sessions 2 and 4
- Verify system catches it at ingestion of session 4
- Verify evolution narrative generation
- Verify feedback pattern detection after 3 similar entries
- Verify "Update anyway" flow properly updates living document
- Verify living document audit catches simulated drift

---

## 18. BUILD PRIORITIES (MVP FIRST)

### Phase 1 — Core (Days 1-2)
1. GitHub repo setup + Streamlit Community Cloud deployment (get the empty app live first)
2. MongoDB Atlas setup with Voyage AI automated embedding + collections + vector search index
3. startup_brain.md template
4. Ingestion pipeline with extraction + claim confirmation step
5. Diff-and-verify living document update logic
6. Basic Streamlit UI with chat + sidebar + progress indicators

### Phase 2 — Consistency Engine (Days 3-4)
7. Multi-pass consistency checking (Passes 1-2 Sonnet, Pass 3 Opus)
8. Contradiction resolution UI with action buttons
9. Decision log population
10. Dismissed contradictions tracking

### Phase 3 — Essential Additions (Days 5-6)
11. Pushback/context surfacing system
12. Whiteboard photo processing
13. Feedback ingestion and pattern detection
14. Cost tracking + sidebar integration
15. Book framework integration

### Phase 4 — Robustness (Day 7+)
16. Living document audit mechanism
17. Evolution narrative generation
18. Pitch material generation
19. Testing suite with simulated transcripts
20. Daily MongoDB backup script

---

## 19. FILES AND DIRECTORY STRUCTURE

```
startup-brain/
├── .streamlit/
│   └── secrets.toml          # Streamlit secrets (gitignored, configured in Cloud)
├── app/
│   ├── main.py               # Streamlit entry point
│   ├── pages/                 # Streamlit multi-page (if needed)
│   ├── components/
│   │   ├── chat.py            # Chat interface
│   │   ├── sidebar.py         # Dashboard sidebar
│   │   ├── claim_editor.py    # Claim confirmation UI
│   │   └── progress.py        # Progress indicator wrapper
│   └── state.py               # Session state management / state machine
├── services/
│   ├── mongo_client.py        # MongoDB connection + CRUD operations
│   ├── claude_client.py       # Claude API wrapper with cost-aware routing
│   ├── ingestion.py           # Ingestion pipeline orchestration
│   ├── consistency.py         # Multi-pass consistency engine
│   ├── document_updater.py    # Diff-and-verify update logic
│   ├── feedback.py            # Feedback pattern detection
│   └── cost_tracker.py        # API cost logging and alerts
├── prompts/
│   ├── extraction.md          # Extraction prompt
│   ├── consistency_pass1.md   # Consistency Pass 1 prompt
│   ├── consistency_pass2.md   # Consistency Pass 2 prompt
│   ├── consistency_pass3.md   # Consistency Pass 3 prompt
│   ├── diff_generate.md       # Diff generation prompt
│   ├── diff_verify.md         # Diff verification prompt
│   ├── pushback.md            # Context surfacing prompt
│   ├── evolution.md           # Evolution narrative prompt
│   ├── feedback_pattern.md    # Feedback pattern prompt
│   ├── pitch_generation.md    # Pitch generation prompt
│   ├── whiteboard.md          # Whiteboard extraction prompt
│   └── audit.md               # Living document audit prompt
├── documents/
│   ├── startup_brain.md       # THE living document (git-tracked)
│   ├── framework_pitch_anything.md    # Book framework summary
│   └── framework_kamps_pitch.md       # Book framework summary
├── tests/
│   ├── test_transcripts/      # Simulated transcripts for testing
│   ├── test_consistency.py    # Consistency engine test scenarios
│   ├── test_extraction.py     # Extraction quality tests
│   └── test_update.py         # Diff-and-verify tests
├── scripts/
│   ├── backup_mongodb.py      # Daily MongoDB export to JSON
│   └── bootstrap.py           # Initial setup: create collections, indexes, etc.
├── .env.example               # Template for environment variables
├── .gitignore
├── requirements.txt           # Python dependencies
└── README.md                  # Setup and usage instructions
```

---

## 20. ADDITIONAL CONTEXT

### 20.1 The Founders' Mental Model

They think of this as a "mind map that lives in the backend" — a dynamic, evolving representation of their startup's knowledge that they can query conversationally. It's NOT a filing cabinet. It's NOT a wiki. It's a knowledgeable co-founder with perfect memory.

### 20.2 What "LLM Maximalist" Means

- Don't build features requiring manual curation if AI can do it
- Don't build complex UIs when a chat interface works
- Don't build taxonomies when embeddings and LLM reasoning handle organization
- DO use AI for everything: extraction, organization, contradiction detection, pattern recognition, generation
- DO make the system feel intelligent and proactive

### 20.3 What They Explicitly Don't Want

- Anything that feels like Notion, a wiki, or a corporate intranet
- Heavy setup or onboarding
- Manual tagging or categorization
- Complex navigation or nested menus
- A system that fights them when they want to make changes
- Hours of configuration before it's useful

### 20.4 The Compliance Domain Context

The startup works in compliance for nuclear, oil & gas, and power generation. They deal with PDFs and technical drawings. Relevant for:
- Types of discussions and terminology in transcripts
- Investor profile (likely deep-tech / industrial)
- Regulatory complexity of their market

### 20.5 Bootstrapping

The founders already have 5-7 transcripts from initial sessions and will have investor/customer feedback starting immediately. The system will be useful from day 1:
- Ingesting existing transcripts builds the living document quickly
- The consistency engine returns "no inconsistencies" when there are none, which is valuable confirmation
- Feedback pattern detection activates naturally as feedback accumulates

---

## 21. BACKUP AND VERSION CONTROL

### 21.1 Git for Everything

- The entire project is a GitHub repository
- startup_brain.md is tracked in git — every update creates a commit with a message like "Updated: [sections changed] — triggered by [session/feedback/manual]"
- This gives free version history
- The founders can `git log documents/startup_brain.md` to see the full evolution

### 21.2 MongoDB Export

- A script (`scripts/backup_mongodb.py`) that exports all MongoDB collections to local JSON files
- Can be run manually or as a daily cron job
- Keep last 7 daily backups
- Protects against Atlas outages or accidental data loss

### 21.3 What Happens If Atlas Goes Down

- System degrades gracefully: chat and living document queries still work (startup_brain.md is local/in-repo)
- RAG retrieval and new ingestion are temporarily unavailable
- Display: "MongoDB is temporarily unavailable. You can still query the current state, but historical search and new ingestion are paused."

---

## 22. KNOWN RISKS AND FAILURE HANDLING

### 22.1 Extraction Hallucination
**Risk:** LLM generates a claim not in the transcript.
**Mitigation:** Clean input convention (summaries only). Claim confirmation step catches hallucinations before they enter the system.
**Recovery:** If a bad claim slips through, founder can delete it from MongoDB via a chat command ("delete claim [id]").

### 22.2 Consistency Engine False Positives
**Risk:** System flags non-contradictions, annoying founders.
**Mitigation:** Two-pass design with severity filtering. "Dismissed Contradictions" prevents re-flagging.
**Recovery:** "Dismiss" button on every flagged item. If persistent, founders edit the consistency prompts (stored as separate files in `/prompts`).

### 22.3 Living Document Drift
**Risk:** Cumulative small update errors compound over time.
**Mitigation:** Diff-and-verify strategy (Section 4.4). Periodic audit (Section 4.3). Git history for comparison.
**Recovery:** Founders can manually edit startup_brain.md — it's just a markdown file in the repo.

### 22.4 Sonnet Insufficient for Consistency
**Risk:** Sonnet misses contradictions Opus would catch.
**Mitigation:** Over-extraction strategy and wide-net Pass 1. Periodic audit as catch-all.
**Recovery:** Switch Pass 2 to Opus (one config change) if needed. Architecture supports this without code changes.

### 22.5 MongoDB Atlas Outage
**Risk:** Atlas unavailable, breaking ingestion and RAG.
**Mitigation:** Living document is in the git repo. Daily JSON backups.
**Recovery:** Degraded mode message. Queue inputs locally and process when Atlas returns.

### 22.6 Runaway API Costs
**Risk:** Bug or unusual usage spikes costs.
**Mitigation:** Cost-tracking wrapper on every API call. Alert at $300. Automatic Opus→Sonnet fallback.
**Recovery:** All calls user-triggered (no background processes). Costs stop when system isn't used.

### 22.7 Prompt Quality Degradation
**Risk:** Prompts that worked initially degrade as living document grows.
**Mitigation:** Prompts stored as separate files, easy to iterate. Audit serves as quality canary.
**Recovery:** Edit prompts directly, see immediate results, no redeployment needed (Streamlit reloads).

### 22.8 Streamlit Community Cloud Outage
**Risk:** Hosting goes down.
**Mitigation:** All code is in GitHub. Can run locally with `streamlit run app/main.py` in under 30 seconds.
**Recovery:** Run locally until Cloud recovers. No data loss (MongoDB Atlas + git repo are independent).

---

## 23. DEPENDENCIES

```
# requirements.txt
streamlit>=1.30.0
pymongo[srv]>=4.6.0
anthropic>=0.40.0
Pillow>=10.0.0        # for whiteboard image handling
python-dotenv>=1.0.0  # for local .env loading
```

Minimal dependencies. No LangChain, no LlamaIndex, no heavy frameworks. Direct API calls to Claude and MongoDB.

---

## 24. DEPLOYMENT

### 24.1 Why Streamlit Community Cloud

- **Free** — no hosting costs
- **Zero DevOps** — deploys directly from GitHub repo, auto-deploys on push
- **Built-in secrets management** — API keys configured in the Streamlit Cloud dashboard, accessed via `st.secrets`
- **Always-on** — both founders can access from any device, any location
- **HTTPS** — handled automatically
- **Perfect fit** — designed specifically for Streamlit apps, maintained by the same team (Snowflake)

### 24.2 Why NOT Vercel / Supabase

- **Vercel** is designed for Next.js, serverless functions, and static sites. Streamlit is a long-running Python process — it won't work on Vercel.
- **Supabase** is a PostgreSQL backend. The project already uses MongoDB Atlas. Adding Supabase would mean two databases for no reason.
- Both are good tools, just wrong for this specific stack.

### 24.3 Deployment Steps

1. Create a GitHub repository (private)
2. Push all code
3. Go to share.streamlit.io, connect the GitHub repo
4. Set the main file path: `app/main.py`
5. Add secrets in the Streamlit Cloud dashboard:
   ```
   MONGODB_URI = "mongodb+srv://..."
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
6. Click Deploy
7. Share the URL with co-founder

That's it. Total deployment time: 5 minutes.

### 24.4 Development Workflow

```
Local development:
    streamlit run app/main.py     # runs locally at localhost:8501
    
Deploy:
    git add . && git commit -m "..." && git push
    # Streamlit Community Cloud auto-deploys within ~1 minute
```

### 24.5 MongoDB Atlas Setup

1. Create free Atlas account at mongodb.com
2. Create a free M0 cluster
3. Create a database user
4. Whitelist IP addresses (allow access from anywhere for Streamlit Cloud: 0.0.0.0/0)
5. Get connection string
6. Run `scripts/bootstrap.py` to create collections and vector search indexes

### 24.6 Anthropic API Setup

1. Create account at console.anthropic.com
2. Generate API key
3. Add billing (or apply for startup credits)
4. Add key to Streamlit Cloud secrets

---

## 25. FORMULATE THE PLAN

Now, Claude Code, produce a comprehensive multi-agent build plan that covers:

1. **Architecture diagram** (text-based) showing all components and data flows
2. **Complete file/directory structure** with every file that needs to be created (reference Section 19 but refine as needed)
3. **Implementation order** — what gets built first, second, third, with dependencies mapped (reference Section 18)
4. **For each major component**: what it does, what APIs it calls, what prompts it uses, what data it reads/writes
5. **All LLM prompts** — full drafts for each prompt listed in Section 16, with few-shot examples where appropriate
6. **MongoDB schema design** — collections, indexes, vector search configuration, including the `claims` collection
7. **Streamlit layout** — wireframe description of each screen/panel, including state machine design and the claim confirmation UI
8. **Testing plan** — specific test scenarios with expected outcomes (reference Section 17)
9. **Cost model** — estimated API calls per interaction type, projected monthly cost, with Sonnet/Opus routing
10. **Risk mitigation** — reference Section 22 and add any additional risks
11. **Deployment checklist** — step-by-step for getting the app live on Streamlit Community Cloud (reference Section 24)
12. **Multi-agent task breakdown** — how to split the work across agents in Claude Code multi-agent mode. Suggested split:
    - **Agent 1: Infrastructure** — MongoDB Atlas setup, bootstrap script, GitHub repo structure, Streamlit Cloud config, secrets management
    - **Agent 2: Core Services** — mongo_client.py, claude_client.py with cost routing, cost_tracker.py, document_updater.py (diff-and-verify)
    - **Agent 3: Prompt Engineering** — All 12 prompts in the /prompts directory, with few-shot examples and testing
    - **Agent 4: Ingestion Pipeline** — ingestion.py, extraction flow, claim confirmation flow, consistency engine (multi-pass)
    - **Agent 5: Streamlit UI** — main.py, all components, state machine, sidebar, progress indicators, claim editor
    - **Agent 6: Testing & Polish** — test suite, simulated transcripts, end-to-end validation, backup scripts

Take your time. Be thorough. This plan will be the blueprint for the entire build.
