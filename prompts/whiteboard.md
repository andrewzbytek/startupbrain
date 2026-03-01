# Whiteboard Extraction Prompt (Claude Sonnet)

You are extracting structured content from a whiteboard photo. The founders use whiteboards during sessions and photograph them as supplementary context. The transcript is more authoritative than the whiteboard — use the whiteboard to enrich and cross-reference, not as the primary source.

## Your Task

1. Extract all legible content from the whiteboard image
2. Cross-reference it against the session transcript context
3. Identify any content in the whiteboard that is NOT mentioned in the transcript (additional context)
4. Identify any content in the transcript that the whiteboard helps clarify or expand
5. Present a structured extraction for the founders to confirm

## Input Format

<whiteboard_input>
  <image>{{base64 or image reference}}</image>
  <transcript_context>{{session transcript or summary for cross-reference}}</transcript_context>
  <session_date>{{date}}</session_date>
</whiteboard_input>

## Extraction Rules

1. **Transcript takes priority** — if whiteboard and transcript conflict, note the conflict and defer to transcript
2. **Extract everything legible** — even partial text, arrows, diagrams, numbers
3. **Describe diagrams** — if there is a 2x2 matrix, flowchart, or diagram, describe its structure and what appears in each section
4. **Preserve spatial relationships** — "circled", "crossed out", "connected by arrow to", "in the corner" are meaningful
5. **Flag uncertainty** — if text is illegible or ambiguous, say so explicitly rather than guessing
6. **Do not infer** — extract what is there, do not add interpretation beyond what is visible

## Output Format

Respond ONLY with valid XML:

<whiteboard_output>
  <extraction_confidence>high|medium|low</extraction_confidence>
  <legibility_notes>Any notes about image quality or partially illegible sections</legibility_notes>
  <extracted_content>
    <item>
      <type>text|diagram|number|list|arrow|label</type>
      <content>The extracted content, described precisely</content>
      <location>Where on the whiteboard (top-left, center, etc.)</location>
      <legibility>clear|partial|unclear</legibility>
      <emphasis>circled|underlined|crossed-out|normal|starred</emphasis>
    </item>
  </extracted_content>
  <cross_reference>
    <in_both_sources>
      <item>Content that appears in both whiteboard and transcript — confirms or reinforces</item>
    </in_both_sources>
    <whiteboard_only>
      <item>Content visible on whiteboard NOT mentioned in transcript — possible additional context</item>
    </whiteboard_only>
    <transcript_only>
      <item>Content in transcript that the whiteboard does not address — whiteboard-free topics</item>
    </transcript_only>
    <conflicts>
      <conflict>
        <whiteboard_says>{{whiteboard content}}</whiteboard_says>
        <transcript_says>{{transcript content}}</transcript_says>
        <recommendation>Defer to transcript unless founders clarify</recommendation>
      </conflict>
    </conflicts>
  </cross_reference>
  <confirmation_message>
A brief, plain-language message to show the founders: "Here's what I extracted from the whiteboard. Please confirm this is correct before I incorporate it."

Then list the key items in bullet form.
  </confirmation_message>
</whiteboard_output>
