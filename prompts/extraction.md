# Extraction Prompt (Claude Sonnet)

You are extracting structured knowledge from a clean post-session summary recorded by startup co-founders. This is NOT raw brainstorming — it is a deliberate, post-discussion recording of conclusions. Treat every statement as an intentional claim or decision.

## Your Task

Extract every conclusion, decision, preference, and assertion as a discrete, self-contained claim. Preserve exact specificity. Generate a session summary and topic tags.

## Input Format

<session_input>
<participants>{{participants}}</participants>
<topic_hint>{{topic_hint}}</topic_hint>
<transcript>{{transcript}}</transcript>
<whiteboard_extraction>{{whiteboard_extraction}}</whiteboard_extraction>
</session_input>

## Extraction Rules

1. **Extract EVERY conclusion** — if it was said, it was meant. Do not filter.
2. **Preserve specificity** — "switch to usage-based at £0.05/unit" not "discussed pricing"
3. **Flag uncertainty** — use `confidence: leaning` for "we're thinking about X" and `confidence: definite` for "we decided X"
4. **Self-contained statements** — each claim must make sense without context from other claims
5. **Include who said it** if the transcript makes it distinguishable (otherwise leave blank)
6. **Claim types:**
   - `decision` — a firm choice made ("We will use MongoDB Atlas")
   - `claim` — a factual statement about the world ("Nuclear plants have 18-month procurement cycles")
   - `preference` — a directional lean not yet decided ("We prefer direct sales over channel")
   - `assertion` — a belief about their startup ("Our moat is regulatory domain expertise")
   - `question` — something they explicitly flagged as unresolved ("How do we handle multi-site licenses?")

## Output Format

Respond ONLY with valid XML in this exact structure:

<extraction_output>
  <session_summary>A 2-3 sentence summary of what this session was about and its main conclusions.</session_summary>
  <topic_tags>
    <tag>tag1</tag>
    <tag>tag2</tag>
  </topic_tags>
  <claims>
    <claim>
      <claim_text>The exact, self-contained claim statement.</claim_text>
      <claim_type>decision|claim|preference|assertion|question</claim_type>
      <confidence>definite|leaning|speculative</confidence>
      <who_said_it>Name or blank if not distinguishable</who_said_it>
      <topic_tags>
        <tag>tag1</tag>
      </topic_tags>
    </claim>
  </claims>
</extraction_output>

---

## Few-Shot Example

### Input

<session_input>
<participants>Alex, Jordan</participants>
<topic_hint>Pricing and go-to-market</topic_hint>
<transcript>
So we talked through the pricing model again. We're going to go with per-facility annual licensing, not usage-based. Jordan pushed back on usage-based because it's harder to forecast revenue and VCs hate variable MRR. We're anchoring at £50K per facility per year for the first customer, with the expectation we'll raise it as we prove value. Small nuclear plants are still the primary target — BP-scale enterprises are a phase two thing, not now. We also decided the first hire needs to be a nuclear domain expert, not a developer. We can build, they can't open doors. Aiming to close the first customer within six months of launch. Still not sure whether to go direct or through a channel partner in the nuclear space — that's unresolved.
</transcript>
<whiteboard_extraction>Whiteboard showed a 2x2 grid comparing direct vs. channel sales against speed and margin. Direct was marked with a question mark. Channel showed "Nuclear Safety Associates?" written next to it.</whiteboard_extraction>
</session_input>

### Expected Output

<extraction_output>
  <session_summary>The founders finalized their pricing model as per-facility annual licensing at £50K/year, confirmed small nuclear plants as the primary target (not enterprise), and decided their first hire must be a nuclear domain expert. Channel vs. direct sales remains unresolved.</session_summary>
  <topic_tags>
    <tag>pricing</tag>
    <tag>go-to-market</tag>
    <tag>hiring</tag>
    <tag>target-market</tag>
  </topic_tags>
  <claims>
    <claim>
      <claim_text>Pricing model is per-facility annual licensing, not usage-based.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>pricing</tag><tag>business-model</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Usage-based pricing was rejected because it is harder to forecast revenue and VCs dislike variable MRR.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
      <who_said_it>Jordan</who_said_it>
      <topic_tags><tag>pricing</tag><tag>fundraising</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Initial pricing anchor is £50K per facility per year for the first customer, with expectation to raise it as value is proven.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>pricing</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Primary target market is small nuclear plants. BP-scale enterprises are a phase two target, not the immediate focus.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>target-market</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>First hire must be a nuclear domain expert, not a developer, because domain access is the scarcer resource.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>hiring</tag><tag>strategy</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Target is to close the first customer within six months of launch.</claim_text>
      <claim_type>assertion</claim_type>
      <confidence>definite</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>go-to-market</tag><tag>timeline</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Whether to sell direct or through a channel partner in the nuclear space is unresolved.</claim_text>
      <claim_type>question</claim_type>
      <confidence>speculative</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>go-to-market</tag><tag>sales</tag></topic_tags>
    </claim>
  </claims>
</extraction_output>
