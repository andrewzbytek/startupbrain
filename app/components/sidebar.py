"""
Dashboard sidebar for Startup Brain.
Renders startup state, changelog, feedback themes, cost tracking, and controls.
"""

import html
import re

import streamlit as st

from app.state import set_mode


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
                    st.markdown(pos)
        else:
            st.caption("No current state defined yet.")

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

        if doc:
            st.download_button(
                "Download Living Document",
                data=doc,
                file_name="startup_brain.md",
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
                        st.markdown(narrative)
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
                        st.info(f"**Current position:** {current_pos}")
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
