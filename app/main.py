"""
Startup Brain — Streamlit entry point.
Streamlit Community Cloud deploys from app/main.py.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path — Streamlit only adds the script's
# directory (app/), so absolute imports like "from app.components..." and
# "from services..." would fail without this.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
import uuid

import streamlit as st

st.set_page_config(
    page_title="Startup Brain",
    layout="wide",
    page_icon="🧠",
    initial_sidebar_state="collapsed",
)

# --- Auth gate: block unauthenticated access ---
from app.components.login import is_authenticated, render_login_page
if not is_authenticated():
    from app.components.styles import inject_custom_css
    inject_custom_css()
    render_login_page()
    st.stop()

# Must import state before any other app imports to avoid circular refs
from app.state import init_session_state, set_mode, reset_ingestion, invalidate_sidebar, SESSION_TYPES

# Initialize session state on every rerun
init_session_state()

# --- Crash recovery: check for pending ingestion checkpoint ---
if not st.session_state.get("_has_pending_ingestion") and st.session_state.get("deferred_writer") is None:
    try:
        from services.deferred_writer import load_pending_ingestion
        _pending_writer = load_pending_ingestion()
        if _pending_writer is not None:
            st.session_state.deferred_writer = _pending_writer
            st.session_state._has_pending_ingestion = True
    except Exception:
        pass  # MongoDB unavailable — no crash recovery

from app.components.styles import inject_custom_css
inject_custom_css()

from app.components.top_bar import render_top_bar
from app.components.dashboard import render_dashboard
from app.components.chat import render_chat, render_contradiction_resolution
from app.components.claim_editor import render_claim_editor
from app.components.progress import IngestionProgress, render_step_indicator


def render_ingesting():
    """Ingestion input screen — paste transcript and add metadata."""
    # Acquire ingestion lock
    if not st.session_state.get("_lock_acquired"):
        from services.ingestion_lock import acquire_lock
        lock_session_id = st.session_state.get("_lock_session_id") or str(uuid.uuid4())
        st.session_state._lock_session_id = lock_session_id
        lock_result = acquire_lock(session_id=lock_session_id)
        if not lock_result["acquired"]:
            st.error("Another ingestion is in progress. Please wait for it to complete.")
            if st.button("Back to Chat", key="lock_blocked_back"):
                set_mode("chat")
                st.rerun()
            return
        st.session_state._lock_acquired = True

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

    from datetime import date as _date
    session_date = st.date_input(
        "Session date",
        value=st.session_state.get("ingestion_session_date") or _date.today(),
        key="session_date_input",
        help="Set to a past date if ingesting a session that happened earlier.",
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
                            logging.error("Whiteboard processing failed: %s", e)
                            st.error("Whiteboard processing failed. Please try again.")

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
                st.session_state.ingestion_session_date = session_date

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
                        logging.error("Extraction failed: %s", e)
                        st.error("Extraction failed. Check that your ANTHROPIC_API_KEY is configured.")
                        st.info("If the issue persists, try again or check the server logs.")

    with col_cancel:
        if st.button("Cancel", use_container_width=True, key="cancel_ingest_btn"):
            reset_ingestion()
            st.rerun()


def render_checking_consistency():
    """
    Run consistency check with deferred writes.
    LLM calls run eagerly; all disk/MongoDB/git writes are deferred to batch_commit().
    """
    st.header("Checking Consistency")
    render_step_indicator(3)

    confirmed_claims = st.session_state.get("pending_claims", [])
    transcript = st.session_state.get("current_transcript", "")
    participants = st.session_state.get("ingestion_participants", "")
    session_summary = st.session_state.get("ingestion_session_summary", "")
    topic_tags = st.session_state.get("ingestion_topic_tags", [])
    session_type = st.session_state.get("ingestion_session_type", "")
    session_date_val = st.session_state.get("ingestion_session_date")
    session_date_str = session_date_val.isoformat() if session_date_val else ""
    metadata = {
        "participants": participants,
        "topic": st.session_state.get("ingestion_topic", ""),
        "session_type": session_type,
        "session_date": session_date_str,
    }

    progress = IngestionProgress()
    try:
        with progress.start("Running ingestion pipeline (deferred writes)..."):
            # Step 1: Initialize DeferredWriter — snapshot document, NO writes
            progress.update_step("Preparing deferred pipeline...", status="running")
            from services.deferred_writer import DeferredWriter
            writer = DeferredWriter()
            writer.initialize(
                transcript=transcript,
                confirmed_claims=confirmed_claims,
                metadata=metadata,
                session_summary=session_summary,
                topic_tags=topic_tags,
                session_type=session_type,
                brain=st.session_state.get("active_brain", "pitch"),
            )
            writer.lock_session_id = st.session_state.get("_lock_session_id")
            writer.stage = "consistency_check"
            progress.update_step("Pipeline initialized", status="complete")

            # Step 2: Run consistency check (read-only — no writes)
            progress.update_step("Checking consistency (Pass 1 of 2)...", status="running")
            from services.consistency import run_consistency_check
            consistency_results = run_consistency_check(confirmed_claims, session_type=session_type)
            st.session_state.consistency_results = consistency_results
            writer.consistency_results = consistency_results

            has_critical = consistency_results.get("has_critical", False)
            has_contradictions = consistency_results.get("has_contradictions", False)

            if has_critical:
                progress.update_step("Consistency check complete (Pass 3 — Opus deep analysis run)", status="complete")
            else:
                progress.update_step("Consistency check complete", status="complete")

            # Step 3: Update living document IN MEMORY (LLM runs, no file/git writes)
            progress.update_step("Generating document updates (deferred)...", status="running")
            from datetime import datetime, timezone
            date_str = session_date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if session_type:
                update_reason = f"{session_type} — {date_str}"
            else:
                update_reason = f"Session {date_str}"
            if participants:
                update_reason += f" ({participants})"

            claims_text_parts = [f"Session summary: {session_summary}", "", "Confirmed claims:"]
            for i, claim in enumerate(confirmed_claims, 1):
                claims_text_parts.append(
                    f"{i}. [{claim.get('claim_type', 'claim')}] {claim.get('claim_text', '')} "
                    f"(confidence: {claim.get('confidence', 'definite')})"
                )
            new_info = "\n".join(claims_text_parts)

            doc_result = writer.apply_document_update_deferred(new_info, update_reason=update_reason)
            changes_applied = doc_result.get("changes_applied", 0)

            # Store pipeline result preview for the done screen
            st.session_state.pipeline_result = {
                "document_updated": doc_result.get("success", False),
                "document_update_message": doc_result.get("message", ""),
                "changes_applied": changes_applied,
                "claims_stored": 0,  # Will be set after batch_commit
            }

            if doc_result.get("success"):
                progress.update_step(
                    f"Document updates prepared — {changes_applied} section(s) staged",
                    status="complete",
                )
            else:
                progress.update_step(f"Document update failed: {doc_result.get('message', '')}", status="error")

            # Step 4: Checkpoint to MongoDB
            writer.stage = "awaiting_resolution" if has_contradictions else "ready_to_commit"
            writer.save_checkpoint()
            st.session_state.deferred_writer = writer

            # Check if any confirmed claims relate to active hypotheses
            try:
                from services.mongo_client import get_hypotheses
                active_hyps = get_hypotheses(status="unvalidated") + get_hypotheses(status="testing")
                if active_hyps and confirmed_claims:
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
                progress.complete("Consistency check found issues. Review required.")
                st.info(f"Found {len(contradictions)} contradiction(s) to review.")
                set_mode("resolving_contradiction")
            else:
                progress.complete("All checks passed. Committing...")
                invalidate_sidebar()
                set_mode("done")

    except Exception as e:
        logging.error("Ingestion pipeline failed: %s", e)
        st.error("Ingestion pipeline failed. You can try again or cancel.")
        if st.button("Cancel", key="cancel_after_error"):
            reset_ingestion()
            st.rerun()
        return

    st.rerun()


def render_done():
    """Success summary screen after ingestion completes. Runs batch commit on first render."""
    st.header("Session Ingested")
    render_step_indicator(4)

    consistency_results = st.session_state.get("consistency_results", {})
    claims = st.session_state.get("pending_claims", [])
    pipeline_result = st.session_state.get("pipeline_result", {})

    # --- Batch commit: write everything at once ---
    writer = st.session_state.get("deferred_writer")
    batch_committed = st.session_state.get("_batch_committed", False)

    if writer is not None and not batch_committed:
        with st.spinner("Committing all changes..."):
            commit_result = writer.batch_commit()
        st.session_state._batch_committed = True

        if commit_result.get("success"):
            # Update pipeline_result with actual values from commit
            pipeline_result["claims_stored"] = commit_result.get("claims_stored", 0)
            pipeline_result["session_id"] = commit_result.get("session_id", "")
            pipeline_result["document_updated"] = commit_result.get("document_updated", pipeline_result.get("document_updated", False))
            st.session_state.pipeline_result = pipeline_result
            st.session_state.current_session_id = commit_result.get("session_id", "")
        else:
            logging.error("Batch commit failed: %s", commit_result.get('message', ''))
            st.error("Saving your session failed. Your checkpoint is preserved and will be offered for recovery on next load.")

    doc_updated = pipeline_result.get("document_updated", False)
    changes_applied = pipeline_result.get("changes_applied", 0)
    claims_stored = pipeline_result.get("claims_stored", 0)
    doc_update_msg = pipeline_result.get("document_update_message", "")
    session_id = st.session_state.get("current_session_id", "")

    if doc_updated:
        st.success("Session ingested successfully. Living document updated.")
    else:
        st.warning(
            "Session ingested but the living document was NOT updated. "
            "Your claims are safely stored in the database. "
            "You can try ingesting again or use chat to update the document manually."
        )
        if doc_update_msg:
            logging.error("Document update error: %s", doc_update_msg)

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


def render_ops_ingesting():
    """Ops Brain ingestion — simpler form, no whiteboard support."""
    from app.components.progress import render_step_indicator

    render_step_indicator(current_step=1, total_steps=3, labels=["Input", "Confirm", "Store"])

    st.markdown("## Ingest → Ops Brain")
    st.caption("Extract operational items: contacts, hypotheses, risks, questions, feedback, hiring needs.")

    with st.form("ops_ingest_form"):
        transcript = st.text_area(
            "Paste session notes or transcript",
            height=200,
            placeholder="Meeting notes, email thread, call notes...",
        )
        col1, col2 = st.columns(2)
        with col1:
            session_type = st.selectbox(
                "Session type",
                options=[""] + SESSION_TYPES,
                format_func=lambda x: "Select session type..." if x == "" else x,
                key="ops_session_type",
            )
            participants = st.text_input("Participants", key="ops_participants")
        with col2:
            from datetime import date as _date
            session_date = st.date_input("Date", value=_date.today(), key="ops_session_date")
            topic = st.text_input("Topic hint (optional)", key="ops_topic")

        col_submit, col_cancel = st.columns([1, 1])
        with col_submit:
            submitted = st.form_submit_button("Extract Items", type="primary", use_container_width=True)
        with col_cancel:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)

    if cancelled:
        from app.state import reset_ingestion
        reset_ingestion()
        st.rerun()

    if submitted and transcript.strip():
        from services.ingestion import extract_claims

        try:
            with st.spinner("Extracting operational items..."):
                result = extract_claims(
                    transcript,
                    participants=participants,
                    topic_hint=topic,
                    session_type=session_type,
                    prompt_name="ops_extraction",
                )

            st.session_state.pending_claims = result.get("claims", [])
            st.session_state.current_transcript = transcript
            st.session_state.ingestion_session_summary = result.get("session_summary", "")
            st.session_state.ingestion_topic_tags = result.get("topic_tags", [])
            st.session_state.ingestion_session_type = session_type
            st.session_state.ingestion_session_date = str(session_date)
            st.session_state.ingestion_participants = participants

            from app.state import set_mode
            set_mode("ops_confirming")
            st.rerun()
        except Exception as e:
            import logging
            logging.error(f"Ops extraction failed: {e}")
            st.error("Extraction failed. Please try again.")


def render_claim_editor_for_ops():
    """Ops claims confirmation — reuses claim list UI but with ops-specific buttons."""
    from app.components.progress import render_step_indicator
    from app.components.claim_editor import render_claim_editor

    render_step_indicator(current_step=2, total_steps=3, labels=["Input", "Confirm", "Store"])

    st.markdown("## Confirm Operational Items")
    st.caption("Review and edit extracted items before storing in Ops Brain.")

    # Render the claim list UI (editing, checkboxes, add/remove) but NOT action buttons.
    # We pass ops_mode=True so it skips rendering the pitch-specific "Check Consistency" button.
    render_claim_editor(ops_mode=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Store in Ops Brain", type="primary", use_container_width=True):
            # Sync widget state before reading claims (mirrors pitch flow sync logic)
            current_claims = st.session_state.get("pending_claims", [])
            synced = []
            for claim in current_claims:
                text_key = f"claim_text_{claim.get('_uid', '')}"
                check_key = f"claim_check_{claim.get('_uid', '')}"
                claim_text = st.session_state.get(text_key, claim.get("claim_text", ""))
                checked = st.session_state.get(check_key, claim.get("confirmed", True))
                if checked and claim_text.strip():
                    synced.append({**claim, "claim_text": claim_text.strip(), "confirmed": True})
            if synced:
                st.session_state._ops_confirmed_claims = synced
                from app.state import set_mode
                set_mode("ops_done")
                st.rerun()
            else:
                st.warning("No items confirmed.")
    with col2:
        if st.button("Cancel", use_container_width=True):
            from app.state import reset_ingestion
            reset_ingestion()
            st.rerun()


def render_ops_done():
    """Ops Brain ingestion completion — direct storage, no consistency check."""
    from app.components.progress import render_step_indicator

    render_step_indicator(current_step=3, total_steps=3, labels=["Input", "Confirm", "Store"])

    confirmed = st.session_state.get("_ops_confirmed_claims", [])
    if not confirmed:
        st.warning("No confirmed items found.")
        if st.button("Back to Chat"):
            from app.state import reset_ingestion
            reset_ingestion()
            st.rerun()
        return

    # Run ops ingestion (synchronous, no deferred writer)
    if not st.session_state.get("_ops_committed"):
        from services.ops_ingestion import run_ops_ingestion

        try:
            with st.spinner("Storing in Ops Brain..."):
                result = run_ops_ingestion(
                    transcript=st.session_state.get("current_transcript", ""),
                    confirmed_claims=confirmed,
                    metadata={
                        "session_type": st.session_state.get("ingestion_session_type", ""),
                        "session_date": st.session_state.get("ingestion_session_date", ""),
                        "participants": st.session_state.get("ingestion_participants", ""),
                    },
                    session_summary=st.session_state.get("ingestion_session_summary", ""),
                    topic_tags=st.session_state.get("ingestion_topic_tags", []),
                    session_type=st.session_state.get("ingestion_session_type", ""),
                )

            st.session_state._ops_committed = True
            st.session_state._ops_result = result
        except Exception as e:
            import logging
            logging.error(f"Ops ingestion failed: {e}")
            result = {"success": False, "message": "Storage failed. Please try again."}
            st.session_state._ops_result = result

    result = st.session_state.get("_ops_result", {})

    if result.get("success"):
        st.success(f"Ops Brain updated: {result.get('claims_stored', 0)} items stored.")
    else:
        st.warning(f"Partial result: {result.get('message', 'Unknown issue')}")

    st.markdown(f"**Items stored:** {result.get('claims_stored', 0)}")
    if result.get("document_updated"):
        st.markdown(f"**Document changes:** {result.get('changes_applied', 0)}")

    if st.button("Done — Back to Chat", type="primary"):
        st.session_state._ops_confirmed_claims = []
        st.session_state._ops_committed = False
        st.session_state._ops_result = {}
        from app.state import reset_ingestion
        reset_ingestion()
        st.rerun()


# ---- Main routing ----

# Persistent top bar across all views
render_top_bar()

mode = st.session_state.get("mode", "chat")

# Non-chat modes (ingestion pipeline) render directly — no tab navigation
if mode not in ("chat",):
    if mode == "ops_ingesting":
        render_ops_ingesting()
    elif mode == "ops_confirming":
        render_claim_editor_for_ops()
    elif mode == "ops_done":
        render_ops_done()
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
        st.warning(f"Unknown mode: {mode}. Resetting to chat.")
        set_mode("chat")
        st.rerun()
else:
    # Chat mode — show tab navigation (Chat | Dashboard)
    # --- Crash recovery intercept ---
    if st.session_state.get("_has_pending_ingestion"):
        writer = st.session_state.get("deferred_writer")
        if writer is not None:
            # Check if this checkpoint belongs to a different session
            checkpoint_owner = writer.lock_session_id
            my_session_id = st.session_state.get("_lock_session_id")
            is_own_checkpoint = checkpoint_owner is None or checkpoint_owner == my_session_id

            if is_own_checkpoint:
                st.warning("A previous ingestion was interrupted before completing.")
            else:
                st.warning("Another session's ingestion was interrupted. You can resume or discard it.")

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("Stage", writer.stage)
            with col_info2:
                st.metric("Claims", len(writer.confirmed_claims))
            with col_info3:
                st.metric("Resolutions", len(writer.contradiction_resolutions))

            col_resume, col_discard = st.columns(2)
            with col_resume:
                if st.button("Resume", type="primary", use_container_width=True, key="resume_pending"):
                    # Re-acquire the ingestion lock for this session (fix L3)
                    from services.ingestion_lock import acquire_lock
                    lock_session_id = st.session_state.get("_lock_session_id") or str(uuid.uuid4())
                    st.session_state._lock_session_id = lock_session_id
                    lock_result = acquire_lock(session_id=lock_session_id)
                    if not lock_result["acquired"]:
                        st.error("Cannot resume — another ingestion is in progress.")
                        st.rerun()
                    else:
                        st.session_state._lock_acquired = True

                    st.session_state.pending_claims = writer.confirmed_claims
                    st.session_state.current_transcript = writer.transcript
                    st.session_state.ingestion_participants = writer.metadata.get("participants", "")
                    st.session_state.ingestion_topic = writer.metadata.get("topic", "")
                    st.session_state.ingestion_session_type = writer.session_type
                    st.session_state.ingestion_session_summary = writer.session_summary
                    st.session_state.ingestion_topic_tags = writer.topic_tags
                    st.session_state.consistency_results = writer.consistency_results
                    st.session_state._has_pending_ingestion = False

                    if writer.stage == "ready_to_commit":
                        set_mode("done")
                    elif writer.stage == "awaiting_resolution":
                        resolved_count = len(writer.contradiction_resolutions)
                        st.session_state.contradiction_index = resolved_count
                        pass2 = (writer.consistency_results or {}).get("pass2", {})
                        contradictions = pass2.get("retained", []) if pass2 else []
                        st.session_state.contradictions = contradictions
                        if resolved_count >= len(contradictions):
                            set_mode("done")
                        else:
                            set_mode("resolving_contradiction")
                    else:
                        set_mode("done")
                    st.rerun()

            with col_discard:
                if st.button("Discard", use_container_width=True, key="discard_pending"):
                    writer.rollback()
                    st.session_state._has_pending_ingestion = False
                    st.session_state.deferred_writer = None
                    st.rerun()
        else:
            st.session_state._has_pending_ingestion = False
            # Fall through to normal tab navigation below

    if not st.session_state.get("_has_pending_ingestion"):
        # Tab navigation via st.radio styled as tabs
        active_view = st.radio(
            "Navigation",
            options=["Chat", "Dashboard"],
            index=0 if st.session_state.get("active_view", "chat") == "chat" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="nav_tabs",
        )
        # Sync back to session state
        st.session_state.active_view = "dashboard" if active_view == "Dashboard" else "chat"

        if st.session_state.active_view == "dashboard":
            render_dashboard()
        else:
            render_chat()
