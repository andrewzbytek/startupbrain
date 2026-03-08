"""
Pure parsing functions for the Startup Brain living document.
Extracted from sidebar.py for reuse across dashboard and other components.
"""

import logging
import re
from datetime import date, timedelta


def _normalize_headers(doc: str) -> str:
    """Strip trailing whitespace from header lines to prevent regex mismatches."""
    lines = doc.split('\n')
    normalized = []
    for line in lines:
        if line.lstrip().startswith('#'):
            normalized.append(line.rstrip())
        else:
            normalized.append(line)
    return '\n'.join(normalized)


def _escape_latex(text: str) -> str:
    """Escape dollar signs so Streamlit doesn't render them as LaTeX math."""
    return text.replace("$", "\\$")


def _parse_current_state(doc: str) -> list:
    """
    Parse Current State sections from the living document.
    Returns list of dicts: {name, current_position, changelog_entries}
    """
    doc = _normalize_headers(doc)
    sections = []
    # Find the Current State section
    cs_match = re.search(r"## Current State\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not cs_match:
        return sections

    cs_content = cs_match.group(1)

    # Find all subsections (### headers)
    for m in re.finditer(r"### (.+?)\n(.*?)(?=\n### |\Z)", cs_content, re.DOTALL):
        name = m.group(1).strip()
        body = m.group(2)

        cp_match = re.search(r"\*\*Current position:\*\*(.*?)(?=\*\*Changelog|\Z)", body, re.DOTALL)
        current_position = cp_match.group(1).strip() if cp_match else ""

        cl_match = re.search(r"\*\*Changelog:\*\*(.*?)$", body, re.DOTALL)
        changelog_raw = cl_match.group(1).strip() if cl_match else ""
        changelog_entries = [
            line.lstrip("- ").strip()
            for line in changelog_raw.split("\n")
            if line.strip() and line.strip() != "[Awaiting first session]"
        ]

        sections.append({
            "name": name,
            "current_position": current_position,
            "changelog_entries": changelog_entries,
        })

    return sections


def _parse_recent_changelog(doc: str, limit: int = 8) -> list:
    """
    Collect the most recent changelog entries across all sections.
    Returns list of strings (most recent first).
    """
    doc = _normalize_headers(doc)
    entries = []
    cs_match = re.search(r"## Current State\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not cs_match:
        return entries

    for m in re.finditer(r"### (.+?)\n.*?\*\*Changelog:\*\*(.*?)(?=\n### |\Z)", cs_match.group(1), re.DOTALL):
        section_name = m.group(1).strip()
        changelog_raw = m.group(2).strip()
        for line in changelog_raw.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and line != "[Awaiting first session]":
                entries.append(f"[{section_name}] {line}")

    # Return last N entries (entries are appended chronologically)
    return entries[-limit:][::-1]


def _parse_feedback_themes(doc: str) -> list:
    """
    Parse recurring themes from Feedback Tracker section.
    Returns list of theme strings.
    """
    doc = _normalize_headers(doc)
    themes = []
    ft_match = re.search(r"## Feedback Tracker\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not ft_match:
        return themes

    rt_match = re.search(r"### Recurring Themes\n(.*?)(?=\n### |\Z)", ft_match.group(1), re.DOTALL)
    if rt_match:
        content = rt_match.group(1).strip()
        if content and content != "[No themes identified yet]":
            for line in content.split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line:
                    themes.append(line)
    return themes


def _parse_feedback_by_source(doc: str) -> dict:
    """
    Parse Individual Feedback entries from the Feedback Tracker section.
    Each entry looks like:
      - [DATE] SOURCE_NAME (SOURCE_TYPE): SUMMARY -- Themes: theme1, theme2
    Groups by source type: investor->vc, customer->customer, advisor->advisor.
    Returns dict like {"vc": [...], "customer": [...], "advisor": [...]}.
    Falls back to empty dict on failure.
    """
    result = {"vc": [], "customer": [], "advisor": [], "other": []}
    doc = _normalize_headers(doc)
    try:
        ft_match = re.search(r"## Feedback Tracker\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
        if not ft_match:
            return result

        if_match = re.search(
            r"### Individual Feedback\n(.*?)(?=\n### |\Z)",
            ft_match.group(1),
            re.DOTALL,
        )
        if not if_match:
            return result

        content = if_match.group(1).strip()
        if not content or content == "[No feedback recorded yet]":
            return result

        type_map = {"investor": "vc", "customer": "customer", "advisor": "advisor",
                    "vc": "vc", "prospect": "customer"}

        for line in content.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if not line:
                continue
            # Match pattern: [DATE] NAME (TYPE): SUMMARY
            # Also handles: [DATE] **Name (Org)** — "quote..." format from ops_diff_generate
            m = re.match(
                r"\[.*?\]\s+(?:\*\*)?(\S.*?)\((\w[\w\s]*?)\)(?:\*\*)?[\s:—–-]+(.+)",
                line,
            )
            if m:
                # Try to identify source type from the captured group or line context
                org_or_type = m.group(2).strip().lower()
                summary = m.group(3).strip()
                bucket = type_map.get(org_or_type)
                if not bucket:
                    # Check line content for type keywords
                    lower_line = line.lower()
                    if any(kw in lower_line for kw in ("investor", "vc", "fund", "capital")):
                        bucket = "vc"
                    elif any(kw in lower_line for kw in ("customer", "user", "prospect", "pilot")):
                        bucket = "customer"
                    elif any(kw in lower_line for kw in ("advisor", "mentor", "board")):
                        bucket = "advisor"
                    else:
                        bucket = "other"  # Default fallback — don't miscategorize as investor
                result[bucket].append(summary)

    except Exception as e:
        logging.debug("Feedback parse error: %s", e)

    return result


_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(text: str):
    """Extract the first YYYY-MM-DD date from text. Returns date or None."""
    m = _DATE_PATTERN.search(text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def _parse_hypotheses(doc: str) -> list:
    """
    Parse Active Hypotheses from the living document.
    Returns list of dicts: {date, text, status, test, evidence}
    """
    doc = _normalize_headers(doc)
    hypotheses = []
    ah_match = re.search(r"## Active Hypotheses\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not ah_match:
        return hypotheses

    content = ah_match.group(1).strip()
    if not content or content == "[No hypotheses tracked yet]":
        return hypotheses

    # Match entries like:
    # - [2026-03-01] **hypothesis text**
    #   Status: unvalidated | Test: some test plan
    #   Evidence: ---
    pattern = re.compile(
        r"- \[(\d{4}-\d{2}-\d{2})\] \*\*(.+?)\*\*\n"
        r"\s+Status: (\w+) \| Test: (.+?)\n"
        r"\s+Evidence: (.+?)(?=\n- \[|\Z)",
        re.DOTALL,
    )

    for m in pattern.finditer(content):
        hypotheses.append({
            "date": m.group(1).strip(),
            "text": m.group(2).strip(),
            "status": m.group(3).strip(),
            "test": m.group(4).strip(),
            "evidence": m.group(5).strip(),
        })

    return hypotheses


def _parse_contacts(doc: str) -> list:
    """
    Parse Key Contacts / Prospects from the living document.
    Works for both pitch brain (### Key Contacts / Prospects inside ## Current State)
    and ops brain (## Contacts / Prospects as top-level section).
    Returns list of dicts: {date, name, org, role, type, status, context, last_interaction, next_step}
    """
    doc = _normalize_headers(doc)
    contacts = []
    content = None

    # Try ops brain format first: ## Contacts / Prospects (top-level)
    ops_match = re.search(r"## Contacts / Prospects\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if ops_match:
        content = ops_match.group(1).strip()
    else:
        # Fall back to pitch brain format: ### Key Contacts / Prospects inside ## Current State
        cs_match = re.search(r"## Current State\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
        if not cs_match:
            return contacts
        kc_match = re.search(
            r"### Key Contacts / Prospects\n(.*?)(?=\n### |\n## |\Z)",
            cs_match.group(1),
            re.DOTALL,
        )
        if not kc_match:
            return contacts
        content = kc_match.group(1).strip()

    if not content or content == "[No contacts tracked yet]":
        return contacts

    pattern = re.compile(
        r"- \[(\d{4}-\d{2}-\d{2})\] \*\*(.+?)\*\*\s*\((.+?)\)\n"
        r"\s+Role: (.+?) \| Type: (\w+) \| Status: ([\w-]+)\n"
        r"\s+Context: (.+?)\n"
        r"\s+Last interaction: (.+?)\n"
        r"\s+Next step: (.+?)(?=\n- \[|\Z)",
        re.DOTALL,
    )

    for m in pattern.finditer(content):
        contacts.append({
            "date": m.group(1).strip(),
            "name": m.group(2).strip(),
            "org": m.group(3).strip(),
            "role": m.group(4).strip(),
            "type": m.group(5).strip(),
            "status": m.group(6).strip(),
            "context": m.group(7).strip(),
            "last_interaction": m.group(8).strip(),
            "next_step": m.group(9).strip(),
        })

    return contacts


# Section keywords for matching dismissed contradictions to sections
_SECTION_KEYWORDS = {
    "Target Market / Initial Customer": ["target", "market", "customer", "beachhead", "segment"],
    "Value Proposition": ["value", "proposition", "product", "solution", "problem"],
    "Pricing": ["pricing", "price", "cost", "fee", "licence", "subscription"],
    "Business Model / Revenue Model": ["business", "model", "revenue", "saas", "licence"],
    "Go-to-Market Strategy": ["go-to-market", "sales", "channel", "distribution", "marketing"],
    "Technical Approach": ["technical", "tech", "architecture", "stack", "engineering"],
    "Competitive Landscape": ["competitive", "competitor", "landscape", "alternative"],
    "Moat / Defensibility": ["moat", "defensibility", "advantage", "barrier"],
    "Key Risks": ["risk", "threat", "challenge", "concern"],
    "Team / Hiring Plans": ["team", "hiring", "hire", "talent", "people"],
    "Fundraising Status / Strategy": ["fundraising", "funding", "investor", "seed", "raise"],
    "Problem We're Solving": ["problem", "pain", "need", "gap"],
    "Why Now": ["timing", "trend", "regulation", "urgency"],
    "Traction / Milestones": ["traction", "milestone", "progress", "metric"],
    "Key Assumptions": ["assumption", "hypothesis", "believe", "expect"],
    "Key Contacts / Prospects": ["contact", "prospect", "lead", "pipeline"],
}


def _find_changelog_tensions(sections: list, today) -> list:
    """Find sections with 2+ changelog entries in the last 7 days."""
    tensions = []
    cutoff = today - timedelta(days=7)

    for section in sections:
        recent_dates = []
        for entry in section.get("changelog_entries", []):
            d = _extract_date(entry)
            if d and d >= cutoff:
                recent_dates.append(d)
        if len(recent_dates) >= 2:
            most_recent = max(recent_dates)
            tensions.append({
                "section_name": section["name"],
                "reason": f"{len(recent_dates)} changes in 7 days",
                "details": f"Section '{section['name']}' has been updated {len(recent_dates)} times since {cutoff.isoformat()}.",
                "sort_date": most_recent,
            })

    return tensions


def _find_dismissed_tensions(doc: str, today) -> list:
    """Find recently dismissed contradictions (within 14 days)."""
    doc = _normalize_headers(doc)
    tensions = []
    cutoff = today - timedelta(days=14)

    dm_match = re.search(r"## Dismissed Contradictions\n(.*?)(?:\Z)", doc, re.DOTALL)
    if not dm_match:
        return tensions

    content = dm_match.group(1).strip()
    if not content or content == "[No dismissed contradictions]":
        return tensions

    for line in content.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if not line:
            continue
        d = _extract_date(line)
        if not d or d < cutoff:
            continue

        # Match to section via keyword overlap
        lower_line = line.lower()
        matched_section = None
        best_score = 0
        for section_name, keywords in _SECTION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lower_line)
            if score > best_score:
                best_score = score
                matched_section = section_name

        if not matched_section:
            # Fallback: use first few words as section hint
            matched_section = "General"

        tensions.append({
            "section_name": matched_section,
            "reason": f"dismissed contradiction on {d.isoformat()}",
            "details": line[:200],
            "sort_date": d,
        })

    return tensions


def _find_decision_tensions(doc: str, today) -> list:
    """Find Decision Log entries under evaluation within 14 days."""
    doc = _normalize_headers(doc)
    tensions = []
    cutoff = today - timedelta(days=14)

    dl_match = re.search(r"## Decision Log\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not dl_match:
        return tensions

    content = dl_match.group(1).strip()
    if not content or content == "[No decisions recorded yet]":
        return tensions

    # Find decision entries with "Under evaluation" or "pending" or "revisit" in Status
    # Decision entries start with "### DATE -- Title"
    for m in re.finditer(r"### (\d{4}-\d{2}-\d{2}) — (.+?)\n(.*?)(?=\n### |\Z)", content, re.DOTALL):
        d = _extract_date(m.group(1))
        if not d or d < cutoff:
            continue
        title = m.group(2).strip()
        body = m.group(3)
        status_match = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        if status_match:
            status_text = status_match.group(1).strip().lower()
            if any(kw in status_text for kw in ["under evaluation", "pending", "revisit"]):
                tensions.append({
                    "section_name": title,
                    "reason": f"decision under evaluation since {d.isoformat()}",
                    "details": f"Decision '{title}' has status: {status_match.group(1).strip()}",
                    "sort_date": d,
                })

    return tensions


def _parse_tensions(doc: str, today=None) -> list:
    """
    Detect areas of active instability in the living document.
    Returns list of {section_name, reason, details, sort_date}.
    """
    if today is None:
        today = date.today()

    sections = _parse_current_state(doc)
    tensions = []

    tensions.extend(_find_changelog_tensions(sections, today))
    tensions.extend(_find_dismissed_tensions(doc, today))
    tensions.extend(_find_decision_tensions(doc, today))

    # Deduplicate: if a section triggers multiple signals, keep the most recent
    seen = {}
    for t in tensions:
        key = t["section_name"]
        if key not in seen or t["sort_date"] > seen[key]["sort_date"]:
            seen[key] = t

    # Sort by date, most recent first
    result = sorted(seen.values(), key=lambda t: t["sort_date"], reverse=True)
    return result


def _read_living_document(brain: str = "pitch") -> str:
    """Read the living document, returning empty string on failure."""
    try:
        from services.document_updater import read_living_document
        return read_living_document(brain=brain)
    except Exception:
        return ""
