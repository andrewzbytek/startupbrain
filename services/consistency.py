"""
Multi-pass consistency checking engine for Startup Brain.
Section 5 of the SPEC — this is the #1 priority feature.

Pass 1 (Sonnet): Wide net — find ALL potential contradictions
Pass 2 (Sonnet): Severity filter — rank Critical/Notable/Minor, remove dismissed
Pass 3 (Opus): Deep analysis — ONLY if Pass 2 found Critical contradictions
"""

import re
import logging

from services.claude_client import extract_xml_tag as _extract_tag


def _is_api_error(result: dict) -> bool:
    """Check if an API call result indicates an error."""
    text = result.get("text", "")
    return text.startswith("AI service temporarily unavailable") or text.startswith("Error:")

# When claim count exceeds this, time-based retrieval starts missing relevant evidence.
# At this point, semantic vector search (Atlas M10+ with autoEmbed) becomes worth it.
RAG_UPGRADE_CLAIM_THRESHOLD = 200


def read_living_document(brain: str = "pitch") -> str:
    """Read and return the current living document content."""
    from services.document_updater import read_living_document as _read_doc
    return _read_doc(brain=brain)


def _claims_to_xml(claims: list) -> str:
    """Convert list of claim dicts to XML for prompts."""
    from services.claude_client import escape_xml
    parts = ["<new_claims>"]
    for claim in claims:
        parts.append("  <claim>")
        parts.append(f"    <claim_text>{escape_xml(claim.get('claim_text', ''))}</claim_text>")
        parts.append(f"    <claim_type>{escape_xml(claim.get('claim_type', 'claim'))}</claim_type>")
        parts.append(f"    <confidence>{escape_xml(claim.get('confidence', 'definite'))}</confidence>")
        if claim.get("who_said_it"):
            parts.append(f"    <who_said_it>{escape_xml(claim['who_said_it'])}</who_said_it>")
        parts.append("  </claim>")
    parts.append("</new_claims>")
    return "\n".join(parts)


def parse_contradictions(raw_output: str) -> list:
    """
    Parse XML contradiction output from Pass 1 into a list of dicts.

    Returns list of: {id, new_claim, existing_position, existing_section,
                       tension_description, is_revisited_rejection}
    """
    contradictions = []
    pattern = re.compile(
        r"<contradiction>(.*?)</contradiction>",
        re.DOTALL,
    )
    for match in pattern.finditer(raw_output):
        block = match.group(1)
        contradiction = {
            "id": _extract_tag(block, "id"),
            "new_claim": _extract_tag(block, "new_claim"),
            "existing_position": _extract_tag(block, "existing_position"),
            "existing_section": _extract_tag(block, "existing_section"),
            "tension_description": _extract_tag(block, "tension_description"),
            "is_revisited_rejection": _extract_tag(block, "is_revisited_rejection") == "true",
        }
        if contradiction["id"]:
            contradictions.append(contradiction)
    return contradictions


def _parse_pass2_output(raw_output: str) -> dict:
    """
    Parse Pass 2 XML output.

    Returns dict: {
        retained: list of contradiction dicts with severity,
        has_critical: bool,
        total_retained: int,
        filtered_out: list
    }
    """
    retained = []
    pattern = re.compile(
        r"<contradiction>(.*?)</contradiction>",
        re.DOTALL,
    )
    for match in pattern.finditer(raw_output):
        block = match.group(1)
        item = {
            "id": _extract_tag(block, "id"),
            "severity": _extract_tag(block, "severity"),
            "new_claim": _extract_tag(block, "new_claim"),
            "existing_position": _extract_tag(block, "existing_position"),
            "existing_section": _extract_tag(block, "existing_section"),
            "evidence_summary": _extract_tag(block, "evidence_summary"),
            "is_revisited_rejection": _extract_tag(block, "is_revisited_rejection") == "true",
        }
        if item["id"]:
            retained.append(item)

    has_critical_match = re.search(r"<has_critical>(.*?)</has_critical>", raw_output)
    has_critical = has_critical_match and has_critical_match.group(1).strip() == "true"

    filtered_out = []
    for m in re.finditer(r"<item>(.*?)</item>", raw_output, re.DOTALL):
        block = m.group(1)
        filtered_out.append({
            "id": _extract_tag(block, "id"),
            "reason": _extract_tag(block, "reason"),
        })

    return {
        "retained": retained,
        "has_critical": bool(has_critical),
        "total_retained": len(retained),
        "filtered_out": filtered_out,
        "raw": raw_output,
    }


def _parse_pass3_output(raw_output: str) -> list:
    """
    Parse Pass 3 XML output into list of analysis dicts.
    """
    analyses = []
    pattern = re.compile(r"<analysis>(.*?)</analysis>", re.DOTALL)
    for match in pattern.finditer(raw_output):
        block = match.group(1)
        analysis = {
            "contradiction_id": _extract_tag(block, "contradiction_id"),
            "headline": _extract_tag(block, "headline"),
            "downstream_implications": _extract_tag(block, "downstream_implications"),
            "analyst_observation": _extract_tag(block, "analyst_observation"),
            "resolution_options": [],
        }
        # Extract original and new position summaries
        orig_block = re.search(r"<original_position>(.*?)</original_position>", block, re.DOTALL)
        if orig_block:
            analysis["original_position"] = {
                "summary": _extract_tag(orig_block.group(1), "summary"),
                "evidence": _extract_tag(orig_block.group(1), "evidence"),
                "original_rationale": _extract_tag(orig_block.group(1), "original_rationale"),
            }
        new_block = re.search(r"<new_position>(.*?)</new_position>", block, re.DOTALL)
        if new_block:
            analysis["new_position"] = {
                "summary": _extract_tag(new_block.group(1), "summary"),
                "evidence": _extract_tag(new_block.group(1), "evidence"),
                "possible_reasons_for_change": _extract_tag(new_block.group(1), "possible_reasons_for_change"),
            }
        for opt in re.finditer(r"<option>(.*?)</option>", block, re.DOTALL):
            ob = opt.group(1)
            analysis["resolution_options"].append({
                "label": _extract_tag(ob, "label"),
                "description": _extract_tag(ob, "description"),
            })
        analyses.append(analysis)
    return analyses


def pass1_wide_net(living_doc: str, claims: list, session_type: str = "") -> dict:
    """
    Pass 1: Find ALL potential contradictions using Sonnet.
    Returns dict with: contradictions (list), total_found (int), raw (str)
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_template = load_prompt("consistency_pass1")
    claims_xml = _claims_to_xml(claims)

    prompt = f"""{prompt_template}

<consistency_input>
  <session_type>{escape_xml(session_type)}</session_type>
  <living_document>{escape_xml(living_doc)}</living_document>
  {claims_xml}
</consistency_input>"""

    result = call_sonnet(prompt, task_type="consistency_pass1")
    if _is_api_error(result):
        logging.error("Consistency Pass 1 API call failed: %s", result["text"])
        return {"contradictions": [], "total_found": 0, "raw": result["text"], "api_error": True}
    raw = result["text"]
    contradictions = parse_contradictions(raw)

    total_match = re.search(r"<total_found>(\d+)</total_found>", raw)
    total_found = int(total_match.group(1)) if total_match else len(contradictions)

    return {"contradictions": contradictions, "total_found": total_found, "raw": raw}


def pass2_severity_filter(pass1_results: dict, living_doc: str, session_type: str = "") -> dict:
    """
    Pass 2: Rate severity, filter Minor, remove dismissed.
    Returns dict from _parse_pass2_output.
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_template = load_prompt("consistency_pass2")

    # Build pass1 XML from the filtered contradictions list (not raw output,
    # which still contains dismissed items that were filtered by check_dismissed)
    filtered_contradictions = pass1_results.get("contradictions", [])
    pass1_xml_parts = [f"<total_found>{len(filtered_contradictions)}</total_found>"]
    for c in filtered_contradictions:
        pass1_xml_parts.append("<contradiction>")
        pass1_xml_parts.append(f"  <id>{escape_xml(c.get('id', ''))}</id>")
        pass1_xml_parts.append(f"  <new_claim>{escape_xml(c.get('new_claim', ''))}</new_claim>")
        pass1_xml_parts.append(f"  <existing_position>{escape_xml(c.get('existing_position', ''))}</existing_position>")
        pass1_xml_parts.append(f"  <existing_section>{escape_xml(c.get('existing_section', ''))}</existing_section>")
        pass1_xml_parts.append(f"  <tension_description>{escape_xml(c.get('tension_description', ''))}</tension_description>")
        pass1_xml_parts.append(f"  <is_revisited_rejection>{str(c.get('is_revisited_rejection', False)).lower()}</is_revisited_rejection>")
        pass1_xml_parts.append("</contradiction>")
    pass1_filtered_xml = "<pass1_output>\n" + "\n".join(pass1_xml_parts) + "\n</pass1_output>"

    prompt = f"""{prompt_template}

<pass2_input>
  <session_type>{escape_xml(session_type)}</session_type>
  <living_document>{escape_xml(living_doc)}</living_document>
  <pass1_results>{pass1_filtered_xml}</pass1_results>
</pass2_input>"""

    result = call_sonnet(prompt, task_type="consistency_pass2")
    if _is_api_error(result):
        logging.error("Consistency Pass 2 API call failed: %s", result["text"])
        return {"retained": [], "has_critical": False, "total_retained": 0, "filtered_out": [], "raw": result["text"], "api_error": True}
    return _parse_pass2_output(result["text"])


def check_rag_health(brain: str = "pitch") -> dict:
    """
    Check whether time-based RAG retrieval is still adequate.

    Returns dict with:
        claim_count: int — total claims in MongoDB
        needs_upgrade: bool — True if claim count exceeds threshold
        threshold: int — the threshold value
        message: str — human-readable status
    """
    from services.mongo_client import count_documents

    claim_count = count_documents("claims", {"brain": brain})
    needs_upgrade = claim_count >= RAG_UPGRADE_CLAIM_THRESHOLD

    if needs_upgrade:
        message = (
            f"You have {claim_count} claims (threshold: {RAG_UPGRADE_CLAIM_THRESHOLD}). "
            f"Time-based retrieval only checks the 50 most recent claims — older evidence may be missed. "
            f"Upgrade to Atlas M10+ ($57/mo) to enable vector search with Voyage AI automated embedding."
        )
    else:
        remaining = RAG_UPGRADE_CLAIM_THRESHOLD - claim_count
        message = f"{claim_count} / {RAG_UPGRADE_CLAIM_THRESHOLD} claims. ~{remaining} more before semantic search is recommended."

    return {
        "claim_count": claim_count,
        "needs_upgrade": needs_upgrade,
        "threshold": RAG_UPGRADE_CLAIM_THRESHOLD,
        "message": message,
    }


def _get_rag_evidence(claims: list, brain: str = "pitch") -> list:
    """
    Retrieve RAG evidence from MongoDB for contradiction analysis.
    Tries Atlas Vector Search first (semantic), falls back to time-based retrieval.
    Returns list of evidence dicts: {source_date, source_type, relevant_excerpt}
    """
    from services.mongo_client import get_claims, get_sessions, vector_search_text

    # Try vector search first (semantic retrieval via Atlas automated embedding)
    try:
        query_text = " ".join(c.get("claim_text", "") for c in claims if c.get("claim_text"))
        if query_text:
            results = vector_search_text(
                "claims", query_text, "claims_vector_index", limit=10,
                filter_query={"brain": brain},
            )
            if results:
                evidence = []
                for r in results:
                    created = r.get("created_at", "")
                    date_str = str(created)[:10] if created else ""
                    evidence.append({
                        "source_date": date_str,
                        "source_type": r.get("source_type", "session"),
                        "relevant_excerpt": r.get("claim_text", ""),
                    })
                return evidence
    except Exception as e:
        logging.debug("Vector search unavailable, using time-based fallback: %s", e)

    # Fallback: time-based retrieval
    evidence = []

    # Fetch recent claims from MongoDB to provide evidence context
    recent_claims = get_claims(limit=10, brain=brain)
    for claim in recent_claims:
        _ca = claim.get("created_at", "")
        evidence.append({
            "source_date": _ca[:10] if isinstance(_ca, str) else (_ca.strftime("%Y-%m-%d") if hasattr(_ca, 'strftime') else ""),
            "source_type": claim.get("source_type", "session"),
            "relevant_excerpt": claim.get("claim_text", ""),
        })

    # Fetch recent sessions for additional context
    recent_sessions = get_sessions(limit=5, brain=brain)
    for session in recent_sessions[:3]:
        _ca = session.get("created_at", "")
        evidence.append({
            "source_date": _ca[:10] if isinstance(_ca, str) else (_ca.strftime("%Y-%m-%d") if hasattr(_ca, 'strftime') else ""),
            "source_type": session.get("metadata", {}).get("session_type", "session"),
            "relevant_excerpt": (session.get("summary") or session.get("transcript") or "")[:500],
        })

    # Log warning if over threshold and using fallback
    try:
        from services.mongo_client import count_documents
        total = count_documents("claims", {"brain": brain})
        if total >= RAG_UPGRADE_CLAIM_THRESHOLD:
            logging.warning(
                "RAG using time-based fallback with %d claims (threshold: %d). "
                "Consistency checks may miss older relevant evidence.",
                total, RAG_UPGRADE_CLAIM_THRESHOLD,
            )
    except Exception as e:
        logging.warning("Could not check RAG claim count: %s", e)

    return evidence


def _format_rag_evidence(evidence: list) -> str:
    """Format RAG evidence list as XML for Pass 3 prompt."""
    from services.claude_client import escape_xml
    parts = ["<rag_evidence>"]
    for ev in evidence:
        parts.append("  <evidence_item>")
        parts.append(f"    <source_date>{escape_xml(ev.get('source_date', ''))}</source_date>")
        parts.append(f"    <source_type>{escape_xml(ev.get('source_type', 'session'))}</source_type>")
        parts.append(f"    <relevant_excerpt>{escape_xml(ev.get('relevant_excerpt', ''))}</relevant_excerpt>")
        parts.append("  </evidence_item>")
    parts.append("</rag_evidence>")
    return "\n".join(parts)


def pass3_deep_analysis(critical_items: list, living_doc: str, rag_evidence: list) -> dict:
    """
    Pass 3: Deep analysis using Opus. ONLY called if Pass 2 found Critical contradictions.
    Returns dict with: analyses (list), raw (str)
    """
    from services.claude_client import call_opus, load_prompt

    prompt_template = load_prompt("consistency_pass3")

    from services.claude_client import escape_xml

    # Build critical contradictions XML
    critical_xml_parts = ["<critical_contradictions>"]
    for item in critical_items:
        critical_xml_parts.append("  <contradiction>")
        for k, v in item.items():
            critical_xml_parts.append(f"    <{k}>{escape_xml(str(v))}</{k}>")
        critical_xml_parts.append("  </contradiction>")
    critical_xml_parts.append("</critical_contradictions>")
    critical_xml = "\n".join(critical_xml_parts)

    rag_xml = _format_rag_evidence(rag_evidence)

    prompt = f"""{prompt_template}

<pass3_input>
  <living_document>{escape_xml(living_doc)}</living_document>
  {critical_xml}
  {rag_xml}
</pass3_input>"""

    result = call_opus(prompt, task_type="consistency_pass3")
    if _is_api_error(result):
        logging.error("Consistency Pass 3 API call failed: %s", result["text"])
        return {"analyses": [], "raw": result["text"], "api_error": True}
    raw = result["text"]
    analyses = _parse_pass3_output(raw)

    return {"analyses": analyses, "raw": raw}


def check_dismissed(contradictions: list, living_doc: str) -> list:
    """
    Filter contradictions that match entries in the Dismissed Contradictions section.
    Splits the section into individual entries (by ### headers) and checks each one
    separately, so a contradiction is only dismissed if 40%+ word overlap with a
    single entry (not the combined vocabulary of all entries).
    Returns the filtered list (dismissed entries removed).
    """
    dismissed_section = ""
    match = re.search(r"## Dismissed Contradictions\n(.*?)(\n## |\Z)", living_doc, re.DOTALL)
    if match:
        dismissed_section = match.group(1).strip()

    if not dismissed_section or dismissed_section.lower() in ("", "[no dismissed contradictions]"):
        return contradictions

    # Split dismissed section into individual entries by ### headers
    entries = re.split(r'\n(?=### )', dismissed_section)
    # Build word sets for each individual entry
    entry_word_sets = []
    for entry in entries:
        entry = entry.strip()
        if entry:
            entry_words = set(re.findall(r'\b\w+\b', entry.lower()))
            if entry_words:
                entry_word_sets.append(entry_words)

    if not entry_word_sets:
        return contradictions

    filtered = []
    for c in contradictions:
        claim_text = c.get("new_claim", "").lower()
        words = [w for w in claim_text.split() if len(w) > 4]
        if len(words) == 0:
            filtered.append(c)
            continue
        # Check against each individual entry — dismissed only if 40%+ overlap with ANY single entry
        is_dismissed = False
        for entry_words in entry_word_sets:
            match_count = sum(1 for w in words if w in entry_words)
            if match_count / len(words) >= 0.4:
                is_dismissed = True
                break
        if not is_dismissed:
            filtered.append(c)

    return filtered


def run_consistency_check(claims: list, session_type: str = "", brain: str = "pitch") -> dict:
    """
    Orchestrate all consistency check passes.

    Args:
        claims: List of confirmed claim dicts from ingestion.

    Returns:
        dict with:
            pass1: raw Pass 1 results
            pass2: Pass 2 results with severity ratings
            pass3: Pass 3 deep analysis (only if Critical found, else None)
            has_contradictions: bool
            has_critical: bool
            summary: human-readable summary string
    """
    if not claims:
        return {
            "pass1": None,
            "pass2": None,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "No claims to check.",
        }

    living_doc = read_living_document(brain=brain)
    if not living_doc:
        return {
            "pass1": None,
            "pass2": None,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "Living document not found — skipping consistency check.",
        }

    # Pass 1
    pass1 = pass1_wide_net(living_doc, claims, session_type=session_type)

    if pass1.get("api_error"):
        return {
            "pass1": pass1,
            "pass2": None,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "Consistency check failed — API error during Pass 1.",
            "api_error": True,
        }

    if pass1["total_found"] == 0:
        return {
            "pass1": pass1,
            "pass2": None,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "No potential contradictions found.",
        }

    # Filter dismissed contradictions before Pass 2
    pass1["contradictions"] = check_dismissed(pass1["contradictions"], living_doc)
    pass1["total_found"] = len(pass1["contradictions"])

    if pass1["total_found"] == 0:
        return {
            "pass1": pass1,
            "pass2": None,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "All potential contradictions were previously dismissed.",
        }

    # Pass 2
    pass2 = pass2_severity_filter(pass1, living_doc, session_type=session_type)

    if pass2.get("api_error"):
        return {
            "pass1": pass1,
            "pass2": pass2,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": "Consistency check failed — API error during severity filtering.",
            "api_error": True,
        }

    if pass2["total_retained"] == 0:
        return {
            "pass1": pass1,
            "pass2": pass2,
            "pass3": None,
            "has_contradictions": False,
            "has_critical": False,
            "summary": f"Pass 1 found {pass1['total_found']} potential contradiction(s), "
                       f"all filtered as Minor or already dismissed.",
        }

    # Pass 3 — only if Critical found
    pass3 = None
    if pass2["has_critical"]:
        critical_items = [c for c in pass2["retained"] if c.get("severity", "") == "Critical"]
        rag_evidence = _get_rag_evidence(claims, brain=brain)
        pass3 = pass3_deep_analysis(critical_items, living_doc, rag_evidence)

    critical_count = sum(1 for c in pass2["retained"] if c.get("severity", "") == "Critical")
    notable_count = sum(1 for c in pass2["retained"] if c.get("severity", "") == "Notable")

    parts = []
    if critical_count:
        parts.append(f"{critical_count} Critical")
    if notable_count:
        parts.append(f"{notable_count} Notable")
    summary = f"Found {', '.join(parts)} contradiction(s) requiring attention."

    return {
        "pass1": pass1,
        "pass2": pass2,
        "pass3": pass3,
        "has_contradictions": True,
        "has_critical": pass2["has_critical"],
        "summary": summary,
    }


def run_audit(num_sessions: int = 10, brain: str = "pitch") -> dict:
    """
    Living document audit (SPEC Section 4.3).
    Retrieves last N sessions, independently assesses Current State, diffs against actual.

    Returns:
        dict with: discrepancies (list), overall_assessment (str), summary_message (str), raw (str)
    """
    if brain != "pitch":
        return {
            "discrepancies": [],
            "overall_assessment": "healthy",
            "summary_message": "Audit is only available for Pitch Brain.",
            "raw": "",
        }

    from services.claude_client import call_sonnet, escape_xml, load_prompt
    from services.mongo_client import get_sessions

    living_doc = read_living_document(brain=brain)
    sessions = get_sessions(limit=num_sessions, brain=brain)

    if not sessions:
        return {
            "discrepancies": [],
            "overall_assessment": "healthy",
            "summary_message": "No sessions found in MongoDB to audit against.",
            "raw": "",
        }

    prompt_template = load_prompt("audit")

    # Format sessions as XML
    sessions_xml_parts = ["<recent_sessions>"]
    for session in sessions:
        sessions_xml_parts.append("  <session>")
        date_str = str(session.get("created_at", ""))[:10]
        sessions_xml_parts.append(f"    <date>{escape_xml(date_str)}</date>")
        session_type = session.get("metadata", {}).get("session_type", "")
        if session_type:
            sessions_xml_parts.append(f"    <session_type>{escape_xml(session_type)}</session_type>")
        transcript = session.get("transcript", session.get("summary", ""))[:2000]
        sessions_xml_parts.append(f"    <transcript>{escape_xml(transcript)}</transcript>")
        sessions_xml_parts.append("  </session>")
    sessions_xml_parts.append("</recent_sessions>")
    sessions_xml = "\n".join(sessions_xml_parts)

    prompt = f"""{prompt_template}

<audit_input>
  <current_document>{escape_xml(living_doc)}</current_document>
  {sessions_xml}
  <audit_period>last {num_sessions} sessions</audit_period>
</audit_input>"""

    result = call_sonnet(prompt, task_type="audit")
    raw = result["text"]

    # Parse audit output
    overall_match = re.search(r"<overall_assessment>(.*?)</overall_assessment>", raw)
    overall = overall_match.group(1).strip() if overall_match else "unknown"

    summary_match = re.search(r"<summary_message>(.*?)</summary_message>", raw, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else raw[:500]

    discrepancies = []
    for m in re.finditer(r"<discrepancy>(.*?)</discrepancy>", raw, re.DOTALL):
        block = m.group(1)
        # Parse evidence citations if present
        citations = []
        evidence_block = re.search(r"<evidence>(.*?)</evidence>", block, re.DOTALL)
        if evidence_block:
            for cit in re.finditer(r"<citation>(.*?)</citation>", evidence_block.group(1), re.DOTALL):
                cb = cit.group(1)
                citations.append({
                    "date": _extract_tag(cb, "date"),
                    "excerpt": _extract_tag(cb, "excerpt"),
                })
        discrepancies.append({
            "type": _extract_tag(block, "type"),
            "section": _extract_tag(block, "section"),
            "document_says": _extract_tag(block, "document_says"),
            "sessions_suggest": _extract_tag(block, "sessions_suggest"),
            "severity": _extract_tag(block, "severity"),
            "suggestion": _extract_tag(block, "suggestion"),
            "evidence": citations,
        })

    return {
        "discrepancies": discrepancies,
        "overall_assessment": overall,
        "summary_message": summary,
        "raw": raw,
    }


def generate_pushback(change_description: str, relevant_decisions: list, session_type: str = "") -> dict:
    """
    Generate informational pushback when a change contradicts prior decisions.
    Always informational, never blocking.

    Args:
        change_description: What the founder wants to change.
        relevant_decisions: List of decision log entry dicts.

    Returns:
        dict with: headline, message, options (list), prior_context, raw
    """
    from services.claude_client import call_sonnet, load_prompt

    prompt_template = load_prompt("pushback")

    from services.claude_client import escape_xml

    # Format decisions as XML
    decisions_xml_parts = ["<relevant_decision_log_entries>"]
    for dec in relevant_decisions:
        decisions_xml_parts.append("  <entry>")
        for k, v in dec.items():
            decisions_xml_parts.append(f"    <{k}>{escape_xml(str(v))}</{k}>")
        decisions_xml_parts.append("  </entry>")
    decisions_xml_parts.append("</relevant_decision_log_entries>")
    decisions_xml = "\n".join(decisions_xml_parts)

    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if session_type:
        context = f"{session_type} — {date_str}. No explanation provided."
    else:
        context = f"Session {date_str}. No explanation provided."

    prompt = f"""{prompt_template}

<pushback_input>
  <proposed_change>{escape_xml(change_description)}</proposed_change>
  {decisions_xml}
  <relevant_changelog_entries/>
  <session_type>{escape_xml(session_type)}</session_type>
  <change_context>{context}</change_context>
</pushback_input>"""

    result = call_sonnet(prompt, task_type="pushback")
    raw = result["text"]

    headline = _extract_tag(raw, "headline")
    message = _extract_tag(raw, "message")

    options = []
    for m in re.finditer(r"<option>(.*?)</option>", raw, re.DOTALL):
        ob = m.group(1)
        options.append({
            "label": _extract_tag(ob, "label"),
            "description": _extract_tag(ob, "description"),
        })

    prior_context_match = re.search(r"<prior_context>(.*?)</prior_context>", raw, re.DOTALL)
    prior_context = {}
    if prior_context_match:
        pc = prior_context_match.group(1)
        prior_context = {
            "date": _extract_tag(pc, "date"),
            "original_position": _extract_tag(pc, "original_position"),
            "original_rationale": _extract_tag(pc, "original_rationale"),
            "source": _extract_tag(pc, "source"),
        }

    return {
        "headline": headline,
        "message": message,
        "options": options,
        "prior_context": prior_context,
        "raw": raw,
    }
