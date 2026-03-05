"""
Full-page dashboard for Startup Brain.
Replaces the sidebar with a dedicated dashboard tab.
"""

import html

import streamlit as st

from app.components._parsers import (
    _escape_latex,
    _parse_current_state,
    _parse_recent_changelog,
    _parse_feedback_by_source,
    _parse_feedback_themes,
    _parse_contacts,
    _parse_tensions,
    _read_living_document,
)

_CONTACT_STATUS_COLORS = {
    "identified": ("rgba(88,166,255,0.12)", "#58A6FF"),
    "in-conversation": ("rgba(210,153,34,0.12)", "#D29922"),
    "engaged": ("rgba(63,185,80,0.12)", "#3FB950"),
    "pilot": ("rgba(63,185,80,0.12)", "#3FB950"),
}


def render_dashboard():
    """Main dashboard rendering function. Called when user selects the Dashboard tab."""

    # Brain dispatch — delegate to Ops dashboard when active
    if st.session_state.get("active_brain", "pitch") == "ops":
        from app.components.ops_dashboard import render_ops_dashboard
        render_ops_dashboard()
        return

    # --- Load living document (cached in sidebar_data) ---
    if not st.session_state.get("sidebar_data"):
        doc = _read_living_document()
        st.session_state.sidebar_data = {"doc": doc}
    else:
        doc = st.session_state.sidebar_data.get("doc", "")

    # --- Refresh button ---
    _, refresh_col = st.columns([0.88, 0.12])
    with refresh_col:
        if st.button("Refresh", key="dashboard_refresh"):
            doc = _read_living_document()
            st.session_state.sidebar_data = {"doc": doc}
            st.rerun()

    # =====================================================================
    # Current State — 2-column expander grid
    # =====================================================================
    st.subheader("Current State")
    sections = _parse_current_state(doc)
    if sections:
        for row_start in range(0, len(sections), 2):
            row_sections = sections[row_start : row_start + 2]
            cols = st.columns(2)
            for col, section in zip(cols, row_sections):
                with col:
                    pos = section["current_position"]
                    has_content = pos and pos != "[Not yet defined]"
                    dot = "\U0001f7e2" if has_content else "\u26aa"
                    with st.expander(f"{dot} {section['name']}", expanded=False):
                        st.markdown(_escape_latex(pos) if has_content else "_Not yet defined_")
    else:
        st.caption("No current state defined yet.")

    # =====================================================================
    # Secondary panels: 2-column layout (all wrapped in expanders)
    # =====================================================================
    left_col, right_col = st.columns(2)

    # --- LEFT COLUMN ---
    with left_col:
        # Contacts panel
        contacts = _parse_contacts(doc)
        active_contacts = [c for c in contacts if c["status"] not in ("closed", "inactive")] if contacts else []

        with st.expander(f"Contacts ({len(active_contacts)} active)", expanded=False):
            if active_contacts:
                type_labels = {
                    "investor": "Investors",
                    "prospect": "Prospects",
                    "hire": "Hires",
                    "advisor": "Advisors",
                    "partner": "Partners",
                }
                type_groups = {}
                for c in active_contacts:
                    ctype = c["type"]
                    label = type_labels.get(ctype, ctype.title())
                    if label not in type_groups:
                        type_groups[label] = []
                    type_groups[label].append(c)

                for group_label, group_contacts in type_groups.items():
                    st.markdown(f"**{group_label} ({len(group_contacts)})**")
                    for c in group_contacts:
                        bg, fg = _CONTACT_STATUS_COLORS.get(c["status"], ("rgba(139,148,158,0.12)", "#8B949E"))
                        status_badge = (
                            f'<span style="background:{bg};color:{fg};padding:2px 8px;'
                            f'border-radius:4px;font-size:0.8em;">{html.escape(c["status"])}</span>'
                        )
                        st.markdown(f"**{html.escape(c['name'])}** ({html.escape(c['org'])})", unsafe_allow_html=True)
                        st.markdown(status_badge + f" &nbsp; {html.escape(c['role'])}", unsafe_allow_html=True)
                        st.caption(f"Last: {c['last_interaction']}")
                        st.caption(f"Next: {c['next_step']}")
            else:
                st.caption("No active contacts.")

    # --- RIGHT COLUMN ---
    with right_col:
        # External Feedback panel
        with st.expander("External Feedback", expanded=True):
            feedback_by_source = _parse_feedback_by_source(doc)
            has_source_feedback = any(feedback_by_source.get(k) for k in ("vc", "customer", "advisor"))

            if has_source_feedback:
                _FEEDBACK_LABELS = {"vc": "VC/Investor", "customer": "Customer", "advisor": "Advisor"}
                for key in ("vc", "customer", "advisor"):
                    items = feedback_by_source.get(key, [])
                    if items:
                        st.markdown(f"**Top {_FEEDBACK_LABELS[key]} feedback:**")
                        for item in items:
                            st.caption(f"  {_escape_latex(item)}")
            else:
                fallback_shown = False
                try:
                    from services.feedback import get_recurring_themes
                    themes = get_recurring_themes()
                    if themes:
                        for theme in themes[:5]:
                            count = theme.get("count", 0)
                            name = theme.get("theme", "")
                            bg = "rgba(248,81,73,0.12)" if count >= 3 else "rgba(88,166,255,0.12)"
                            fg = "#F85149" if count >= 3 else "#58A6FF"
                            safe_name = html.escape(str(name))
                            safe_count = html.escape(str(count))
                            st.markdown(
                                f'<span style="background:{bg};color:{fg};padding:2px 10px;'
                                f'border-radius:12px;font-size:0.85em;">'
                                f'{safe_name} ({safe_count}x)</span>',
                                unsafe_allow_html=True,
                            )
                        fallback_shown = True
                except Exception:
                    pass

                if not fallback_shown:
                    doc_themes = _parse_feedback_themes(doc)
                    if doc_themes:
                        for t in doc_themes[:5]:
                            st.caption(f"  {_escape_latex(t)}")
                        fallback_shown = True

                if not fallback_shown:
                    st.caption("No external feedback yet.")

        # Recent Changes panel — collapsed by default
        recent = _parse_recent_changelog(doc)
        with st.expander(f"Recent Changes ({len(recent)})" if recent else "Recent Changes", expanded=False):
            if recent:
                for entry in recent:
                    st.caption(f"  {_escape_latex(entry)}")
            else:
                st.caption("No changes recorded yet.")

        # Active Tensions panel
        tensions = _parse_tensions(doc)
        with st.expander(f"Active Tensions ({len(tensions)})" if tensions else "Active Tensions", expanded=False):
            if tensions:
                for t in tensions:
                    st.markdown(f"**{t['section_name']}** -- {t['reason']}")
                    st.caption(_escape_latex(t["details"]))
            else:
                st.caption("No active tensions detected.")

    # =====================================================================
    # Actions — 2-column row + Topic Evolution expander
    # =====================================================================
    st.divider()
    st.subheader("Actions")

    act_col1, act_col2 = st.columns(2)

    with act_col1:
        if doc:
            st.download_button(
                "Download Living Document",
                data=doc,
                file_name="pitch_brain.md",
                mime="text/markdown",
                use_container_width=True,
            )

    with act_col2:
        if doc:
            if st.button("Generate Full Context Export", use_container_width=True, key="dash_export_btn"):
                with st.spinner("Generating context export..."):
                    try:
                        from services.export import generate_context_export
                        context_export = generate_context_export(brain="pitch")
                        st.session_state["_context_export_data"] = context_export
                        st.rerun()
                    except Exception as e:
                        import logging
                        logging.error(f"Export failed: {e}")
                        st.error("Export failed. Please try again.")

            export_data = st.session_state.get("_context_export_data")
            if export_data:
                st.download_button(
                    "Save Export File",
                    data=export_data,
                    file_name="startup_context_export.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="dash_export_download",
                )

    # Topic Evolution in its own expander
    with st.expander("Topic Evolution", expanded=False):
        topic_names = [s["name"] for s in sections] if sections else []
        if topic_names:
            selected_topic = st.selectbox(
                "Topic",
                options=topic_names,
                key="dash_evolution_topic_select",
            )
            if st.button("Show Evolution", use_container_width=True, key="dash_show_evolution_btn"):
                with st.spinner(f"Generating evolution narrative for {selected_topic}..."):
                    try:
                        from services.feedback import generate_evolution_narrative
                        evo_result = generate_evolution_narrative(selected_topic, brain=st.session_state.get("active_brain", "pitch"))
                        st.session_state.evolution_result = evo_result
                        st.rerun()
                    except Exception as e:
                        import logging
                        logging.error("Evolution narrative failed: %s", e)
                        st.error("Evolution narrative failed. Please try again.")

            evo = st.session_state.get("evolution_result")
            if evo:
                narrative = evo.get("narrative", "")
                if narrative:
                    st.markdown(_escape_latex(narrative))
                inflection_points = evo.get("key_inflection_points", [])
                if inflection_points:
                    st.markdown("**Key Inflection Points**")
                    for pt in inflection_points:
                        pt_date = pt.get("date", "")
                        what = pt.get("what_changed", "")
                        why = pt.get("why", "")
                        st.caption(f"**{pt_date}** -- {what}" + (f" _{why}_" if why else ""))
                current_pos = evo.get("current_position_summary", "")
                if current_pos:
                    st.info(f"**Current position:** {_escape_latex(current_pos)}")
        else:
            st.caption("No topics found in living document.")
