"""
Dashboard sidebar for Startup Brain.
Renders startup state, changelog, feedback themes, cost tracking, and controls.
"""

import html
import re
from datetime import date, timedelta

import streamlit as st

from app.state import set_mode


def _escape_latex(text: str) -> str:
    """Escape dollar signs so Streamlit doesn't render them as LaTeX math."""
    return text.replace("$", "\\$")


def _parse_current_state(doc: str) -> list:
    """
    Parse Current State sections from startup_brain.md.
    Returns list of dicts: {name, current_position, changelog_entries}
    """
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
      - [DATE] SOURCE_NAME (SOURCE_TYPE): SUMMARY — Themes: theme1, theme2
    Groups by source type: investor->vc, customer->customer, advisor->advisor.
    Returns dict like {"vc": [...], "customer": [...], "advisor": [...]}.
    Falls back to empty dict on failure.
    """
    result = {"vc": [], "customer": [], "advisor": []}
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

        type_map = {"investor": "vc", "customer": "customer", "advisor": "advisor"}

        for line in content.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if not line:
                continue
            # Match pattern: [DATE] NAME (TYPE): SUMMARY
            m = re.match(
                r"\[.*?\]\s+\S.*?\((\w+)\):\s*(.+)",
                line,
            )
            if m:
                source_type = m.group(1).strip().lower()
                summary = m.group(2).strip()
                bucket = type_map.get(source_type)
                if bucket:
                    result[bucket].append(summary)

    except Exception:
        pass

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
    tensions = []
    cutoff = today - timedelta(days=14)

    dl_match = re.search(r"## Decision Log\n(.*?)(?=\n## |\Z)", doc, re.DOTALL)
    if not dl_match:
        return tensions

    content = dl_match.group(1).strip()
    if not content or content == "[No decisions recorded yet]":
        return tensions

    # Find decision entries with "Under evaluation" or "pending" or "revisit" in Status
    # Decision entries start with "### DATE — Title"
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


def _read_living_document() -> str:
    """Read the living document, returning empty string on failure."""
    try:
        from services.document_updater import read_living_document
        return read_living_document()
    except Exception:
        return ""


def render_sidebar():
    """Main sidebar rendering function. Called from main.py on every rerun."""
    with st.sidebar:
        st.title("Startup Brain")
        st.caption("Your startup's memory")

        # Load living document (cached in sidebar_data)
        if not st.session_state.get("sidebar_data"):
            doc = _read_living_document()
            st.session_state.sidebar_data = {"doc": doc}
        else:
            doc = st.session_state.sidebar_data.get("doc", "")

        # Button to refresh sidebar
        if st.button("Refresh", key="sidebar_refresh", use_container_width=True):
            doc = _read_living_document()
            st.session_state.sidebar_data = {"doc": doc}
            st.rerun()

        st.divider()

        # --- Our Current View ---
        st.subheader("Our Current View")
        sections = _parse_current_state(doc)
        if sections:
            for section in sections:
                pos = section["current_position"]
                if not pos or pos == "[Not yet defined]":
                    pos = "_Not yet defined_"
                icon = "🟢" if pos and pos != "_Not yet defined_" else "⚪"
                with st.expander(f"{icon} {section['name']}", expanded=False):
                    st.markdown(_escape_latex(pos))
        else:
            st.caption("No current state defined yet.")

        st.divider()

        # --- Hypotheses ---
        hypotheses = _parse_hypotheses(doc)
        if hypotheses:
            active = [h for h in hypotheses if h["status"] in ("unvalidated", "testing")]
            resolved = [h for h in hypotheses if h["status"] in ("validated", "invalidated")]

            st.subheader(f"Hypotheses ({len(active)} active)")

            import html as html_mod
            for h in active:
                status_class = f"hypothesis-{h['status']}"
                badge = f'<span class="hypothesis-badge {status_class}">{html.escape(h["status"])}</span>'
                with st.expander(f"{badge} {html.escape(h['text'][:60])}", expanded=False):
                    st.markdown(f"**Tracked:** {h['date']}")
                    st.markdown(f"**Test:** {h['test']}")
                    st.markdown(f"**Evidence:** {h['evidence']}")

                    # Status update controls
                    new_status = st.selectbox(
                        "Update status",
                        options=["unvalidated", "testing", "validated", "invalidated"],
                        index=["unvalidated", "testing", "validated", "invalidated"].index(h["status"]),
                        key=f"hyp_status_{h['text'][:20]}",
                    )
                    if st.button("Save", key=f"hyp_save_{h['text'][:20]}"):
                        if new_status != h["status"]:
                            try:
                                from services.document_updater import (
                                    read_living_document, write_living_document,
                                    _update_hypothesis_status, _git_commit,
                                )
                                from services.mongo_client import update_hypothesis_status, upsert_living_document
                                from datetime import datetime, timezone

                                fresh_doc = read_living_document()
                                updated = _update_hypothesis_status(fresh_doc, h["text"], new_status)
                                if updated != fresh_doc:
                                    write_living_document(updated)
                                    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                                    upsert_living_document(updated, metadata={"last_updated": date_str})
                                    _git_commit(f"Hypothesis {new_status}: {h['text'][:50]}")
                                    try:
                                        update_hypothesis_status(h["text"], new_status)
                                    except Exception:
                                        pass
                                    st.session_state.sidebar_data = {}
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Update failed: {e}")

            if resolved:
                with st.expander(f"Resolved ({len(resolved)})", expanded=False):
                    for h in resolved:
                        status_class = f"hypothesis-{h['status']}"
                        badge = f'<span class="hypothesis-badge {status_class}">{html.escape(h["status"])}</span>'
                        st.markdown(f"{badge} **{html.escape(h['text'][:60])}** ({h['date']})", unsafe_allow_html=True)

            st.divider()

        # --- External Feedback ---
        st.subheader("External Feedback")
        feedback_by_source = _parse_feedback_by_source(doc)
        has_source_feedback = any(feedback_by_source.get(k) for k in ("vc", "customer", "advisor"))

        if has_source_feedback:
            if feedback_by_source.get("vc"):
                st.markdown("**Top VC/Investor feedback:**")
                for item in feedback_by_source["vc"]:
                    st.caption(f"• {item}")
            if feedback_by_source.get("customer"):
                st.markdown("**Top Customer feedback:**")
                for item in feedback_by_source["customer"]:
                    st.caption(f"• {item}")
            if feedback_by_source.get("advisor"):
                st.markdown("**Top Advisor feedback:**")
                for item in feedback_by_source["advisor"]:
                    st.caption(f"• {item}")
        else:
            # Fall back to recurring themes
            fallback_shown = False
            try:
                from services.feedback import get_recurring_themes
                themes = get_recurring_themes()
                if themes:
                    for theme in themes[:5]:
                        count = theme.get("count", 0)
                        name = theme.get("theme", "")
                        color_class = "pill-badge-red" if count >= 3 else "pill-badge-blue"
                        safe_name = html.escape(str(name))
                        safe_count = html.escape(str(count))
                        st.markdown(
                            f'<span class="pill-badge {color_class}">{safe_name} ({safe_count}x)</span>',
                            unsafe_allow_html=True,
                        )
                    fallback_shown = True
            except Exception:
                pass

            if not fallback_shown:
                doc_themes = _parse_feedback_themes(doc)
                if doc_themes:
                    for t in doc_themes[:5]:
                        st.caption(f"• {t}")
                    fallback_shown = True

            if not fallback_shown:
                st.caption("No external feedback yet.")

        st.divider()

        # --- Recent Changes ---
        st.subheader("Recent Changes")
        recent = _parse_recent_changelog(doc)
        if recent:
            for entry in recent:
                st.caption(f"• {entry}")
        else:
            st.caption("No changes recorded yet.")

        st.divider()

        # --- Active Tensions ---
        tensions = _parse_tensions(doc)
        if tensions:
            st.subheader(f"Active Tensions ({len(tensions)})")
            for t in tensions:
                with st.expander(f"⚡ {t['section_name']} — {t['reason']}", expanded=False):
                    st.markdown(_escape_latex(t["details"]))
            st.divider()

        # --- Actions ---
        st.subheader("Actions")

        current_mode = st.session_state.get("mode", "chat")

        if current_mode == "chat":
            if st.button("Ingest New Session", use_container_width=True, type="primary"):
                set_mode("ingesting")
                st.rerun()
        else:
            st.button("Ingest New Session", use_container_width=True, disabled=True)

        if st.button("Run Consistency Audit", use_container_width=True, disabled=current_mode != "chat"):
            with st.spinner("Running full consistency audit..."):
                try:
                    from services.consistency import run_audit
                    result = run_audit()
                    assessment = result.get("overall_assessment", "unknown")
                    summary = result.get("summary_message", "Audit complete.")
                    discrepancies = result.get("discrepancies", [])
                    st.success(f"Audit complete: {assessment}")
                    if discrepancies:
                        st.warning(f"{len(discrepancies)} discrepancy(ies) found.")
                        for d in discrepancies[:3]:
                            st.caption(f"• [{d.get('severity', '?')}] {d.get('section', '')}: {d.get('suggestion', '')}")
                    else:
                        st.info("No discrepancies found.")
                except Exception as e:
                    st.error(f"Audit failed: {e}")

        # Track Hypothesis form
        with st.expander("Track Hypothesis", expanded=st.session_state.get("show_hypothesis_form", False)):
            with st.form("hypothesis_form", clear_on_submit=True):
                hyp_text = st.text_input("Hypothesis", placeholder="e.g., Small plants have <12 month procurement cycles")
                hyp_test = st.text_input("Test plan (optional)", placeholder="e.g., Ask 3 plant operators")
                submitted = st.form_submit_button("Track")
                if submitted and hyp_text.strip():
                    try:
                        from services.document_updater import (
                            read_living_document, write_living_document, _add_hypothesis, _git_commit,
                        )
                        from services.mongo_client import insert_claim, upsert_living_document
                        from datetime import datetime, timezone

                        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        test_plan = hyp_test.strip() if hyp_test.strip() else "[to be defined]"
                        entry = (
                            f"- [{date_str}] **{hyp_text.strip()}**\n"
                            f"  Status: unvalidated | Test: {test_plan}\n"
                            f"  Evidence: ---"
                        )

                        fresh_doc = read_living_document()
                        updated = _add_hypothesis(fresh_doc, entry)
                        write_living_document(updated)
                        upsert_living_document(updated, metadata={"last_updated": date_str, "update_reason": "New hypothesis"})
                        _git_commit(f"Add hypothesis: {hyp_text.strip()[:50]}")

                        try:
                            insert_claim({
                                "claim_text": hyp_text.strip(),
                                "claim_type": "hypothesis",
                                "confidence": "speculative",
                                "source_type": "hypothesis",
                                "who_said_it": "Founder",
                                "confirmed": True,
                                "status": "unvalidated",
                                "test_plan": test_plan,
                                "created_at": datetime.now(timezone.utc),
                            })
                        except Exception:
                            pass

                        st.success(f"Tracking: {hyp_text.strip()}")
                        st.session_state.sidebar_data = {}
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not track hypothesis: {e}")

        if doc:
            st.download_button(
                "Download Living Document",
                data=doc,
                file_name="startup_brain.md",
                mime="text/markdown",
                use_container_width=True,
            )
            # Full context export (living doc + session history + claims)
            from services.export import generate_context_export
            context_export = generate_context_export()
            st.download_button(
                "Download Full Context",
                data=context_export,
                file_name="startup_context_export.md",
                mime="text/markdown",
                use_container_width=True,
            )

        st.divider()

        # --- Topic Evolution ---
        st.subheader("Topic Evolution")
        topic_names = [s["name"] for s in sections] if sections else []
        if topic_names:
            selected_topic = st.selectbox(
                "Select topic",
                options=topic_names,
                key="evolution_topic_select",
                disabled=current_mode != "chat",
            )
            if st.button("Show Evolution", use_container_width=True, disabled=current_mode != "chat", key="show_evolution_btn"):
                with st.spinner(f"Generating evolution narrative for {selected_topic}..."):
                    try:
                        from services.feedback import generate_evolution_narrative
                        evo_result = generate_evolution_narrative(selected_topic)
                        st.session_state.evolution_result = evo_result
                    except Exception as e:
                        st.error(f"Evolution narrative failed: {e}")
            evo = st.session_state.get("evolution_result")
            if evo:
                with st.expander("Evolution Narrative", expanded=True):
                    narrative = evo.get("narrative", "")
                    if narrative:
                        st.markdown(_escape_latex(narrative))
                    inflection_points = evo.get("key_inflection_points", [])
                    if inflection_points:
                        st.markdown("**Key Inflection Points**")
                        for pt in inflection_points:
                            date = pt.get("date", "")
                            what = pt.get("what_changed", "")
                            why = pt.get("why", "")
                            st.caption(f"**{date}** — {what}" + (f" _{why}_" if why else ""))
                    current_pos = evo.get("current_position_summary", "")
                    if current_pos:
                        st.info(f"**Current position:** {_escape_latex(current_pos)}")
        else:
            st.caption("No topics found in living document.")

        st.divider()

        # --- API Cost ---
        st.subheader("API Cost")
        try:
            from services.cost_tracker import get_monthly_cost
            monthly = get_monthly_cost()
            budget = 300.0
            progress = min(monthly / budget, 1.0)
            st.progress(progress)
            st.caption(f"${monthly:.2f} / ${budget:.0f} budget")
        except Exception:
            st.caption("Cost data unavailable.")

        # --- RAG Health ---
        try:
            from services.consistency import check_rag_health
            rag = check_rag_health()
            if rag["needs_upgrade"]:
                st.warning(
                    f"**RAG upgrade needed** — {rag['claim_count']} claims exceed "
                    f"the {rag['threshold']} threshold. Consistency checks may miss "
                    f"older evidence. Upgrade Atlas to M10+ for semantic search."
                )
            else:
                st.caption(f"RAG: {rag['claim_count']} / {rag['threshold']} claims")
        except Exception:
            pass

        st.divider()

        # --- Quick Commands ---
        with st.expander("Quick Commands", expanded=False):
            st.markdown(
                "**Chat prefixes:**\n"
                "- `note:` / `remember:` / `jot:` / `fyi:` — Quick note\n"
                "- `hypothesis:` — Track a hypothesis\n"
                "- `validated:` / `invalidated:` — Update hypothesis status\n"
                "- `no,` / `actually,` / `correction:` — Direct correction"
            )
