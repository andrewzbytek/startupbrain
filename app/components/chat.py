"""
Chat interface for Startup Brain.
Handles conversation, query routing, and contradiction resolution UI.
"""

import html
import logging
import re
from datetime import datetime, timedelta, timezone

import streamlit as st

from app.state import add_message, set_mode, invalidate_sidebar


from app.components._parsers import _escape_latex
from services.claude_client import escape_xml


# Minimum transcript length to suggest ingestion flow
TRANSCRIPT_SUGGEST_LENGTH = 500

# Maps user keywords to MongoDB session_type values
# Values are intentional substrings — search_sessions() uses $regex matching,
# so "Investor" matches both "Investor meeting" and "Investor email/feedback"
_SESSION_TYPE_MAP = {
    "investor": "Investor",
    "vc": "Investor",
    "customer": "Customer interview",
    "advisor": "Advisor",
    "co-founder": "Co-founder",
    "cofounder": "Co-founder",
    "internal": "Internal",
}


def _is_likely_transcript(text: str) -> bool:
    """Heuristic: detect if user pasted a long transcript."""
    if len(text) < TRANSCRIPT_SUGGEST_LENGTH:
        return False
    # Look for common transcript signals
    signals = [
        ":" in text and text.count("\n") > 5,  # speaker: line format
        text.count("\n") > 10,                  # many lines
        len(text.split()) > 100,                # lots of words
    ]
    return sum(signals) >= 2


def _is_direct_correction(text: str) -> bool:
    """Detect direct corrections like 'no, it's actually X' or 'actually, ...'."""
    lower = text.lower().strip()
    correction_signals = [
        lower.startswith("no,"),
        lower.startswith("actually,"),
        lower.startswith("wait,"),
        lower.startswith("correction:"),
        "it's actually" in lower,
        "it is actually" in lower,
        "the correct answer is" in lower,
        "update that to" in lower,
        "change that to" in lower,
    ]
    return any(correction_signals)


def _is_quick_note(text: str) -> bool:
    """Detect quick note prefixes like 'note:', 'remember:', etc."""
    lower = text.lower().strip()
    prefixes = ("note:", "remember:", "quick note:", "jot:", "fyi:")
    return any(lower.startswith(p) for p in prefixes)


def _strip_quick_note_prefix(text: str) -> str:
    """Strip the quick note prefix from the message."""
    lower = text.lower().strip()
    prefixes = ("quick note:", "note:", "remember:", "jot:", "fyi:")
    for p in prefixes:
        if lower.startswith(p):
            return text.strip()[len(p):].strip()
    return text.strip()


def _is_contact(text: str) -> bool:
    """Detect contact prefixes like 'contact:', 'prospect:', 'lead:'."""
    lower = text.lower().strip()
    prefixes = ("contact:", "prospect:", "lead:")
    return any(lower.startswith(p) for p in prefixes)


def _strip_contact_prefix(text: str) -> str:
    """Strip the contact prefix from the message."""
    lower = text.lower().strip()
    prefixes = ("contact:", "prospect:", "lead:")
    for p in prefixes:
        if lower.startswith(p):
            return text.strip()[len(p):].strip()
    return text.strip()


def _is_hypothesis(text: str) -> bool:
    """Detect hypothesis prefix like 'hypothesis: ...'."""
    lower = text.lower().strip()
    return lower.startswith("hypothesis:")


def _is_hypothesis_status_update(text: str) -> bool:
    """Detect hypothesis status update prefixes like 'validated:' or 'invalidated:'."""
    lower = text.lower().strip()
    return lower.startswith("validated:") or lower.startswith("invalidated:")


def _strip_hypothesis_prefix(text: str) -> str:
    """Strip the hypothesis prefix from the message."""
    lower = text.lower().strip()
    if lower.startswith("hypothesis:"):
        return text.strip()[len("hypothesis:"):].strip()
    return text.strip()


def _strip_status_prefix(text: str) -> tuple:
    """Strip the status prefix and return (status, text)."""
    lower = text.lower().strip()
    if lower.startswith("validated:"):
        return "validated", text.strip()[len("validated:"):].strip()
    if lower.startswith("invalidated:"):
        return "invalidated", text.strip()[len("invalidated:"):].strip()
    return "", text.strip()


def _extract_session_type_filter(lower: str):
    """Scan for session type keywords in the message. Returns MongoDB session_type or None."""
    for keyword, session_type in _SESSION_TYPE_MAP.items():
        if keyword in lower:
            return session_type
    return None


def _extract_date_filter(lower: str):
    """
    Parse date references from the message.
    Returns {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} or None.
    """
    # ISO date
    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', lower)
    if iso_match:
        date_str = iso_match.group(1)
        return {"from": date_str, "to": date_str}

    # Month + day (e.g. "march 5th", "january 15")
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    month_pattern = '|'.join(months.keys())
    month_match = re.search(
        r'(' + month_pattern + r')\s+(\d{1,2})(?:st|nd|rd|th)?', lower
    )
    if month_match:
        month_num = months[month_match.group(1)]
        day = int(month_match.group(2))
        year = datetime.now(timezone.utc).year
        date_str = f"{year}-{month_num:02d}-{day:02d}"
        return {"from": date_str, "to": date_str}

    # Relative: last week
    now = datetime.now(timezone.utc)
    if "last week" in lower:
        week_ago = now - timedelta(days=7)
        return {"from": week_ago.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}

    # Relative: this month
    if "this month" in lower:
        first_of_month = now.replace(day=1)
        return {"from": first_of_month.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}

    return None


def _extract_participant_filter(lower: str):
    """Extract participant name from 'meeting with [name]' pattern. Returns name or None."""
    match = re.search(r'meeting(?:s)?\s+with\s+([a-z]+(?:\s+[a-z]+)?)', lower)
    if match:
        return match.group(1).strip()
    return None


def _classify_query(text: str) -> str:
    """
    Classify user query for routing.
    Returns: "current_state" | "historical" | "pitch" | "recall" | "challenge" | "analysis" | "general"
    """
    lower = text.lower()
    if any(kw in lower for kw in ["what is our current", "what's our", "where are we on", "current position", "right now"]):
        return "current_state"
    # Recall — check before pitch to avoid "investor" routing to pitch
    _recall_keywords = [
        "list all meetings", "list all sessions", "how many meetings",
        "what meetings", "meeting with", "meetings with",
        "what did we discuss", "did we discuss", "did we talk about",
        "summarize all",
        "what did investors say", "what did customers say",
        "who said", "who was the most", "recap",
        "customer feedback", "investor feedback", "advisor feedback",
        "all customer", "all investor",
    ]
    if any(kw in lower for kw in _recall_keywords):
        return "recall"
    if any(kw in lower for kw in ["pitch", "investor", "deck", "slide", "one-pager", "elevator"]):
        return "pitch"
    if any(kw in lower for kw in ["challenge", "poke holes", "devil's advocate", "stress test", "what am i missing", "what are we missing", "pushback"]):
        return "challenge"
    if any(kw in lower for kw in ["analyze", "analysis", "strategy", "strategic", "should we", "recommend"]):
        return "analysis"
    if any(kw in lower for kw in ["when did we", "history", "evolution", "changed", "last time", "previous"]):
        return "historical"
    return "general"


# ---------------------------------------------------------------------------
# Recall context — fetch sessions/claims/feedback from MongoDB
# ---------------------------------------------------------------------------

_MAX_RECALL_CHARS = 8000


def _format_recall_context(sessions, claims=None, feedback=None) -> str:
    """Format sessions, claims, and feedback into XML context for the prompt."""
    parts = ["<session_recall>", f"<session_count>{len(sessions)}</session_count>"]

    if sessions:
        parts.append("<sessions>")
        for s in sessions:
            meta = s.get("metadata", {})
            date = s.get("session_date", s.get("created_at", ""))
            if hasattr(date, "strftime"):
                date = date.strftime("%Y-%m-%d")
            stype = escape_xml(meta.get("session_type", "Unknown"))
            participants = escape_xml(meta.get("participants", ""))
            summary = escape_xml(s.get("summary", "")[:500])
            tags = escape_xml(", ".join(s.get("topic_tags", [])))
            entry = f"- [{date}] {stype}"
            if participants:
                entry += f" | Participants: {participants}"
            if summary:
                entry += f" | {summary}"
            if tags:
                entry += f" | Tags: {tags}"
            parts.append(entry)
        parts.append("</sessions>")

    if claims:
        parts.append("<claims>")
        for c in claims[:30]:
            ctype = escape_xml(c.get("claim_type", "claim"))
            text = escape_xml(c.get("claim_text", ""))
            who = escape_xml(c.get("who_said_it", ""))
            confidence = escape_xml(c.get("confidence", ""))
            entry = f"- [{ctype}] {text}"
            if who:
                entry += f" (by {who}"
                if confidence:
                    entry += f", {confidence}"
                entry += ")"
            parts.append(entry)
        parts.append("</claims>")

    if feedback:
        parts.append("<feedback>")
        for f in feedback[:10]:
            source = escape_xml(f.get("source_type", ""))
            summary = escape_xml(f.get("feedback_text", f.get("summary", f.get("text", "")))[:200])
            parts.append(f"- [{source}] {summary}")
        parts.append("</feedback>")

    parts.append("</session_recall>")

    result = "\n".join(parts)
    if len(result) > _MAX_RECALL_CHARS:
        # Truncate at a newline boundary to avoid cutting through XML tags
        truncated = result[:_MAX_RECALL_CHARS]
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        result = truncated + "\n</session_recall>"
    return result


def _build_recall_context(user_message: str) -> str:
    """Build recall context from MongoDB for a recall query. Returns XML string or empty."""
    from services.mongo_client import is_mongo_available, search_sessions, get_session_claims, get_feedback

    if not is_mongo_available():
        return ""

    lower = user_message.lower()
    session_type = _extract_session_type_filter(lower)
    date_filter = _extract_date_filter(lower)
    participant = _extract_participant_filter(lower)

    kwargs = {"limit": 20}
    if session_type:
        kwargs["session_type"] = session_type
    if participant:
        kwargs["participant"] = participant
    if date_filter:
        kwargs["date_from"] = date_filter.get("from")
        kwargs["date_to"] = date_filter.get("to")

    brain_ctx = st.session_state.get("chat_brain_context", "pitch")
    brain_filter = brain_ctx if brain_ctx != "both" else ""
    if brain_filter:
        kwargs["brain"] = brain_filter

    sessions = search_sessions(**kwargs)

    if not sessions:
        return "<session_recall><session_count>0</session_count></session_recall>"

    # Fetch claims for detail queries
    session_ids = []
    for s in sessions:
        sid = s.get("_id")
        if sid:
            session_ids.append(str(sid))
    claims = get_session_claims(session_ids) if session_ids else []

    # Fetch feedback when message mentions it
    feedback_list = []
    feedback_keywords = ["feedback", "what did investors say", "what did customers say", "what did advisors say"]
    if any(kw in lower for kw in feedback_keywords):
        feedback_source_map = {
            "Investor": "investor",
            "Customer interview": "customer",
            "Advisor": "advisor",
        }
        source_type = feedback_source_map.get(session_type)
        feedback_list = get_feedback(source_type=source_type, brain=brain_filter)

    return _format_recall_context(sessions, claims, feedback_list)


def _get_system_prompt(query_type: str = "") -> str:
    """Build a system prompt including current living document state."""
    try:
        from services.document_updater import read_living_document
        brain_ctx = st.session_state.get("chat_brain_context", "pitch")
        if brain_ctx == "both":
            pitch_doc = read_living_document(brain="pitch")
            ops_doc = read_living_document(brain="ops")
            doc = f"## PITCH BRAIN\n{pitch_doc}\n\n## OPS BRAIN\n{ops_doc}"
        elif brain_ctx == "ops":
            doc = read_living_document(brain="ops")
        else:
            doc = read_living_document(brain="pitch")
    except Exception as _doc_err:
        logging.warning("Failed to read living document for system prompt: %s", _doc_err)
        doc = ""

    base = (
        "You are Startup Brain — an AI knowledge assistant for a two-person early-stage startup "
        "in the compliance space (nuclear, oil & gas, power generation). "
        "You have access to the startup's living knowledge document below.\n\n"

        "## Socratic Pushback\n"
        "When discussing a topic covered in the living document, reference specific dates from "
        "the Changelog, rationale from the Decision Log, and any relevant Dismissed Contradictions. "
        "After answering, ask ONE probing question about gaps, untested assumptions, or missing evidence — "
        "but only when the topic warrants it (analysis, strategy, decisions). "
        "Do not ask probing questions on trivial or casual messages.\n\n"

        "## Context Surfacing\n"
        "When you identify relevant context in the living document that the founder may not be thinking about, "
        "append a brief section after your main answer:\n"
        "---\n"
        "**Related context**\n"
        "- [relevant dismissed contradiction, feedback entry, or recent changelog activity]\n\n"
        "Omit this section entirely when nothing is relevant. Do NOT surface context on every message. "
        "Do NOT repeat context already mentioned earlier in the conversation.\n\n"

        "## Feedback Echo\n"
        "When a topic overlaps with entries in the Feedback Tracker, weave them into your response "
        "naturally — mention the source name, type (investor/customer/advisor), and date. "
        "For example: 'Sarah Chen (investor, 2026-02-10) raised a similar concern about branding.'\n\n"

        "## Tone Calibration\n"
        "- Current-state queries: factual, direct, cite the document\n"
        "- Analysis/strategy queries: Socratic, opinionated, reference Decision Log trade-offs\n"
        "- Historical queries: narrative, trace the evolution through Changelog entries\n"
        "- Pitch queries: constructive, polished, frame strengths\n"
        "- Recall queries: when given <session_recall> data, answer based on that data. "
        "Cite dates, participants, and session types. If no sessions match, say so. "
        "Do not invent sessions not in the data.\n"
        "- Casual/greetings: brief, friendly, no context surfacing\n\n"

        "## Guardrails\n"
        "- You NEVER block founders from making changes — you inform, not gatekeep.\n"
        "- If asked to update or change something, acknowledge it and update immediately.\n"
        "- Do NOT invent information not in the document.\n"
        "- Do NOT surface related context on every message — only when genuinely relevant.\n"
        "- Respond in plain markdown.\n\n"
    )
    # Token budget: cap living document to ~120K chars (~30K tokens) to leave headroom
    # for scratchpad, book framework, conversation history, and response within 200K context
    _MAX_DOC_CHARS = 120_000
    if doc:
        original_len = len(doc)
        if original_len > _MAX_DOC_CHARS:
            doc = doc[:_MAX_DOC_CHARS]
            logging.warning(
                "Living document truncated for system prompt: %d chars exceeds %d limit",
                original_len, _MAX_DOC_CHARS,
            )
            base += f"<startup_brain>\n{escape_xml(doc)}\n[Document truncated — showing first {_MAX_DOC_CHARS:,} characters]\n</startup_brain>"
        else:
            base += f"<startup_brain>\n{escape_xml(doc)}\n</startup_brain>"

    # Append recent scratchpad notes so the AI can reference them
    try:
        from services.mongo_client import find_many
        scratchpad_query = {"source_type": "quick_note", "claim_type": "scratchpad"}
        # Don't filter scratchpad by brain — notes should surface in all contexts
        scratchpad = find_many(
            "claims",
            scratchpad_query,
            sort_by="created_at",
            sort_order=-1,
            limit=50,
        )
        if scratchpad:
            notes_text = "\n".join(
                f"- [{n.get('created_at', '').strftime('%Y-%m-%d %H:%M') if hasattr(n.get('created_at', ''), 'strftime') else 'unknown date'}] {n.get('claim_text', '')}"
                for n in scratchpad
            )
            base += f"\n\n<scratchpad_notes>\nRecent scratchpad notes from the founder (not in the living document):\n{escape_xml(notes_text)}\n</scratchpad_notes>"
    except Exception as _pad_err:
        logging.warning("Scratchpad fetch failed: %s", _pad_err)

    # Append book framework if loaded for cross-check (skip for recall/historical to avoid inflating prompts)
    if query_type not in ("recall", "historical"):
        book_content = st.session_state.get("book_crosscheck_content", "")
        if book_content:
            base += f"\n\n<book_framework>{escape_xml(book_content)}</book_framework>"

    return base


def _build_claude_prompt(user_message: str, query_type: str):
    """Build prompt components shared by streaming and non-streaming callers."""
    from services.claude_client import call_with_routing

    history = st.session_state.get("conversation_history", [])
    recent_history = history[-10:] if len(history) > 10 else history

    history_text = ""
    for msg in recent_history[:-1]:
        role_label = "Founder" if msg["role"] == "user" else "Startup Brain"
        history_text += f"{role_label}: {escape_xml(msg['content'])}\n\n"

    if history_text:
        full_prompt = f"<conversation_history>\n{history_text}</conversation_history>\n\nFounder: {escape_xml(user_message)}"
    else:
        full_prompt = escape_xml(user_message)

    # Inject recall context for recall queries
    if query_type == "recall":
        recall_context = _build_recall_context(user_message)
        if recall_context:
            full_prompt = f"{recall_context}\n\n{full_prompt}"

    task_map = {
        "pitch": "pitch_generation",
        "challenge": "strategic_analysis",
        "analysis": "strategic_analysis",
        "recall": "general",
        "current_state": "general",
        "historical": "general",
        "general": "general",
    }
    task_type = task_map.get(query_type, "general")
    system = _get_system_prompt(query_type=query_type)
    return full_prompt, task_type, system


def _call_claude(user_message: str, query_type: str) -> str:
    """Route to appropriate Claude model and return full response text (non-streaming)."""
    try:
        from services.claude_client import call_with_routing
        full_prompt, task_type, system = _build_claude_prompt(user_message, query_type)
        result = call_with_routing(full_prompt, task_type=task_type, system=system, stream=False)
        return result.get("text", "Sorry, I could not generate a response.")
    except Exception as e:
        logging.error("Chat routing error: %s", e)
        return "I had trouble responding. Please try again."


def _call_claude_stream(user_message: str, query_type: str):
    """
    Route to appropriate Claude model and return a generator yielding text chunks.
    Compatible with st.write_stream().
    """
    try:
        from services.claude_client import call_with_routing
        full_prompt, task_type, system = _build_claude_prompt(user_message, query_type)
        generator = call_with_routing(full_prompt, task_type=task_type, system=system, stream=True)
        yield from generator
    except Exception as e:
        logging.error("Chat stream error: %s", e)
        yield "I had trouble responding. Please try again."


def _apply_direct_correction(user_message: str) -> str:
    """
    Apply a direct correction to the living document immediately.
    Runs a lightweight consistency check (informational only) before applying.
    The correction always goes through regardless of consistency findings.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import update_document
        from services.consistency import run_consistency_check

        # Determine target brain — use active_brain (write target), not chat_brain_context (read context)
        brain = st.session_state.get("active_brain", "pitch")

        # Build synthetic claim for consistency check
        claim = {
            "claim_text": user_message,
            "claim_type": "decision",
            "confidence": "definite",
        }

        # Run lightweight consistency check (informational only) — pitch brain only
        info_note = ""
        if brain == "pitch":
            try:
                results = run_consistency_check([claim], session_type="Direct correction", brain=brain)
                if results.get("has_contradictions"):
                    contradictions = results.get("pass2", {}).get("retained", [])
                    if contradictions:
                        notes = []
                        for c in contradictions:
                            notes.append(
                                f"- **{c.get('severity', 'Notable')}**: "
                                f"{c.get('evidence_summary', c.get('tension_description', ''))}"
                            )
                        info_note = (
                            "\n\nHeads up — this touches on some existing positions:\n"
                            + "\n".join(notes)
                            + "\n\nThe update has been applied as requested."
                        )
            except Exception as _cc_err:
                logging.warning("Informational consistency check skipped: %s", _cc_err)

        # Always apply the correction — route to the active brain
        result = update_document(
            new_info=f"Direct correction from founder: {user_message}",
            update_reason="Direct founder correction",
            brain=brain,
        )

        if result.get("success"):
            base = f"Got it — updated. {result.get('message', '')}"
            return base + info_note + "\n\nWhat else can I help with?"
        else:
            logging.error("Direct correction failed: %s", result.get('message', ''))
            return "I heard you, but the document update ran into an issue. Please try again."
    except Exception as e:
        logging.error("Direct correction error: %s", e)
        return "Understood. Could not auto-update the document. Please try again."


def _apply_quick_note(note_text: str) -> str:
    """
    Save a quick note to the scratchpad (MongoDB only).
    Does NOT update the living document.
    Stored with claim_type='scratchpad' and source_type='quick_note'.
    Notes are surfaced in the chat system prompt so the AI can reference them.
    """
    try:
        from services.mongo_client import insert_claim
        from datetime import datetime, timezone

        # Notes always stored to ops brain — surfaced cross-brain in system prompt (by design)
        result_id = insert_claim({
            "claim_text": note_text,
            "claim_type": "scratchpad",
            "confidence": "definite",
            "source_type": "quick_note",
            "who_said_it": "Founder",
            "confirmed": True,
        }, brain="ops")

        if not result_id:
            return "Could not save note — database unavailable. Please try again."
        return "Noted — saved to scratchpad. I can reference this in our conversation, but it won't appear in the living document."
    except Exception as e:
        logging.error("Could not save note: %s", e)
        return "Could not save note. Please try again."


def _apply_contact(contact_text: str) -> str:
    """
    Apply a contact note to the living document.
    Same lightweight path as quick notes — skips extraction and consistency check.
    Stores a claim in MongoDB with source_type='contact_note'.
    """
    try:
        from services.document_updater import update_document
        from services.mongo_client import find_one, insert_claim
        from datetime import datetime, timezone

        result = update_document(
            new_info=f"Contact update from founder: {contact_text}",
            update_reason="Contact note",
            brain="ops",
        )

        claim_synced = True
        try:
            existing = find_one("claims", {"claim_text": contact_text, "claim_type": "claim", "source_type": "contact_note", "brain": "ops"})
            if not existing:
                claim_result = insert_claim({
                    "claim_text": contact_text,
                    "claim_type": "claim",
                    "confidence": "definite",
                    "source_type": "contact_note",
                    "who_said_it": "Founder",
                    "confirmed": True,
                }, brain="ops")
                if not claim_result:
                    logging.warning("Contact claim insert returned None — document updated but claims not synced")
                    claim_synced = False
        except Exception as e:
            logging.error("Contact claim insert failed: %s", e)
            claim_synced = False

        if result.get("success"):
            msg = f"Contact noted — {result.get('message', '')}"
            if not claim_synced:
                msg += " (note: contact is in the document but not indexed for search)"
            return msg
        else:
            logging.error("Contact save issue: %s", result.get('message', ''))
            return "Contact may not have been saved. Please try again."
    except Exception as e:
        logging.error("Could not save contact: %s", e)
        return "Could not save contact. Please try again."


def _apply_hypothesis(user_message: str) -> str:
    """
    Add a new hypothesis to the living document and MongoDB.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import (
            read_living_document, write_living_document, _add_hypothesis, _git_commit,
        )
        from services.mongo_client import find_one, insert_claim, upsert_living_document
        from services.ingestion_lock import acquire_doc_lock, release_doc_lock
        from datetime import datetime, timezone

        hypothesis_text = _strip_hypothesis_prefix(user_message)
        if not hypothesis_text:
            return "Please provide a hypothesis after the 'hypothesis:' prefix."

        lock_id = acquire_doc_lock(timeout_seconds=30)
        if not lock_id:
            return "Could not update document — another update is in progress. Please try again."

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = (
            f"- [{date_str}] **{hypothesis_text}**\n"
            f"  Status: unvalidated | Test: [to be defined]\n"
            f"  Evidence: ---"
        )

        try:
            doc = read_living_document(brain="ops")
            doc = _add_hypothesis(doc, entry)
            # Mirror to MongoDB first (source of truth on Render's ephemeral FS)
            mirror_ok = upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": "New hypothesis"}, brain="ops")
            if not mirror_ok:
                logging.error("upsert_living_document failed for hypothesis update — not mirrored to MongoDB")
            try:
                write_living_document(doc, brain="ops")
                _git_commit(f"Add hypothesis: {hypothesis_text[:50]}", brain="ops")
            except Exception as file_err:
                logging.warning("Hypothesis file write failed (MongoDB succeeded): %s", file_err)
        finally:
            release_doc_lock(lock_id)

        # Store in MongoDB as a hypothesis claim (dedup guard)
        db_synced = False
        try:
            existing = find_one("claims", {"claim_text": hypothesis_text, "claim_type": "hypothesis", "brain": "ops"})
            if existing:
                db_synced = True  # Already stored — skip duplicate
            else:
                result = insert_claim({
                    "claim_text": hypothesis_text,
                    "claim_type": "hypothesis",
                    "confidence": "speculative",
                    "source_type": "hypothesis",
                    "who_said_it": "Founder",
                    "confirmed": True,
                    "status": "unvalidated",
                    "test_plan": "",
                }, brain="ops")
                db_synced = result is not None
        except Exception as _hyp_db_err:
            logging.error("Hypothesis claim insert failed: %s", _hyp_db_err)
            db_synced = False

        confirmation = (
            f"Hypothesis tracked: **{hypothesis_text}**\n\n"
            f"Status: unvalidated. You can update it later with `validated: {hypothesis_text[:30]}...` "
            f"or `invalidated: {hypothesis_text[:30]}...` in chat, or use the sidebar."
        )
        if not db_synced:
            confirmation += " (note: database sync failed — hypothesis is in the document but not searchable via chat history)"
        return confirmation
    except Exception as e:
        logging.error("Could not track hypothesis: %s", e)
        return "Could not track hypothesis. Please try again."


def _apply_hypothesis_status_update(user_message: str) -> str:
    """
    Update the status of an existing hypothesis.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import (
            read_living_document, write_living_document,
            _update_hypothesis_status, _git_commit,
        )
        from services.mongo_client import update_hypothesis_status, upsert_living_document
        from datetime import datetime, timezone

        new_status, fragment = _strip_status_prefix(user_message)
        if not fragment:
            return f"Please provide the hypothesis text after '{new_status}:'."

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Update living document (hypotheses live in ops brain)
        from services.ingestion_lock import acquire_doc_lock, release_doc_lock
        lock_id = acquire_doc_lock()
        if not lock_id:
            return "Document is being updated by another process. Try again shortly."
        try:
            doc = read_living_document(brain="ops")
            updated_doc = _update_hypothesis_status(doc, fragment, new_status)
            if updated_doc == doc:
                return f"Could not find a hypothesis matching: **{fragment}**. Check the sidebar for exact text."

            # Mirror to MongoDB first (source of truth on Render's ephemeral FS)
            mirror_ok = upsert_living_document(updated_doc, metadata={"last_updated": date_str}, brain="ops")
            if not mirror_ok:
                logging.error("upsert_living_document failed for hypothesis status update — not mirrored to MongoDB")
            try:
                write_living_document(updated_doc, brain="ops")
                _git_commit(f"Hypothesis {new_status}: {fragment[:50]}", brain="ops")
            except Exception as file_err:
                logging.warning("Hypothesis status file write failed (MongoDB succeeded): %s", file_err)
        finally:
            release_doc_lock(lock_id)

        # Update MongoDB
        synced = False
        try:
            synced = update_hypothesis_status(fragment, new_status)
            if not synced:
                logging.warning("update_hypothesis_status matched nothing in claims for fragment: %s", fragment[:80])
        except Exception as e:
            logging.error("Failed to sync hypothesis status to MongoDB: %s", e)

        confirmation = f"Hypothesis updated to **{new_status}**: {fragment}"
        if not synced:
            confirmation += " (note: database sync did not match — status may be out of sync in query results)"
        return confirmation
    except Exception as e:
        logging.error("Could not update hypothesis: %s", e)
        return "Could not update hypothesis. Please try again."


_QUICK_COMMANDS = [
    (
        "note:", "note: ",
        "We decided to focus on small plants first",
        "Saves to scratchpad (does not update living document)",
        "Saves the note to MongoDB as a scratchpad entry. **Does not update the living "
        "document.** The AI can reference your scratchpad notes when answering questions. "
        "Use for quick facts, decisions, reminders, or things you want to remember.",
    ),
    (
        "hypothesis:", "hypothesis: ",
        "Small plant operators have <12 month procurement cycles",
        "Tracks a testable assumption",
        "Adds an entry to the Active Hypotheses section with status 'unvalidated'. "
        "Stored in both the living document and MongoDB. You can later mark it "
        "validated or invalidated. **No consistency check.**",
    ),
    (
        "contact:", "contact: ",
        "Jane Doe, PSEG, prospect, in-conversation",
        "Logs a contact: name, org, type, status",
        "Updates the Key Contacts section of the living document via AI. "
        "Also stores a claim in MongoDB. Format: name, organization, type "
        "(prospect/investor/advisor/hire/partner), status. **No consistency check.**",
    ),
]


def _render_quick_command_panel():
    """Render tiny quick command chips + active input field if one is selected."""
    active_cmd = st.session_state.get("_active_quick_cmd")

    # If no command is active, show chips as clickable st.buttons styled small
    if not active_cmd:
        btn_cols = st.columns(len(_QUICK_COMMANDS))
        for i, (label, _prefix, _example, _hint, _detail) in enumerate(_QUICK_COMMANDS):
            with btn_cols[i]:
                if st.button(label, key=f"qcmd_btn_{i}", use_container_width=True):
                    st.session_state._active_quick_cmd = _prefix
                    st.rerun()
    else:
        # Active command — show guidance, input field with placeholder, and buttons
        example = ""
        hint = ""
        detail = ""
        for _label, prefix, ex, h, d in _QUICK_COMMANDS:
            if prefix == active_cmd:
                example = ex
                hint = h
                detail = d
                break
        # Guidance line + help popover
        hint_col, help_col = st.columns([6, 1])
        with hint_col:
            st.caption(f"{hint}. Example: *{example}*")
        with help_col:
            with st.popover("?"):
                st.markdown(f"**{active_cmd.strip()}**")
                st.markdown(detail)
                st.markdown("---")
                st.markdown(
                    "**How is this different from Ingest Session?**\n\n"
                    "Full ingestion extracts multiple claims from a transcript, "
                    "lets you confirm/edit each one, runs a 3-pass consistency check "
                    "against everything already in your knowledge base, and flags "
                    "contradictions for resolution. Quick commands skip all of that — "
                    "they apply a single update directly."
                )
        cmd_text = st.text_input(
            "Quick command",
            value="",
            placeholder=f"{active_cmd}{example}",
            key="_quick_cmd_input",
            label_visibility="collapsed",
        )
        send_col, cancel_col, _ = st.columns([1, 1, 4])
        with send_col:
            if st.button("Send", key="qcmd_send", use_container_width=True):
                text_to_send = cmd_text.strip() if cmd_text.strip() else ""
                # Prepend prefix if user didn't include it
                if text_to_send and not text_to_send.startswith(active_cmd.strip()):
                    text_to_send = active_cmd + text_to_send
                if text_to_send:
                    st.session_state._quick_cmd_pending = text_to_send
                    st.session_state._active_quick_cmd = None
                    st.rerun()
        with cancel_col:
            if st.button("Cancel", key="qcmd_cancel", use_container_width=True):
                st.session_state._active_quick_cmd = None
                st.rerun()


def _handle_quick_action(text: str, query_type: str):
    """Process a quick-action button click as a user message."""
    with st.chat_message("user"):
        st.markdown(text)
    add_message("user", text)
    with st.chat_message("assistant"):
        response = st.write_stream(_call_claude_stream(text, query_type))
    add_message("assistant", response if isinstance(response, str) else "".join(response) if response else "")
    st.rerun()


def render_chat():
    """Main chat UI. Called when mode='chat'."""
    from services.mongo_client import is_mongo_available
    if not is_mongo_available():
        st.warning("Memory storage is currently unavailable. Chat still works, but session history and ingestion are disabled.")

    # Brain context selector
    brain_ctx = st.session_state.get("chat_brain_context", "pitch")
    ctx_col1, ctx_col2 = st.columns([8, 2])
    with ctx_col2:
        context_options = ["Pitch", "Ops", "Both"]
        ctx_idx = {"pitch": 0, "ops": 1, "both": 2}.get(brain_ctx, 0)
        selected_ctx = st.radio(
            "Context",
            context_options,
            index=ctx_idx,
            horizontal=True,
            label_visibility="collapsed",
            key="chat_context_toggle",
        )
        new_ctx = selected_ctx.lower()
        if new_ctx != brain_ctx:
            st.session_state.chat_brain_context = new_ctx
            st.rerun()

    # --- Chat frame: bordered container for the conversation area ---
    with st.container(border=True):
        history = st.session_state.get("conversation_history", [])

        # Display conversation history
        for msg in history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # --- Welcome area (only when empty) — compact, centered above chat input ---
        if not history:
            st.markdown(
                '<div class="welcome-container">'
                '<div class="welcome-tagline">Your startup\'s AI memory. Ask anything.</div>'
                '<div class="welcome-emphasis">Chat \u00b7 Ingest \u00b7 Track \u00b7 Challenge</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            # Suggestion chips — small centered buttons, brain-aware
            active_brain = st.session_state.get("active_brain", "pitch")
            if active_brain == "ops":
                # Ops-relevant chips
                _, sc1, sc2, sc3, sc4, _ = st.columns([1.5, 1, 1, 1, 1, 1.5])
                with sc1:
                    if st.button("Open hypotheses", key="quick_hypotheses"):
                        _handle_quick_action("What are our open hypotheses?", "general")
                        return
                with sc2:
                    if st.button("Key risks", key="quick_risks"):
                        _handle_quick_action("What are our key risks?", "general")
                        return
                with sc3:
                    if st.button("Recent contacts", key="quick_contacts"):
                        _handle_quick_action("Who are our recent contacts?", "general")
                        return
                with sc4:
                    if st.button("Open questions", key="quick_ops_questions"):
                        _handle_quick_action("What are our open questions?", "general")
                        return
            else:
                # Pitch-relevant chips
                _, sc1, sc2, sc3, sc4, _ = st.columns([1.5, 1, 1, 1, 1, 1.5])
                with sc1:
                    if st.button("Current state", key="quick_state"):
                        _handle_quick_action("What's our current state?", "current_state")
                        return
                with sc2:
                    if st.button("Open questions", key="quick_questions"):
                        _handle_quick_action("What are our open questions?", "general")
                        return
                with sc3:
                    if st.button("Recent changes", key="quick_changes"):
                        _handle_quick_action("What are the recent changes?", "historical")
                        return
                with sc4:
                    if st.button("Challenge me", key="quick_challenge"):
                        _handle_quick_action("Challenge our current assumptions. What are we missing?", "challenge")
                        return

        # Quick command chips — only when top-level brain is Ops (notes/hypotheses/contacts are Ops features)
        if st.session_state.get("active_brain", "pitch") == "ops":
            _render_quick_command_panel()
        else:
            st.caption("Switch to Ops Brain to log notes, hypotheses, and contacts.")

    # Book framework upload — outside frame, near the bottom
    with st.expander("Upload .md for cross-check", expanded=False):
        uploaded_file = st.file_uploader(
            "Choose file", type=["md"], key="book_upload",
            label_visibility="collapsed",
        )
        if uploaded_file is not None and uploaded_file.name != st.session_state.get("book_crosscheck_filename", ""):
            try:
                content = uploaded_file.read().decode("utf-8")
            except UnicodeDecodeError:
                st.error("Could not read file — only UTF-8 encoded .md files are supported.")
                content = None
            if content is not None:
                st.session_state.book_crosscheck_content = content
                st.session_state.book_crosscheck_filename = uploaded_file.name

    if st.session_state.get("book_crosscheck_content"):
        filename = st.session_state.get("book_crosscheck_filename", "file")
        char_count = len(st.session_state.book_crosscheck_content)
        col_info, col_clear = st.columns([4, 1])
        with col_info:
            st.info(f"Book loaded: {filename} ({char_count} chars) — Ask me to cross-check your model against this.")
        with col_clear:
            if st.button("Clear", key="clear_book"):
                st.session_state.book_crosscheck_content = ""
                st.session_state.book_crosscheck_filename = ""
                st.rerun()

    # Chat input — the primary interaction point
    user_input = st.chat_input("Ask anything about your startup...")

    # Pick up pending quick command if no direct input
    pending_cmd = st.session_state.pop("_quick_cmd_pending", None)
    if not user_input and pending_cmd:
        user_input = pending_cmd

    if user_input:
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)

        # Check if user pasted a transcript
        if _is_likely_transcript(user_input):
            add_message("user", user_input[:200] + "... [transcript detected, use Ingest button]")
            response = (
                "That looks like a session transcript or summary. "
                "Would you like to run it through the ingestion pipeline to extract and store the key claims? "
                "Click **Ingest Session** in the top bar to get started."
            )
            with st.chat_message("assistant"):
                st.markdown(response)
            add_message("assistant", response)
            st.rerun()
            return

        add_message("user", user_input)

        # Prefix commands (note:/contact:/hypothesis:/validated:/invalidated:) are ops-only
        active_brain = st.session_state.get("active_brain", "pitch")

        # Handle quick notes — lightweight doc update, no full pipeline
        if active_brain == "ops" and _is_quick_note(user_input):
            note_text = _strip_quick_note_prefix(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Noting..."):
                    response = _apply_quick_note(note_text)
                st.markdown(response)
            add_message("assistant", response)
            st.rerun()
            return

        # Handle contact notes
        if active_brain == "ops" and _is_contact(user_input):
            contact_text = _strip_contact_prefix(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Updating contacts..."):
                    response = _apply_contact(contact_text)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
            st.rerun()
            return

        # Handle hypothesis tracking
        if active_brain == "ops" and _is_hypothesis(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Tracking hypothesis..."):
                    response = _apply_hypothesis(user_input)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
            st.rerun()
            return

        # Handle hypothesis status updates
        if active_brain == "ops" and _is_hypothesis_status_update(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Updating hypothesis..."):
                    response = _apply_hypothesis_status_update(user_input)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
            st.rerun()
            return

        # If user typed an ops prefix in pitch mode, block it early (don't waste API cost)
        if active_brain != "ops":
            if _is_quick_note(user_input) or _is_contact(user_input) or _is_hypothesis(user_input) or _is_hypothesis_status_update(user_input):
                with st.chat_message("assistant"):
                    st.info("Quick commands like note: and hypothesis: work in Ops Brain. Switch the brain toggle at the top and try again.")
                add_message("assistant", "Quick commands like note: and hypothesis: work in Ops Brain. Switch the brain toggle at the top and try again.")
                st.rerun()
                return

        # Handle direct corrections — apply immediately, zero pushback
        if _is_direct_correction(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Updating..."):
                    response = _apply_direct_correction(user_input)
                st.markdown(response)
            add_message("assistant", response)
            # Invalidate sidebar cache so it reflects the update
            invalidate_sidebar()
            st.rerun()
            return

        # Normal query — classify and route
        query_type = _classify_query(user_input)
        with st.chat_message("assistant"):
            response = st.write_stream(_call_claude_stream(user_input, query_type))

        # Don't pollute conversation history with error messages
        if response and not str(response).startswith("Error: "):
            add_message("assistant", response)
        elif response:
            # Show error but don't save to history (would pollute future Claude context)
            add_message("assistant", "I had trouble responding. Please try again.")
        st.rerun()


def render_contradiction_resolution():
    """
    Displays the contradiction resolution UI per SPEC Section 5.5.
    Called when mode='resolving_contradiction'.
    """
    contradictions = st.session_state.get("contradictions", [])
    idx = st.session_state.get("contradiction_index", 0)

    if idx >= len(contradictions):
        # All contradictions resolved — move to done
        set_mode("done")
        st.rerun()
        return

    contradiction = contradictions[idx]
    total = len(contradictions)

    from app.components.progress import render_step_indicator
    render_step_indicator(3)

    st.header(f"Contradiction {idx + 1} of {total}")
    st.progress((idx + 1) / total)

    severity = contradiction.get("severity", "Notable")
    severity_cls = "critical" if severity == "Critical" else "notable"
    import html as _html_mod
    existing_position = html.escape(_html_mod.unescape(contradiction.get("existing_position", "Not found")))
    new_claim_display = html.escape(_html_mod.unescape(contradiction.get("new_claim", "Not found")))
    tension = _html_mod.unescape(contradiction.get("tension_description", "") or contradiction.get("evidence_summary", ""))
    section = contradiction.get("existing_section", "")

    severity_html = (
        f'<div class="severity-{severity_cls}">'
        f'<strong>Severity: {html.escape(severity)}</strong>'
    )
    if section:
        severity_html += f'<br><em>Section: {html.escape(section)}</em>'
    severity_html += (
        f'<br><br><strong>What the document says:</strong> {existing_position}'
        f'<br><br><strong>What you just said:</strong> {new_claim_display}'
    )
    if tension:
        severity_html += f'<br><br><strong>Tension:</strong> {html.escape(tension)}'
    severity_html += '</div>'
    st.markdown(severity_html, unsafe_allow_html=True)

    # Check if this is a revisited rejection
    if contradiction.get("is_revisited_rejection"):
        st.warning("Note: This contradicts a previously dismissed contradiction.")

    st.markdown("---")

    # Pass 3 deep analysis if available
    consistency_results = st.session_state.get("consistency_results", {})
    if consistency_results:
        pass3 = consistency_results.get("pass3")
        if pass3 and pass3.get("analyses"):
            c_id = contradiction.get("id", "")
            for analysis in pass3["analyses"]:
                if analysis.get("contradiction_id") == c_id:
                    with st.expander("Deep Analysis", expanded=True):
                        headline = analysis.get("headline", "")
                        if headline:
                            st.markdown(f"> {_escape_latex(headline)}")
                        implications = analysis.get("downstream_implications", "")
                        if implications:
                            st.markdown(f"> **Downstream implications:** {_escape_latex(implications)}")
                        observation = analysis.get("analyst_observation", "")
                        if observation:
                            st.info(_escape_latex(observation))
                    break

    # Resolution buttons
    new_claim_text = contradiction.get("new_claim", "the new position")
    col_update, col_keep, col_explain = st.columns(3)

    with col_update:
        if st.button("Update to new", type="primary", use_container_width=True, key=f"resolve_update_{idx}",
                      help="Overwrite the document with the new claim"):
            with st.spinner("Updating document..."):
                success = _resolve_contradiction_deferred(contradiction, "update", new_claim_text, "")
            if success:
                _advance_contradiction()

    with col_keep:
        if st.button("Keep current", use_container_width=True, key=f"resolve_keep_{idx}",
                      help="Keep the document as-is, ignore the new claim"):
            with st.spinner("Logging decision..."):
                success = _resolve_contradiction_deferred(contradiction, "keep", "", "")
            if success:
                _advance_contradiction()

    with col_explain:
        if st.button("Let me explain", use_container_width=True, key=f"resolve_explain_{idx}",
                      help="Provide context before updating"):
            st.session_state[f"show_explain_{idx}"] = True
            st.rerun()

    # Explanation text input
    if st.session_state.get(f"show_explain_{idx}", False):
        st.markdown("---")
        explanation = st.text_area(
            "Explain the change",
            key=f"explanation_{idx}",
            placeholder="Explain why this changed and what you want the updated position to be...",
        )
        if st.button("Submit explanation", key=f"submit_explain_{idx}", type="primary"):
            if explanation.strip():
                with st.spinner("Updating document with your explanation..."):
                    success = _resolve_contradiction_deferred(contradiction, "explain", new_claim_text, explanation.strip())
                if success:
                    _advance_contradiction()
            else:
                st.error("Please enter an explanation before submitting.")

    # Cancel button — escape hatch to abandon ingestion mid-resolution (two-click confirmation)
    st.markdown("---")
    if st.session_state.get("_confirm_cancel_ingestion", False):
        st.warning("This will discard all progress. Are you sure?")
        confirm_col1, confirm_col2 = st.columns(2)
        with confirm_col1:
            if st.button("Yes, cancel everything", key=f"confirm_cancel_{idx}", type="primary"):
                st.session_state._confirm_cancel_ingestion = False
                writer = st.session_state.get("deferred_writer")
                if writer is not None:
                    try:
                        writer.rollback()
                    except Exception as e:
                        logging.error("Rollback during cancel failed: %s", e)
                from app.state import reset_ingestion
                reset_ingestion()
                st.rerun()
        with confirm_col2:
            if st.button("No, continue", key=f"cancel_cancel_{idx}"):
                st.session_state._confirm_cancel_ingestion = False
                st.rerun()
    else:
        if st.button("Cancel Ingestion", key=f"cancel_resolution_{idx}"):
            st.session_state._confirm_cancel_ingestion = True
            st.rerun()


def _resolve_contradiction_deferred(contradiction: dict, action: str, new_claim: str, explanation: str):
    """
    Apply a contradiction resolution using the DeferredWriter (in-memory only).
    All disk/MongoDB/git writes are deferred to batch_commit().
    """
    writer = st.session_state.get("deferred_writer")
    if writer is None:
        logging.warning("No deferred_writer in session state — falling back to immediate contradiction resolution.")
        try:
            _resolve_contradiction(contradiction, action, new_claim, explanation)
        except Exception as e:
            logging.error("Fallback contradiction resolution failed: %s", e)
            st.warning("Could not apply resolution. Please try again.")
            return False
        return True

    try:
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        section = contradiction.get("existing_section", "Unknown Section")
        tension = contradiction.get("tension_description", "")
        participants = st.session_state.get("ingestion_participants", "Founders")
        idx = st.session_state.get("contradiction_index", 0)

        if action == "update":
            new_info = (
                f"Contradiction resolved ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved — updated {section} ({date_str})"
            doc_result = writer.apply_document_update_deferred(new_info, update_reason=reason)
            if not doc_result.get("success"):
                logging.error("Deferred resolution update failed: %s", doc_result.get("message"))
                st.warning(f"Could not apply resolution: {doc_result.get('message', 'unknown error')}. Please try again.")
                return False

            if doc_result.get("changes_applied", 0) > 0:
                decision_entry = (
                    f"### {date_str} — Resolved: {section}\n"
                    f"**Decision:** Updated to: {new_claim}\n"
                    f"**Alternatives considered:** Keep previous position\n"
                    f"**Why alternatives were rejected:** New information contradicted existing position. {tension}\n"
                    f"**Context:** Contradiction resolution during ingestion.\n"
                    f"**Participants:** {participants}"
                )
                writer.apply_decision_log_deferred(decision_entry)

        elif action == "keep":
            dismissed_entry = (
                f"- [{date_str}] Dismissed: \"{contradiction.get('new_claim', '')}\"\n"
                f"  Kept: {contradiction.get('existing_position', '')}\n"
                f"  Section: {section}"
            )
            writer.apply_dismissed_deferred(dismissed_entry)

        else:  # explain
            new_info = (
                f"Contradiction resolved with explanation ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Explanation: {explanation}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved with explanation — {section} ({date_str})"
            doc_result = writer.apply_document_update_deferred(new_info, update_reason=reason)
            if not doc_result.get("success"):
                logging.error("Deferred resolution explain failed: %s", doc_result.get("message"))
                st.warning(f"Could not apply resolution: {doc_result.get('message', 'unknown error')}. Please try again.")
                return False

            if doc_result.get("changes_applied", 0) > 0:
                decision_entry = (
                    f"### {date_str} — Resolved: {section}\n"
                    f"**Decision:** Updated to: {new_claim}\n"
                    f"**Alternatives considered:** Keep previous position\n"
                    f"**Why alternatives were rejected:** {explanation}\n"
                    f"**Context:** Contradiction resolution during ingestion.\n"
                    f"**Participants:** {participants}"
                )
                writer.apply_decision_log_deferred(decision_entry)

        writer.record_contradiction_resolution(idx, action, new_claim, explanation)
        writer.save_checkpoint()
        return True

    except Exception as e:
        logging.error("Deferred resolution failed: %s", e)
        st.warning("Could not apply resolution. Please try again.")
        return False


def _resolve_contradiction(contradiction: dict, action: str, new_claim: str, explanation: str):
    """
    Apply a contradiction resolution to the living document.
    action: "update" | "keep" | "explain"

    - "update" / "explain": calls update_document() (which manages its own doc lock)
      AND then separately locks to add a Decision Log entry.
    - "keep": does NOT call update_document(); locks to add a Dismissed Contradiction entry.
    """
    try:
        from services.document_updater import (
            update_document, read_living_document, write_living_document,
            _add_decision, _add_dismissed, _git_commit,
        )
        from services.mongo_client import upsert_living_document
        from services.ingestion_lock import acquire_doc_lock, release_doc_lock
        from datetime import datetime, timezone

        brain = st.session_state.get("active_brain", "pitch")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        section = contradiction.get("existing_section", "Unknown Section")
        tension = contradiction.get("tension_description", "")

        participants = st.session_state.get("ingestion_participants", "Founders")

        if action == "update":
            new_info = (
                f"Contradiction resolved ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved — updated {section} ({date_str})"
            # update_document manages its own doc lock internally
            result = update_document(new_info, update_reason=reason, brain=brain)
            if not result or not result.get("success"):
                logging.error("Contradiction resolution document update failed: %s", result.get("message", "unknown") if result else "no result")
                st.warning("Could not update document. Please try again.")
                return  # Don't write Decision Log for a failed update

            # Separate lock scope for the Decision Log entry
            lock_id = acquire_doc_lock(timeout_seconds=60)
            if not lock_id:
                st.warning("Document updated but could not add Decision Log entry — lock busy.")
                return
            try:
                doc = read_living_document(brain=brain)
                decision_entry = (
                    f"### {date_str} — Resolved: {section}\n"
                    f"**Decision:** Updated to: {new_claim}\n"
                    f"**Alternatives considered:** Keep previous position\n"
                    f"**Why alternatives were rejected:** New information contradicted existing position. {tension}\n"
                    f"**Context:** Contradiction resolution during ingestion.\n"
                    f"**Participants:** {participants}"
                )
                doc = _add_decision(doc, decision_entry, brain=brain)
                # Mirror to MongoDB first (source of truth on Render's ephemeral FS)
                upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": reason}, brain=brain)
                write_living_document(doc, brain=brain)
                _git_commit(f"Decision log: {reason}", brain=brain)
            finally:
                release_doc_lock(lock_id)

        elif action == "keep":
            # No content update — just add a Dismissed Contradiction entry
            lock_id = acquire_doc_lock(timeout_seconds=60)
            if not lock_id:
                st.warning("Document is being updated by another process. Try again shortly.")
                return
            try:
                doc = read_living_document(brain=brain)
                dismissed_entry = (
                    f"- [{date_str}] Dismissed: \"{contradiction.get('new_claim', '')}\"\n"
                    f"  Kept: {contradiction.get('existing_position', '')}\n"
                    f"  Section: {section}"
                )
                doc = _add_dismissed(doc, dismissed_entry, brain=brain)
                # Mirror to MongoDB first (source of truth on Render's ephemeral FS)
                upsert_living_document(doc, metadata={"last_updated": date_str}, brain=brain)
                write_living_document(doc, brain=brain)
                _git_commit(f"Dismissed contradiction in {section} ({date_str})", brain=brain)
            finally:
                release_doc_lock(lock_id)

        else:  # explain
            new_info = (
                f"Contradiction resolved with explanation ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Explanation: {explanation}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved with explanation — {section} ({date_str})"
            # update_document manages its own doc lock internally
            result = update_document(new_info, update_reason=reason, brain=brain)
            if not result or not result.get("success"):
                logging.error("Contradiction resolution document update failed: %s", result.get("message", "unknown") if result else "no result")
                st.warning("Could not update document. Please try again.")
                return  # Don't write Decision Log for a failed update

            # Separate lock scope for the Decision Log entry
            lock_id = acquire_doc_lock(timeout_seconds=60)
            if not lock_id:
                st.warning("Document updated but could not add Decision Log entry — lock busy.")
                return
            try:
                doc = read_living_document(brain=brain)
                decision_entry = (
                    f"### {date_str} — Resolved: {section}\n"
                    f"**Decision:** Updated to: {new_claim}\n"
                    f"**Alternatives considered:** Keep previous position\n"
                    f"**Why alternatives were rejected:** {explanation}\n"
                    f"**Context:** Contradiction resolution during ingestion.\n"
                    f"**Participants:** {participants}"
                )
                doc = _add_decision(doc, decision_entry, brain=brain)
                # Mirror to MongoDB first (source of truth on Render's ephemeral FS)
                upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": reason}, brain=brain)
                write_living_document(doc, brain=brain)
                _git_commit(f"Decision log: {reason}", brain=brain)
            finally:
                release_doc_lock(lock_id)

    except Exception as e:
        logging.error("Contradiction resolution failed: %s", e)
        st.warning("Could not update document. Please try again.")


def _advance_contradiction():
    """Move to the next contradiction, or to done mode if all resolved."""
    idx = st.session_state.get("contradiction_index", 0)
    contradictions = st.session_state.get("contradictions", [])

    # Clear explain state for this index
    st.session_state.pop(f"show_explain_{idx}", None)
    st.session_state.pop(f"explanation_{idx}", None)

    next_idx = idx + 1
    if next_idx >= len(contradictions):
        # All done
        invalidate_sidebar()  # Invalidate sidebar cache
        set_mode("done")
    else:
        st.session_state.contradiction_index = next_idx

    st.rerun()
