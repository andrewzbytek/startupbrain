"""
Ops Brain dashboard component.
Renders operational sections: Contacts, Hypotheses, Assumptions, Risks,
Open Questions, Feedback, Hiring Plans, Scratchpad Notes.
"""

import re
import streamlit as st

from app.components._parsers import (
    _read_living_document,
    _parse_hypotheses,
    _parse_contacts,
    _parse_feedback_themes,
    _parse_feedback_by_source,
    _escape_latex,
)


def render_ops_dashboard():
    """Render the Ops Brain dashboard — operational knowledge view."""
    doc = _read_living_document(brain="ops")
    if not doc:
        st.info("Ops Brain document is empty. Ingest an ops session to get started.")
        return

    st.markdown("## Ops Brain Dashboard")

    # Parse sections from ops_brain.md
    sections = _parse_ops_sections(doc)

    # --- Top row: Contacts & Hypotheses ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Contacts / Prospects")
        contacts = _parse_contacts(doc)
        if contacts:
            for c in contacts:
                status_color = {"identified": "#D29922", "in-conversation": "#58A6FF", "engaged": "#3FB950"}.get(
                    c.get("status", ""), "#8B949E"
                )
                st.markdown(
                    f'<span style="color:{status_color};font-weight:600;">{_escape_latex(c["name"])}</span> '
                    f'({_escape_latex(c.get("org", ""))}) — {c.get("status", "")}',
                    unsafe_allow_html=True,
                )
                st.caption(f'{c.get("role", "")} | {c.get("context", "")[:80]}')
        else:
            st.caption("No contacts tracked yet.")

    with col2:
        st.markdown("### Active Hypotheses")
        hypotheses = _parse_hypotheses(doc)
        if hypotheses:
            for h in hypotheses:
                badge_class = f"hypothesis-badge hypothesis-{h['status']}"
                st.markdown(
                    f'<span class="{badge_class}">{h["status"]}</span> '
                    f'**{_escape_latex(h["text"])}**',
                    unsafe_allow_html=True,
                )
                st.caption(f'Test: {h.get("test", "---")} | Evidence: {h.get("evidence", "---")}')
        else:
            st.caption("No hypotheses tracked yet.")

        # Hypothesis form
        with st.expander("Track a hypothesis"):
            lock_failed_key = "_ops_hyp_lock_failed"
            if st.session_state.get(lock_failed_key):
                st.warning("Document is currently being updated by another process. Please re-enter your hypothesis and try again.")
                st.session_state.pop(lock_failed_key, None)

            with st.form("ops_hypothesis_form", clear_on_submit=True):
                hyp_text = st.text_input("Hypothesis statement")
                hyp_test = st.text_input("How will you test this?")
                if st.form_submit_button("Add Hypothesis", type="primary"):
                    if hyp_text:
                        from datetime import datetime, timezone
                        from services.document_updater import _add_hypothesis, read_living_document, write_living_document, _git_commit
                        from services.mongo_client import upsert_living_document
                        from services.ingestion_lock import acquire_doc_lock, release_doc_lock

                        if not acquire_doc_lock():
                            st.session_state[lock_failed_key] = True
                            st.rerun()
                        else:
                            try:
                                entry = (
                                    f"- [{datetime.now(timezone.utc).strftime('%Y-%m-%d')}] **{hyp_text}**\n"
                                    f"  Status: unvalidated | Test: {hyp_test or '---'}\n"
                                    f"  Evidence: ---"
                                )
                                current = read_living_document(brain="ops")
                                updated = _add_hypothesis(current, entry)
                                write_living_document(updated, brain="ops")
                                upsert_living_document(updated, metadata={"last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "update_reason": "New hypothesis"}, brain="ops")
                                _git_commit(f"Add ops hypothesis: {hyp_text[:50]}", brain="ops")
                                # Also insert into claims collection for query parity with chat path
                                from services.mongo_client import insert_claim
                                insert_claim({
                                    "claim_text": hyp_text,
                                    "claim_type": "hypothesis",
                                    "confidence": "low",
                                    "source_type": "hypothesis",
                                    "who_said_it": "Founder",
                                    "confirmed": True,
                                    "status": "unvalidated",
                                    "test_plan": hyp_test or "",
                                }, brain="ops")
                                st.rerun()
                            except Exception as e:
                                import logging
                                logging.error(f"Ops hypothesis add failed: {e}")
                                st.error("Could not add hypothesis. Please try again.")
                            finally:
                                release_doc_lock()

    # --- Middle row: Assumptions, Risks, Open Questions ---
    col3, col4, col5 = st.columns(3)

    with col3:
        st.markdown("### Key Assumptions")
        _render_section_content(sections.get("Key Assumptions", ""))

    with col4:
        st.markdown("### Key Risks")
        _render_section_content(sections.get("Key Risks", ""))

    with col5:
        st.markdown("### Open Questions")
        _render_section_content(sections.get("Open Questions", ""))

    # --- Bottom row: Feedback, Hiring, Scratchpad ---
    col6, col7 = st.columns(2)

    with col6:
        st.markdown("### Feedback Tracker")
        themes = _parse_feedback_themes(doc)
        if themes:
            st.markdown("**Recurring Themes:**")
            for t in themes:
                st.markdown(f"- {_escape_latex(t)}")

        feedback = _parse_feedback_by_source(doc)
        total = sum(len(v) for v in feedback.values())
        if total > 0:
            for source_type, label in [("vc", "Investor"), ("customer", "Customer"), ("advisor", "Advisor")]:
                entries = feedback.get(source_type, [])
                if entries:
                    st.markdown(f"**{label} Feedback** ({len(entries)})")
                    for entry in entries[:5]:
                        st.caption(f"• {_escape_latex(entry[:120])}")
        elif not themes:
            st.caption("No feedback recorded yet.")

    with col7:
        st.markdown("### Hiring Plans")
        _render_section_content(sections.get("Hiring Plans", ""))

        st.markdown("### Scratchpad Notes")
        _render_section_content(sections.get("Scratchpad Notes", ""))

    # Download button
    st.markdown("---")
    st.download_button(
        "Download Ops Brain",
        data=doc,
        file_name="ops_brain.md",
        mime="text/markdown",
    )

    # Context Export
    st.markdown("---")
    st.subheader("Context Export")
    if st.button("Generate Full Context Export", key="ops_context_export"):
        from services.export import generate_context_export
        with st.spinner("Generating ops context export..."):
            try:
                context_export = generate_context_export(brain="ops")
                st.session_state["_ops_context_export_data"] = context_export
                st.rerun()
            except Exception as e:
                import logging
                logging.error(f"Ops context export failed: {e}")
                st.error("Export failed. Please try again.")
    if st.session_state.get("_ops_context_export_data"):
        st.download_button(
            "Save Export File",
            data=st.session_state["_ops_context_export_data"],
            file_name="ops_brain_context_export.md",
            mime="text/markdown",
            key="ops_export_download",
        )


def _parse_ops_sections(doc: str) -> dict:
    """Parse top-level ## sections from the ops brain document into a dict."""
    sections = {}
    for m in re.finditer(r"## (.+?)\n(.*?)(?=\n## |\Z)", doc, re.DOTALL):
        name = m.group(1).strip()
        content = m.group(2).strip()
        sections[name] = content
    return sections


def _render_section_content(content: str):
    """Render section content, handling placeholders."""
    if not content or content.startswith("[No ") or content.startswith("[Not "):
        st.caption(content or "No content yet.")
    else:
        st.markdown(_escape_latex(content))
