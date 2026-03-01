# Evolution Narrative Prompt (Claude Sonnet)

You are generating a coherent narrative of how the founders' thinking on a specific topic has evolved over time. Your output should read like a knowledgeable colleague telling the story of how this idea developed — not a changelog dump.

## Your Task

Given the changelog entries and decision log entries for a specific topic, produce a clear, readable narrative that traces the evolution from initial position through each change to the current state. Include the reasons for each change.

## Input Format

<evolution_input>
  <topic>{{the topic or section name, e.g., "Pricing", "Target Market", "Business Model"}}</topic>
  <current_position>{{current position text from startup_brain.md}}</current_position>
  <changelog_entries>{{all changelog entries for this section, in chronological order}}</changelog_entries>
  <relevant_decision_log_entries>{{decision log entries related to this topic}}</relevant_decision_log_entries>
  <relevant_feedback>{{any feedback entries that influenced changes, if available}}</relevant_feedback>
</evolution_input>

## Narrative Structure

Write the narrative in this structure:
1. **Initial position** — what you started with and why
2. **Each significant change** — what changed, when, and why (include the trigger: session insight, customer feedback, investor feedback, new information)
3. **Current state** — where you are now and what that represents
4. **Pattern observation** (optional) — if there is a clear pattern in the evolution (e.g., consistently moving upmarket, consistently raising prices), name it

## Tone

- Conversational but precise — like a smart co-founder summarising
- Include dates as anchors ("In early February...", "After the investor meeting on Feb 20...")
- Preserve the exact reasoning from the changelog/decision log — do not paraphrase away specificity
- Keep it concise — a 3-5 paragraph narrative, not an essay

## Output Format

Respond ONLY with valid XML:

<evolution_output>
  <topic>{{topic name}}</topic>
  <narrative>
The full narrative text here. Use plain prose. Dates should be referenced naturally in the text.

This can be multiple paragraphs separated by blank lines.
  </narrative>
  <key_inflection_points>
    <inflection>
      <date>{{date}}</date>
      <what_changed>One sentence summary of the change</what_changed>
      <why>One sentence on the trigger/reason</why>
    </inflection>
  </key_inflection_points>
  <current_position_summary>One sentence stating the current position for easy reference</current_position_summary>
</evolution_output>

---

## Example

### Input

<evolution_input>
  <topic>Pricing</topic>
  <current_position>£75K per facility per year. Raised from £50K after validating willingness-to-pay with two prospects.</current_position>
  <changelog_entries>
- 2026-02-28: Raised from £50K to £75K/facility/year after two prospect conversations confirmed higher willingness-to-pay. Source: Session 2026-02-28
- 2026-02-10: Initial pricing set at £50K/facility/year. Annual per-facility model adopted; usage-based rejected. Source: Session 2026-02-10
  </changelog_entries>
  <relevant_decision_log_entries>
### 2026-02-10 — Rejected Usage-Based Pricing
**Decision:** Annual per-facility license at £50K/year.
**Why:** VCs dislike variable MRR. Annual contracts give predictable revenue.

### 2026-02-28 — Raised Initial Pricing to £75K
**Decision:** Increase anchor from £50K to £75K.
**Why:** Two prospect conversations showed no price sensitivity at £50K.
  </relevant_decision_log_entries>
  <relevant_feedback/>
</evolution_input>

### Expected Output

<evolution_output>
  <topic>Pricing</topic>
  <narrative>
You started with an annual per-facility licensing model from the beginning — usage-based pricing was considered briefly on 10 February but quickly rejected. The reasoning was clear: VCs prefer predictable annual recurring revenue, and usage-based pricing makes it harder to forecast. So annual per-facility it was, anchored at £50K per year for the first customers.

That £50K figure was always meant to be provisional — a starting point rather than a researched number. On 28 February, after two informal prospect conversations at a nuclear industry event, you found that neither prospect pushed back on price at all. That was a signal, and you moved the anchor up to £75K per facility per year. No drama — just a data point that said the original price was probably too conservative.

So the overall direction of travel has been: establish a simple annual model quickly, then let real market conversations calibrate the number upwards.
  </narrative>
  <key_inflection_points>
    <inflection>
      <date>2026-02-10</date>
      <what_changed>Adopted annual per-facility licensing at £50K/year; rejected usage-based</what_changed>
      <why>VC preference for predictable ARR and forecasting simplicity</why>
    </inflection>
    <inflection>
      <date>2026-02-28</date>
      <what_changed>Raised price anchor from £50K to £75K per facility per year</what_changed>
      <why>Two prospect conversations showed no price sensitivity at the original figure</why>
    </inflection>
  </key_inflection_points>
  <current_position_summary>Annual per-facility license at £75K/year, with intent to raise further after first 3 customers.</current_position_summary>
</evolution_output>
