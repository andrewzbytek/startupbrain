# Consistency Check — Pass 3: Deep Analysis (Claude Opus)

**IMPORTANT: This prompt is only called when Pass 2 has identified Critical contradictions. It uses Claude Opus and carries higher cost. Do not invoke unnecessarily.**

You are performing the third and final pass of the consistency check. You receive the Critical contradictions identified in Pass 2, the full living document, and RAG-retrieved evidence from the original sessions. Your job is to provide deep, authoritative analysis with full citations and suggested resolution paths.

## Your Task

For each Critical contradiction:
1. Analyse both positions fully with all available evidence
2. Identify what may have changed in the founders' thinking
3. Assess whether this represents a genuine strategic pivot or a momentary exploration
4. Suggest concrete resolution options
5. Cite specific sessions, dates, and quotes as evidence

## Input Format

<pass3_input>
  <living_document>{{startup_brain_md_full_text}}</living_document>
  <critical_contradictions>{{pass2_retained_critical_xml}}</critical_contradictions>
  <rag_evidence>
    <evidence_item>
      <source_date>{{date}}</source_date>
      <source_type>session|feedback</source_type>
      <relevant_excerpt>{{retrieved_text}}</relevant_excerpt>
    </evidence_item>
  </rag_evidence>
</pass3_input>

## Analysis Framework

For each Critical contradiction, consider:
- **What was the original decision?** Who was involved, what alternatives were considered, what rationale was given?
- **What is the new claim?** Is it a full reversal, a refinement, or an expansion?
- **What external context might explain the change?** New feedback received, new market information, new competitor information?
- **What are the downstream implications?** If the new position is adopted, what else in the living document needs to change?
- **Is this a pivot or an exploration?** Founders sometimes think aloud — does the new claim read as a firm decision or as exploration?

## Output Format

Respond ONLY with valid XML in this exact structure:

<pass3_output>
  <analyses>
    <analysis>
      <contradiction_id>{{pass2_id}}</contradiction_id>
      <headline>One sentence describing the core tension</headline>
      <original_position>
        <summary>Summary of the original position</summary>
        <evidence>Specific citations — date, session, exact quote</evidence>
        <original_rationale>Why this position was adopted</original_rationale>
      </original_position>
      <new_position>
        <summary>Summary of the new claim</summary>
        <evidence>Source session date and relevant context</evidence>
        <possible_reasons_for_change>What might have prompted this rethink</possible_reasons_for_change>
      </new_position>
      <downstream_implications>What else in the living document would need updating if the new position is adopted</downstream_implications>
      <resolution_options>
        <option>
          <label>Update to new position</label>
          <description>What this means and what else would change</description>
        </option>
        <option>
          <label>Keep original position</label>
          <description>What this means and how to handle the new claim</description>
        </option>
        <option>
          <label>Acknowledge the tension and decide next session</label>
          <description>Flag this as an open question to resolve with more deliberation</description>
        </option>
      </resolution_options>
      <analyst_observation>Optional: any pattern or insight from the broader evidence that is worth surfacing</analyst_observation>
    </analysis>
  </analyses>
</pass3_output>
