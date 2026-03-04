# Ops Extraction Prompt (Claude Sonnet)

You are extracting operational items from a startup session — contacts, hypotheses, risks, open questions, feedback, and team needs. Skip high-level pitch/strategy claims (pricing models, market sizing, value propositions) unless they surface a specific risk, question, or action.

## Your Task

Extract contacts, hypotheses, risks, open questions, feedback, and hiring/team needs as discrete, self-contained claims. Generate a session summary and topic tags.

## Input Format

<session_input>
<session_type>{{session_type}}</session_type>
<participants>{{participants}}</participants>
<topic_hint>{{topic_hint}}</topic_hint>
<transcript>{{transcript}}</transcript>
<whiteboard_extraction>{{whiteboard_extraction}}</whiteboard_extraction>
</session_input>

## What to Extract

1. **Contacts and prospects** — names, organizations, roles, relationship status, intro paths. Use `claim_type: claim`.
2. **Hypotheses and assumptions** — beliefs that need validation ("We assume enterprise buyers need SOC2"). Use `claim_type: assertion` with `confidence: speculative` or `confidence: leaning`.
3. **Key risks and concerns** — anything that could go wrong or block progress. Use `claim_type: claim`.
4. **Open questions** — things explicitly flagged as unresolved or needing answers. Use `claim_type: question`.
5. **Feedback** — opinions, objections, or advice from investors, customers, or advisors. Attribute to the speaker. Use `claim_type: preference` for subjective takes, `claim_type: claim` for factual corrections.
6. **Hiring and team needs** — roles needed, candidates mentioned, capability gaps. Use `claim_type: decision` if committed, `claim_type: preference` if exploratory.

## Extraction Rules

1. **Preserve names and specifics** — "Sarah Chen at Atomica, VP Eng, warm intro via Dave" not "met someone at a nuclear company"
2. **Self-contained statements** — each claim must make sense on its own
3. **Include who said it** if distinguishable from the transcript
4. **Skip broad strategy** — do not extract general pitch claims (market size, business model, value prop) unless they contain a specific risk, question, or testable assumption
5. **Claim types:** `decision`, `claim`, `preference`, `assertion`, `question`
6. **Confidence levels:** `definite`, `leaning`, `speculative`

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
<session_type>Investor meeting</session_type>
<participants>Alex, Jordan, Marcus (angel investor)</participants>
<topic_hint>Catch-up after demo day</topic_hint>
<transcript>
Marcus said he liked the demo but thinks we need a technical co-founder or senior engineer before he'd commit. He mentioned his friend Sarah Chen at Atomica — she's VP of Engineering and apparently looking for her next thing. Warm intro if we want it. He also flagged that our assumption about utilities buying software without a formal procurement process is wrong — anything over $10K at a utility goes through procurement, minimum 6 months. That scares him a bit on our sales cycle timeline. We need to figure out whether we can get a pilot under $10K to bypass procurement. Jordan mentioned we should talk to Lisa Park, she ran sales at GridPoint and would know the utility buying process. Alex raised the concern that if our first customer churns before we close the second, the whole narrative falls apart. Marcus agreed. Still no answer on whether we can use the DOE grant for compute costs — Alex is going to check. Marcus also said he's heard good things about Render for deployment and that we should talk to their startup program.
</transcript>
<whiteboard_extraction></whiteboard_extraction>
</session_input>

### Expected Output

<extraction_output>
  <session_summary>Post-demo-day meeting with angel investor Marcus, who flagged the need for a technical co-founder and corrected the team's assumption about utility procurement thresholds. Two potential contacts surfaced: Sarah Chen (engineering hire) and Lisa Park (sales domain expertise).</session_summary>
  <topic_tags>
    <tag>fundraising</tag>
    <tag>contacts</tag>
    <tag>hiring</tag>
    <tag>sales-cycle</tag>
    <tag>risks</tag>
  </topic_tags>
  <claims>
    <claim>
      <claim_text>Marcus wants to see a technical co-founder or senior engineer on the team before he would commit to investing.</claim_text>
      <claim_type>preference</claim_type>
      <confidence>definite</confidence>
      <who_said_it>Marcus</who_said_it>
      <topic_tags><tag>fundraising</tag><tag>hiring</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Sarah Chen is VP of Engineering at Atomica and is reportedly looking for her next role. Marcus can make a warm intro.</claim_text>
      <claim_type>claim</claim_type>
      <confidence>leaning</confidence>
      <who_said_it>Marcus</who_said_it>
      <topic_tags><tag>contacts</tag><tag>hiring</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Any software purchase over $10K at a utility goes through formal procurement, with a minimum 6-month cycle.</claim_text>
      <claim_type>claim</claim_type>
      <confidence>definite</confidence>
      <who_said_it>Marcus</who_said_it>
      <topic_tags><tag>sales-cycle</tag><tag>target-market</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Can we structure a pilot under $10K to bypass utility procurement processes?</claim_text>
      <claim_type>question</claim_type>
      <confidence>speculative</confidence>
      <who_said_it></who_said_it>
      <topic_tags><tag>sales-cycle</tag><tag>pricing</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Lisa Park, former head of sales at GridPoint, may have insight into the utility buying process. Jordan suggested reaching out.</claim_text>
      <claim_type>claim</claim_type>
      <confidence>leaning</confidence>
      <who_said_it>Jordan</who_said_it>
      <topic_tags><tag>contacts</tag><tag>sales-cycle</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>If the first customer churns before the second is closed, the fundraising narrative collapses.</claim_text>
      <claim_type>assertion</claim_type>
      <confidence>definite</confidence>
      <who_said_it>Alex</who_said_it>
      <topic_tags><tag>risks</tag><tag>fundraising</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Can the DOE grant be used for compute costs? Alex is checking.</claim_text>
      <claim_type>question</claim_type>
      <confidence>speculative</confidence>
      <who_said_it>Alex</who_said_it>
      <topic_tags><tag>fundraising</tag><tag>infrastructure</tag></topic_tags>
    </claim>
    <claim>
      <claim_text>Marcus recommended looking into Render's startup program for deployment.</claim_text>
      <claim_type>preference</claim_type>
      <confidence>leaning</confidence>
      <who_said_it>Marcus</who_said_it>
      <topic_tags><tag>infrastructure</tag><tag>contacts</tag></topic_tags>
    </claim>
  </claims>
</extraction_output>
