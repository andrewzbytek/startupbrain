"""
Feedback pattern detection for Startup Brain.
Section 8 of the SPEC — detects recurring themes across investor/customer feedback.
"""

import re
from datetime import datetime, timezone
from typing import Optional


def _extract_tag(text: str, tag: str) -> str:
    """Extract content of first XML tag from text."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _get_feedback_tracker_section() -> str:
    """Read the Feedback Tracker section from the living document."""
    from services.document_updater import read_living_document
    doc = read_living_document()
    match = re.search(r"## Feedback Tracker\n(.*?)(\n## |\Z)", doc, re.DOTALL)
    return match.group(1).strip() if match else ""


def _get_current_strategy_summary() -> str:
    """Extract Current State section from living document for pattern analysis."""
    from services.document_updater import read_living_document
    doc = read_living_document()
    match = re.search(r"## Current State\n(.*?)(\n## |\Z)", doc, re.DOTALL)
    if not match:
        return ""
    # Truncate to reasonable size
    return match.group(1).strip()[:3000]


def detect_patterns(feedback_tracker_section: str, new_feedback: dict) -> dict:
    """
    Detect patterns in feedback using Sonnet and feedback_pattern.md prompt.

    Args:
        feedback_tracker_section: Current Feedback Tracker section from startup_brain.md.
        new_feedback: Dict with keys: date, source_name, source_type, feedback_text,
                       meeting_context (optional).

    Returns:
        dict with:
            new_feedback_entry (dict)
            pattern_alerts (list)
            updated_recurring_themes (list)
            document_updates_needed (list)
            raw (str)
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_template = load_prompt("feedback_pattern")
    strategy_summary = _get_current_strategy_summary()

    prompt = f"""{prompt_template}

<feedback_input>
  <current_feedback_tracker>{feedback_tracker_section}</current_feedback_tracker>
  <new_feedback>
    <date>{escape_xml(new_feedback.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')))}</date>
    <source_name>{escape_xml(new_feedback.get('source_name', ''))}</source_name>
    <source_type>{escape_xml(new_feedback.get('source_type', 'investor'))}</source_type>
    <feedback_text>{escape_xml(new_feedback.get('feedback_text', ''))}</feedback_text>
    <meeting_context>{escape_xml(new_feedback.get('meeting_context', ''))}</meeting_context>
  </new_feedback>
  <current_strategy_summary>{strategy_summary}</current_strategy_summary>
</feedback_input>"""

    result = call_sonnet(prompt, task_type="feedback_pattern")
    raw = result["text"]

    # Parse new_feedback_entry
    entry_block = re.search(r"<new_feedback_entry>(.*?)</new_feedback_entry>", raw, re.DOTALL)
    new_entry = {}
    if entry_block:
        eb = entry_block.group(1)
        new_entry = {
            "date": _extract_tag(eb, "date"),
            "source": _extract_tag(eb, "source"),
            "summary": _extract_tag(eb, "summary"),
            "themes": re.findall(r"<theme>(.*?)</theme>", _extract_tag(eb, "themes")),
        }
        contradiction_block = re.search(r"<strategy_contradiction>(.*?)</strategy_contradiction>", eb, re.DOTALL)
        if contradiction_block:
            cb = contradiction_block.group(1)
            new_entry["strategy_contradiction"] = {
                "contradicts": _extract_tag(cb, "contradicts") == "true",
                "which_position": _extract_tag(cb, "which_position"),
                "description": _extract_tag(cb, "description"),
            }

    # Parse pattern alerts
    alerts = []
    for m in re.finditer(r"<alert>(.*?)</alert>", raw, re.DOTALL):
        ab = m.group(1)
        alerts.append({
            "theme": _extract_tag(ab, "theme"),
            "source_count": int(_extract_tag(ab, "source_count") or "0"),
            "sources": _extract_tag(ab, "sources"),
            "severity": _extract_tag(ab, "severity"),
            "description": _extract_tag(ab, "description"),
            "current_strategy_alignment": _extract_tag(ab, "current_strategy_alignment"),
        })

    # Parse updated recurring themes
    updated_themes = []
    for m in re.finditer(r"<theme>(.*?)</theme>", _extract_tag(raw, "updated_recurring_themes") or "", re.DOTALL):
        tb = m.group(1)
        updated_themes.append({
            "name": _extract_tag(tb, "name"),
            "count": int(_extract_tag(tb, "count") or "0"),
            "sources": _extract_tag(tb, "sources"),
            "status": _extract_tag(tb, "status"),
            "notes": _extract_tag(tb, "notes"),
        })

    # Parse document updates needed
    doc_updates = re.findall(r"<update>(.*?)</update>", raw, re.DOTALL)

    return {
        "new_feedback_entry": new_entry,
        "pattern_alerts": alerts,
        "updated_recurring_themes": updated_themes,
        "document_updates_needed": [u.strip() for u in doc_updates],
        "raw": raw,
    }


def get_recurring_themes() -> list:
    """
    Query MongoDB feedback collection for theme counts.
    Returns list of dicts: {theme, count, sources}
    """
    from services.mongo_client import get_feedback

    feedback_entries = get_feedback(limit=200)

    theme_map = {}
    for entry in feedback_entries:
        for theme in entry.get("themes", []):
            if theme not in theme_map:
                theme_map[theme] = {"theme": theme, "count": 0, "sources": []}
            theme_map[theme]["count"] += 1
            source = entry.get("source_name", "")
            if source and source not in theme_map[theme]["sources"]:
                theme_map[theme]["sources"].append(source)

    return sorted(theme_map.values(), key=lambda x: x["count"], reverse=True)


def should_alert(theme: str) -> bool:
    """Returns True if the given theme has 3 or more distinct sources."""
    themes = get_recurring_themes()
    for t in themes:
        if t["theme"] == theme:
            return len(t["sources"]) >= 3
    return False


def ingest_feedback(
    text: str,
    source_name: str,
    source_type: str,
    date: Optional[str] = None,
    meeting_context: str = "",
) -> dict:
    """
    Full feedback ingestion:
    1. Store in MongoDB
    2. Run pattern detection
    3. Update living document with feedback entry

    Args:
        text: Feedback text content.
        source_name: Name of investor/customer/advisor.
        source_type: 'investor' | 'customer' | 'advisor'
        date: Date string (YYYY-MM-DD), defaults to today.
        meeting_context: Optional context about the meeting.

    Returns:
        dict with: feedback_id, pattern_results, document_updated, alerts
    """
    from services.document_updater import update_document
    from services.mongo_client import insert_feedback

    date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Store in MongoDB
    feedback_doc = {
        "source_name": source_name,
        "source_type": source_type,
        "feedback_text": text,
        "date": date_str,
        "meeting_context": meeting_context,
        "themes": [],
    }
    feedback_id = insert_feedback(feedback_doc)

    # Get current feedback tracker for context
    feedback_tracker = _get_feedback_tracker_section()

    new_feedback = {
        "date": date_str,
        "source_name": source_name,
        "source_type": source_type,
        "feedback_text": text,
        "meeting_context": meeting_context,
    }

    # Run pattern detection
    pattern_results = detect_patterns(feedback_tracker, new_feedback)

    # Update living document with feedback entry
    # Build new_info from pattern results
    entry = pattern_results.get("new_feedback_entry", {})
    summary = entry.get("summary", text[:200])
    themes = entry.get("themes", [])
    themes_str = ", ".join(themes) if themes else "general"

    new_info = (
        f"New feedback from {source_name} ({source_type}) on {date_str}:\n"
        f"Summary: {summary}\n"
        f"Themes: {themes_str}\n"
        f"Meeting context: {meeting_context}"
    )
    if pattern_results.get("document_updates_needed"):
        new_info += "\n\nDocument updates needed:\n" + "\n".join(pattern_results["document_updates_needed"])

    doc_result = update_document(new_info, update_reason=f"Feedback from {source_name} ({date_str})")

    # Check for alerts
    alerts = pattern_results.get("pattern_alerts", [])
    alert_themes = [a for a in alerts if a.get("severity") == "signal"]

    return {
        "feedback_id": feedback_id,
        "pattern_results": pattern_results,
        "document_updated": doc_result.get("success", False),
        "alerts": alert_themes,
    }


def generate_evolution_narrative(topic: str) -> dict:
    """
    Generate a narrative of how thinking on a topic has evolved.
    Uses Sonnet with evolution.md prompt.

    Args:
        topic: Topic name (e.g., "Pricing", "Target Market").

    Returns:
        dict with: narrative, key_inflection_points, current_position_summary, raw
    """
    from services.claude_client import call_sonnet, load_prompt
    from services.document_updater import read_living_document

    prompt_template = load_prompt("evolution")
    doc = read_living_document()

    # Extract relevant section and decision log entries
    # Find the section for this topic
    section_match = re.search(
        rf"### {re.escape(topic)}.*?\n(.*?)(?=\n### |\n## |\Z)",
        doc,
        re.DOTALL | re.IGNORECASE,
    )
    section_content = section_match.group(1).strip() if section_match else ""

    current_position = ""
    changelog = ""
    cp_match = re.search(r"\*\*Current position:\*\*(.*?)(?=\*\*Changelog|\Z)", section_content, re.DOTALL)
    if cp_match:
        current_position = cp_match.group(1).strip()
    cl_match = re.search(r"\*\*Changelog:\*\*(.*?)$", section_content, re.DOTALL)
    if cl_match:
        changelog = cl_match.group(1).strip()

    # Extract relevant decision log entries (simple keyword match)
    decision_log_match = re.search(r"## Decision Log\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    decision_log = decision_log_match.group(1).strip() if decision_log_match else ""

    # Filter decision log entries containing the topic keyword
    topic_decisions = []
    for entry_match in re.finditer(r"### \d{4}-\d{2}-\d{2}.*?\n(.*?)(?=\n### |\Z)", decision_log, re.DOTALL):
        if topic.lower() in entry_match.group(0).lower():
            topic_decisions.append(entry_match.group(0).strip())
    relevant_decisions = "\n\n".join(topic_decisions)

    prompt = f"""{prompt_template}

<evolution_input>
  <topic>{topic}</topic>
  <current_position>{current_position}</current_position>
  <changelog_entries>{changelog}</changelog_entries>
  <relevant_decision_log_entries>{relevant_decisions}</relevant_decision_log_entries>
  <relevant_feedback/>
</evolution_input>"""

    result = call_sonnet(prompt, task_type="evolution")
    raw = result["text"]

    narrative = _extract_tag(raw, "narrative")
    current_pos_summary = _extract_tag(raw, "current_position_summary")

    inflection_points = []
    for m in re.finditer(r"<inflection>(.*?)</inflection>", raw, re.DOTALL):
        ib = m.group(1)
        inflection_points.append({
            "date": _extract_tag(ib, "date"),
            "what_changed": _extract_tag(ib, "what_changed"),
            "why": _extract_tag(ib, "why"),
        })

    return {
        "narrative": narrative,
        "key_inflection_points": inflection_points,
        "current_position_summary": current_pos_summary,
        "raw": raw,
    }


def generate_pitch_materials(request: str, book_frameworks: Optional[list] = None) -> dict:
    """
    Generate pitch materials using Opus and pitch_generation.md prompt.

    Args:
        request: Specific request from founders (e.g., "5-minute pitch for seed VC").
        book_frameworks: Optional list of dicts: {title, summary} for framework context.

    Returns:
        dict with: pitch_content, framework_notes, gaps_and_suggestions, format_type, audience, raw
    """
    from services.claude_client import call_opus, load_prompt
    from services.document_updater import read_living_document
    from services.mongo_client import get_book_frameworks

    prompt_template = load_prompt("pitch_generation")
    startup_brain = read_living_document()

    # Get book frameworks from MongoDB if not provided
    if book_frameworks is None:
        stored_frameworks = get_book_frameworks()
        book_frameworks = [
            {"title": f.get("title", ""), "summary": f.get("summary", "")}
            for f in stored_frameworks
        ]

    # Build book frameworks XML
    frameworks_xml_parts = ["<book_frameworks>"]
    for fw in (book_frameworks or []):
        frameworks_xml_parts.append("  <framework>")
        frameworks_xml_parts.append(f"    <title>{fw.get('title', '')}</title>")
        frameworks_xml_parts.append(f"    <summary>{fw.get('summary', '')}</summary>")
        frameworks_xml_parts.append("  </framework>")
    frameworks_xml_parts.append("</book_frameworks>")
    frameworks_xml = "\n".join(frameworks_xml_parts)

    prompt = f"""{prompt_template}

<pitch_input>
  <startup_brain>{startup_brain}</startup_brain>
  {frameworks_xml}
  <specific_request>{request}</specific_request>
  <audience_context>As specified in the request.</audience_context>
</pitch_input>"""

    result = call_opus(prompt, task_type="pitch_generation")
    raw = result["text"]

    pitch_content = _extract_tag(raw, "pitch_content")
    format_type = _extract_tag(raw, "format_type")
    audience = _extract_tag(raw, "audience")

    framework_notes = re.findall(r"<note>(.*?)</note>", raw, re.DOTALL)
    gaps = re.findall(r"<gap>(.*?)</gap>", raw, re.DOTALL)

    return {
        "pitch_content": pitch_content,
        "format_type": format_type,
        "audience": audience,
        "framework_notes": [n.strip() for n in framework_notes],
        "gaps_and_suggestions": [g.strip() for g in gaps],
        "raw": raw,
    }
