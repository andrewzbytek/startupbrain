# Consistency Check — Pass 1: Wide Net (Claude Sonnet)

You are performing the first pass of a multi-pass consistency check. Your job is to find ALL potential contradictions between new session claims and the existing startup knowledge base. **Over-flag rather than under-flag.** It is better to surface a false positive than to miss a real contradiction.

## Your Task

Compare each new claim against the full living document. Identify any new claim that conflicts with, undermines, or is in tension with existing documented positions. Also flag if any new claim appears to revisit a previously rejected idea.

## Input Format

<consistency_input>
  <living_document>{{startup_brain_md_full_text}}</living_document>
  <new_claims>{{confirmed_claims_xml}}</new_claims>
</consistency_input>

## Rules

1. **Wide net** — flag anything suspicious. Pass 2 will filter.
2. **Reference specific sections** — cite the exact section header and relevant text from the living document.
3. **Quote both sides** — quote the new claim AND the existing position it potentially contradicts.
4. **Include dismissed contradictions** in your input check, but do NOT flag them — they are already resolved.
5. **Flag revisited rejections** — if the new claim appears to revisit something in the Decision Log marked as rejected.
6. **Do not evaluate severity** — that is Pass 2's job.

## Output Format

Respond ONLY with valid XML in this exact structure:

<pass1_output>
  <potential_contradictions>
    <contradiction>
      <id>1</id>
      <new_claim>Exact text of the new claim that may contradict</new_claim>
      <existing_position>Exact quote from startup_brain.md</existing_position>
      <existing_section>The section header where the existing position appears</existing_section>
      <tension_description>One sentence explaining why these are in tension</tension_description>
      <is_revisited_rejection>true|false</is_revisited_rejection>
    </contradiction>
  </potential_contradictions>
  <total_found>N</total_found>
</pass1_output>

If no potential contradictions are found, output:

<pass1_output>
  <potential_contradictions/>
  <total_found>0</total_found>
</pass1_output>

---

## Few-Shot Example

### Input

<consistency_input>
  <living_document>
# Startup Brain — NuclearCompliance.ai
Last updated: 2026-02-14

## Current State

### Target Market / Initial Customer
**Current position:** Small nuclear power plants in the UK, specifically operators with fewer than 3 reactors. Chosen because shorter procurement cycles (6-12 months vs. 18-24 months for majors).
**Changelog:**
- 2026-02-01: Initial position set. Source: Session 1

### Business Model / Revenue Model
**Current position:** Per-facility annual SaaS license.

### Pricing
**Current position:** £50K per facility per year for initial customers. Plan to raise pricing after first 3 customers.

## Decision Log

### 2026-02-10 — Rejected Usage-Based Pricing
**Decision:** Rejected usage-based pricing in favour of annual per-facility license.
**Why rejected:** VCs dislike variable MRR. Harder to forecast. Annual contracts give predictable revenue.

## Dismissed Contradictions
- 2026-02-12: Claim that BP would be a faster sale — Dismissed because: small plants have shorter procurement.
  </living_document>
  <new_claims>
    <claim>
      <claim_text>We should target BP and Shell as our first customers because they have larger budgets.</claim_text>
      <claim_type>preference</claim_type>
      <confidence>leaning</confidence>
    </claim>
    <claim>
      <claim_text>We are considering usage-based pricing at £0.05 per document processed.</claim_text>
      <claim_type>preference</claim_type>
      <confidence>leaning</confidence>
    </claim>
    <claim>
      <claim_text>Our MVP will focus on PDF compliance document management.</claim_text>
      <claim_type>decision</claim_type>
      <confidence>definite</confidence>
    </claim>
  </new_claims>
</consistency_input>

### Expected Output

<pass1_output>
  <potential_contradictions>
    <contradiction>
      <id>1</id>
      <new_claim>We should target BP and Shell as our first customers because they have larger budgets.</new_claim>
      <existing_position>Small nuclear power plants in the UK, specifically operators with fewer than 3 reactors. Chosen because shorter procurement cycles (6-12 months vs. 18-24 months for majors).</existing_position>
      <existing_section>Current State → Target Market / Initial Customer</existing_section>
      <tension_description>New claim proposes BP/Shell (major operators) as initial targets, directly contradicting the documented decision to focus on small plants due to shorter procurement cycles.</tension_description>
      <is_revisited_rejection>false</is_revisited_rejection>
    </contradiction>
    <contradiction>
      <id>2</id>
      <new_claim>We are considering usage-based pricing at £0.05 per document processed.</new_claim>
      <existing_position>Rejected usage-based pricing in favour of annual per-facility license. VCs dislike variable MRR.</existing_position>
      <existing_section>Decision Log → 2026-02-10 — Rejected Usage-Based Pricing</existing_section>
      <tension_description>New claim revisits usage-based pricing, which was explicitly rejected in the Decision Log with documented rationale.</tension_description>
      <is_revisited_rejection>true</is_revisited_rejection>
    </contradiction>
  </potential_contradictions>
  <total_found>2</total_found>
</pass1_output>
