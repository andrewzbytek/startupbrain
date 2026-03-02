"""
Startup Brain — Streamlit entry point.
Streamlit Community Cloud deploys from app/main.py.
"""

import streamlit as st

st.set_page_config(
    page_title="Startup Brain",
    layout="wide",
    page_icon="🧠",
    initial_sidebar_state="expanded",
)

# Must import state before any other app imports to avoid circular refs
from app.state import init_session_state, set_mode, reset_ingestion, invalidate_sidebar

# Initialize session state on every rerun
init_session_state()

from app.components.styles import inject_custom_css
inject_custom_css()

from app.components.sidebar import render_sidebar
from app.components.chat import render_chat, render_contradiction_resolution
from app.components.claim_editor import render_claim_editor
from app.components.progress import IngestionProgress, INGESTION_STEPS, render_step_indicator


def render_ingesting():
    """Ingestion input screen — paste transcript and add metadata."""
    st.header("Ingest New Session")
    render_step_indicator(1)
    st.caption("Paste your post-session summary below. This should be a clean summary, not raw brainstorming.")

    transcript = st.text_area(
        "Session transcript / summary",
        value=st.session_state.get("current_transcript") or "",
        height=300,
        placeholder="Paste your session summary here...",
        key="transcript_input",
    )

    col1, col2 = st.columns(2)
    with col1:
        participants = st.text_input(
            "Participants (optional)",
            value=st.session_state.get("ingestion_participants", ""),
            placeholder="e.g. Alice, Bob",
            key="participants_input",
        )
    with col2:
        topic = st.text_input(
            "Topic / focus area (optional)",
            value=st.session_state.get("ingestion_topic", ""),
            placeholder="e.g. Pricing strategy, Go-to-market",
            key="topic_input",
        )

    from app.state import SESSION_TYPES
    col_type, col_custom = st.columns(2)
    with col_type:
        session_type = st.selectbox(
            "Session type",
            options=[""] + SESSION_TYPES,
            index=0,
            format_func=lambda x: "Select session type..." if x == "" else x,
            key="session_type_select",
        )
    with col_custom:
        custom_type = ""
        if session_type == "Other":
            custom_type = st.text_input(
                "Custom session type",
                key="custom_session_type_input",
                placeholder="e.g. Board meeting",
            )
        else:
            st.empty()

    # Whiteboard photo (optional)
    st.markdown("---")
    st.subheader("Whiteboard Photo (optional)")
    uploaded_file = st.file_uploader(
        "Upload whiteboard photo",
        type=["jpg", "jpeg", "png"],
        key="whiteboard_upload",
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        if uploaded_file.size > 10_000_000:
            st.error("File too large. Maximum upload size is 10 MB.")
        else:
            col_preview, col_action = st.columns([2, 1])
            with col_preview:
                st.image(uploaded_file, width=300)
            with col_action:
                if st.button("Process Whiteboard", key="process_wb_btn"):
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
                                text_parts = []
                                for item in extracted:
                                    content = item.get("content", "")
                                    if content:
                                        text_parts.append(content)
                                st.session_state.whiteboard_text = "\n".join(text_parts)
                                st.rerun()
                            else:
                                st.warning("No content extracted from whiteboard.")
                        except Exception as e:
                            st.error(f"Whiteboard processing failed: {e}")

    whiteboard_text = st.session_state.get("whiteboard_text", "")
    if whiteboard_text:
        st.success(f"Whiteboard content attached ({len(whiteboard_text)} chars). Will be included in extraction.")

    col_process, col_cancel = st.columns([3, 1])

    with col_process:
        if st.button("Ingest Session", type="primary", use_container_width=True, key="process_btn"):
            if not transcript.strip():
                st.error("Please paste a session transcript before proceeding.")
            else:
                # Store metadata in session state
                st.session_state.current_transcript = transcript.strip()
                st.session_state.ingestion_participants = participants.strip()
                st.session_state.ingestion_topic = topic.strip()

                # Resolve session type
                final_session_type = custom_type.strip() if session_type == "Other" else session_type
                st.session_state.ingestion_session_type = final_session_type

                # Extract claims with progress feedback
                with st.spinner("Analyzing session and extracting claims..."):
                    try:
                        from services.ingestion import extract_claims

                        result = extract_claims(
                            transcript=transcript.strip(),
                            participants=participants.strip(),
                            topic_hint=topic.strip(),
                            whiteboard_text=whiteboard_text,
                            session_type=final_session_type,
                        )

                        claims = result.get("claims", [])
                        session_summary = result.get("session_summary", "")
                        topic_tags = result.get("topic_tags", [])

                        st.session_state.pending_claims = claims
                        st.session_state.ingestion_session_summary = session_summary
                        st.session_state.ingestion_topic_tags = topic_tags

                        if claims:
                            st.success(f"Extracted {len(claims)} claim(s). Review and confirm below.")
                        else:
                            st.warning("No claims were extracted. You can add claims manually.")

                        set_mode("confirming_claims")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Extraction failed: {e}")
                        st.info("Check that your ANTHROPIC_API_KEY is configured in st.secrets.")

    with col_cancel:
        if st.button("Cancel", use_container_width=True, key="cancel_ingest_btn"):
            reset_ingestion()
            st.rerun()


def render_checking_consistency():
    """
    Run consistency check and transition to resolving_contradiction or done.
    This mode auto-advances — it shows progress and then transitions.
    """
    st.header("Checking Consistency")
    render_step_indicator(3)

    confirmed_claims = st.session_state.get("pending_claims", [])
    transcript = st.session_state.get("current_transcript", "")
    participants = st.session_state.get("ingestion_participants", "")
    session_summary = st.session_state.get("ingestion_session_summary", "")
    topic_tags = st.session_state.get("ingestion_topic_tags", [])
    session_type = st.session_state.get("ingestion_session_type", "")
    metadata = {
        "participants": participants,
        "topic": st.session_state.get("ingestion_topic", ""),
        "session_type": session_type,
    }

    progress = IngestionProgress()
    try:
        with progress.start("Running ingestion pipeline..."):
            # Step 1: Store session
            progress.update_step("Storing session...", status="running")
            from services.ingestion import store_session
            session_id = store_session(
                transcript,
                metadata=metadata,
                session_summary=session_summary,
                topic_tags=topic_tags,
            )
            st.session_state.current_session_id = session_id
            progress.update_step("Session stored", status="complete")

            # Step 2: Run consistency check
            progress.update_step("Checking consistency (Pass 1 of 2)...", status="running")
            from services.consistency import run_consistency_check
            consistency_results = run_consistency_check(confirmed_claims, session_type=session_type)
            st.session_state.consistency_results = consistency_results

            has_critical = consistency_results.get("has_critical", False)
            has_contradictions = consistency_results.get("has_contradictions", False)

            if has_critical:
                progress.update_step("Consistency check complete (Pass 3 — Opus deep analysis run)", status="complete")
            else:
                progress.update_step("Consistency check complete", status="complete")

            # Step 3: Update living document
            progress.update_step("Updating living document...", status="running")
            from services.ingestion import run_ingestion_pipeline
            pipeline_result = run_ingestion_pipeline(
                transcript=transcript,
                confirmed_claims=confirmed_claims,
                session_id=session_id or "",
                metadata=metadata,
                session_summary=session_summary,
            )
            claims_stored = pipeline_result.get("claims_stored", 0)
            doc_updated = pipeline_result.get("document_updated", False)
            changes_applied = pipeline_result.get("changes_applied", 0)
            doc_update_msg = pipeline_result.get("document_update_message", "")

            # Store pipeline result for the done screen
            st.session_state.pipeline_result = pipeline_result

            if doc_updated:
                progress.update_step(
                    f"Living document updated — {changes_applied} section(s) changed, {claims_stored} claims stored",
                    status="complete",
                )
            else:
                progress.update_step(f"Document update failed: {doc_update_msg}", status="error")

            # Check if any confirmed claims relate to active hypotheses
            try:
                from services.mongo_client import get_hypotheses
                active_hyps = get_hypotheses(status="unvalidated") + get_hypotheses(status="testing")
                if active_hyps and confirmed_claims:
                    # Simple keyword overlap check
                    import re as _re
                    _stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                                   "have", "has", "had", "do", "does", "did", "will", "would", "could",
                                   "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                                   "on", "with", "at", "by", "from", "as", "into", "through", "during",
                                   "before", "after", "above", "below", "between", "out", "off", "over",
                                   "under", "again", "further", "then", "once", "and", "but", "or", "nor",
                                   "not", "no", "so", "than", "too", "very", "just", "about", "up", "that",
                                   "this", "it", "we", "our", "they", "their", "them", "its", "per", "each"}

                    def _significant_words(text):
                        return {w for w in _re.findall(r"\w+", text.lower()) if len(w) > 2 and w not in _stop_words}

                    relevant_hyps = []
                    for hyp in active_hyps:
                        hyp_words = _significant_words(hyp.get("claim_text", ""))
                        for claim in confirmed_claims:
                            claim_words = _significant_words(claim.get("claim_text", ""))
                            if len(hyp_words & claim_words) >= 3:
                                relevant_hyps.append(hyp.get("claim_text", ""))
                                break

                    if relevant_hyps:
                        hyp_list = "\n".join(f"- {h[:80]}" for h in relevant_hyps[:3])
                        st.info(f"These claims may relate to active hypotheses:\n{hyp_list}")
            except Exception:
                pass  # Hypothesis check is a nudge, never blocking

            # Determine if we have contradictions to resolve
            if has_contradictions:
                pass2 = consistency_results.get("pass2", {})
                contradictions = pass2.get("retained", []) if pass2 else []
                st.session_state.contradictions = contradictions
                st.session_state.contradiction_index = 0
                summary = consistency_results.get("summary", "")
                progress.complete(f"Consistency check found issues. Review required.")
                st.info(f"Found {len(contradictions)} contradiction(s) to review.")
                set_mode("resolving_contradiction")
            else:
                progress.complete("All done. Session ingested.")
                # Invalidate sidebar cache
                invalidate_sidebar()
                set_mode("done")

    except Exception as e:
        st.error(f"Ingestion pipeline failed: {e}")
        st.info("You can try again or cancel.")
        if st.button("Cancel", key="cancel_after_error"):
            reset_ingestion()
            st.rerun()
        return

    st.rerun()


def render_done():
    """Success summary screen after ingestion completes."""
    st.header("Session Ingested")
    render_step_indicator(4)

    consistency_results = st.session_state.get("consistency_results", {})
    claims = st.session_state.get("pending_claims", [])
    session_id = st.session_state.get("current_session_id", "")
    pipeline_result = st.session_state.get("pipeline_result", {})

    doc_updated = pipeline_result.get("document_updated", False)
    changes_applied = pipeline_result.get("changes_applied", 0)
    claims_stored = pipeline_result.get("claims_stored", 0)
    doc_update_msg = pipeline_result.get("document_update_message", "")

    if doc_updated:
        st.success("Session ingested successfully. Living document updated.")
    else:
        st.warning(
            "Session ingested but the living document was NOT updated. "
            "Your claims are safely stored in the database. "
            "You can try ingesting again or use chat to update the document manually."
        )
        if doc_update_msg:
            st.error(f"Document update error: {doc_update_msg}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Claims confirmed", len(claims))
    with col2:
        st.metric("Claims stored", claims_stored)
    with col3:
        st.metric("Sections updated", changes_applied if doc_updated else 0)
    with col4:
        has_contradictions = consistency_results.get("has_contradictions", False) if consistency_results else False
        st.metric("Contradictions", "Resolved" if has_contradictions else "None")

    if session_id:
        st.caption(f"Session ID: {session_id}")

    summary = consistency_results.get("summary", "") if consistency_results else ""
    if summary:
        st.info(f"Consistency summary: {summary}")

    st.markdown("---")

    if st.button("Return to Chat", type="primary", key="return_to_chat"):
        # Keep conversation history, clear ingestion state
        reset_ingestion()
        st.rerun()


# ---- Main routing ----

# Always render sidebar
render_sidebar()

# Main content area
st.title("Startup Brain")

mode = st.session_state.get("mode", "chat")

if mode == "chat":
    render_chat()

elif mode == "ingesting":
    render_ingesting()

elif mode == "confirming_claims":
    render_claim_editor()

elif mode == "checking_consistency":
    render_checking_consistency()

elif mode == "resolving_contradiction":
    render_contradiction_resolution()

elif mode == "done":
    render_done()

else:
    # Fallback — unknown mode, reset to chat
    st.warning(f"Unknown mode: {mode}. Resetting to chat.")
    set_mode("chat")
    st.rerun()
