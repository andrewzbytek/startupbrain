"""
Dashboard sidebar for Startup Brain.
Renders startup state, changelog, feedback themes, cost tracking, and controls.
"""

import re
import base64

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

        # --- Current State Cards ---
        st.subheader("Current State")
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

        # --- Recent Changes ---
        st.subheader("Recent Changes")
        recent = _parse_recent_changelog(doc)
        if recent:
            for entry in recent:
                st.caption(f"• {entry}")
        else:
            st.caption("No changes recorded yet.")

        st.divider()

        # --- Feedback Themes ---
        st.subheader("Feedback Themes")
        try:
            from services.feedback import get_recurring_themes
            themes = get_recurring_themes()
            if themes:
                for theme in themes[:5]:
                    count = theme.get("count", 0)
                    name = theme.get("theme", "")
                    color_class = "pill-badge-red" if count >= 3 else "pill-badge-blue"
                    st.markdown(
                        f'<span class="pill-badge {color_class}">{name} ({count}x)</span>',
                        unsafe_allow_html=True,
                    )
            else:
                # Fall back to parsing document
                doc_themes = _parse_feedback_themes(doc)
                if doc_themes:
                    for t in doc_themes[:5]:
                        st.caption(f"• {t}")
                else:
                    st.caption("No themes yet.")
        except Exception:
            st.caption("Feedback themes unavailable.")

        st.divider()

        # --- Cost Tracking ---
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

        st.divider()

        # --- Controls ---
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

        # --- Evolution Narrative ---
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

        # Whiteboard photo uploader
        st.subheader("Whiteboard Photo")
        uploaded_file = st.file_uploader(
            "Upload whiteboard photo",
            type=["jpg", "jpeg", "png"],
            key="whiteboard_upload",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            if st.button("Process Whiteboard", use_container_width=True):
                with st.spinner("Extracting whiteboard content..."):
                    try:
                        from services.ingestion import process_whiteboard
                        image_bytes = uploaded_file.read()
                        result = process_whiteboard(
                            image_bytes,
                            transcript_context=st.session_state.get("current_transcript", ""),
                        )
                        extracted = result.get("extracted_content", [])
                        if extracted:
                            # Accumulate whiteboard text for current ingestion
                            text_parts = []
                            for item in extracted:
                                content = item.get("content", "")
                                if content:
                                    text_parts.append(content)
                            st.session_state.whiteboard_text = "\n".join(text_parts)
                            st.success(f"Extracted {len(extracted)} item(s) from whiteboard.")
                            conf = result.get("extraction_confidence", "")
                            if conf:
                                st.caption(f"Confidence: {conf}")
                        else:
                            st.warning("No content extracted from whiteboard.")
                    except Exception as e:
                        st.error(f"Whiteboard processing failed: {e}")
