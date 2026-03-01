# Consistency Check — Pass 2: Severity Filter (Claude Sonnet)

You are performing the second pass of a multi-pass consistency check. You receive the potential contradictions identified in Pass 1 and your job is to rate each by severity, filter out minor items, and remove any that have already been dismissed.

## Your Task

For each potential contradiction from Pass 1:
1. Assign a severity rating: Critical, Notable, or Minor
2. Remove items rated Minor
3. Remove items that appear in the Dismissed Contradictions section
4. Provide a brief evidence summary for each retained item

## Input Format

<pass2_input>
  <session_type>{{session_type}}</session_type>
  <living_document>{{startup_brain_md_full_text}}</living_document>
  <pass1_results>{{pass1_output_xml}}</pass1_results>
</pass2_input>

## Severity Calibration

**Critical** — Strategic direction change. If acted on, the startup would need to significantly alter its core strategy, target market, value proposition, or business model. These must always be surfaced.
- Examples: switching target market, changing core business model, pivoting away from a validated decision, significant pricing model change

**Notable** — Important tactical change. Affects specific implementation decisions but not core strategy. Should be surfaced but does not require Opus-level analysis.
- Examples: changing a specific pricing number, adjusting timeline targets, modifying technical approach for a feature, reconsidering a hire

**Minor** — Trivial detail that does not affect strategy or execution in a meaningful way. Filter these out.
- Examples: word choice differences, minor process clarifications, administrative details, specifics that are obviously being refined rather than reversed

**Session type affects severity:** A claim from a formal decision session or customer interview that contradicts the living document is more likely Critical. A claim from internal notes or brainstorming that explores an alternative is more likely Notable or Minor — it may represent thinking-out-loud rather than a real strategic shift.

## Dismissed Contradictions Rule

If a potential contradiction from Pass 1 corresponds to an entry in the Dismissed Contradictions section of the living document, remove it from the output entirely. Do not surface already-dismissed items.

## Output Format

Respond ONLY with valid XML in this exact structure:

<pass2_output>
  <retained_contradictions>
    <contradiction>
      <id>{{original_pass1_id}}</id>
      <severity>Critical|Notable</severity>
      <new_claim>{{exact claim text}}</new_claim>
      <existing_position>{{existing position quote}}</existing_position>
      <existing_section>{{section header}}</existing_section>
      <evidence_summary>2-3 sentences summarizing why this matters and what evidence supports each side.</evidence_summary>
      <is_revisited_rejection>true|false</is_revisited_rejection>
    </contradiction>
  </retained_contradictions>
  <filtered_out>
    <item>
      <id>{{pass1_id}}</id>
      <reason>Minor|Dismissed</reason>
    </item>
  </filtered_out>
  <has_critical>true|false</has_critical>
  <total_retained>N</total_retained>
</pass2_output>

If all contradictions were filtered out:

<pass2_output>
  <retained_contradictions/>
  <filtered_out>
    <item><id>1</id><reason>Minor</reason></item>
  </filtered_out>
  <has_critical>false</has_critical>
  <total_retained>0</total_retained>
</pass2_output>
