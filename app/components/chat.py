"""
Chat interface for Startup Brain.
Handles conversation, query routing, and contradiction resolution UI.
"""

import streamlit as st

from app.state import add_message, set_mode, reset_ingestion, invalidate_sidebar


# Minimum transcript length to suggest ingestion flow
TRANSCRIPT_SUGGEST_LENGTH = 500


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


def _classify_query(text: str) -> str:
    """
    Classify user query for routing.
    Returns: "current_state" | "historical" | "pitch" | "challenge" | "analysis" | "general"
    """
    lower = text.lower()
    if any(kw in lower for kw in ["what is our current", "what's our", "where are we on", "current position", "right now"]):
        return "current_state"
    if any(kw in lower for kw in ["pitch", "investor", "deck", "slide", "one-pager", "elevator"]):
        return "pitch"
    if any(kw in lower for kw in ["challenge", "poke holes", "devil's advocate", "stress test", "what am i missing", "what are we missing", "pushback"]):
        return "challenge"
    if any(kw in lower for kw in ["analyze", "analysis", "strategy", "strategic", "should we", "recommend"]):
        return "analysis"
    if any(kw in lower for kw in ["when did we", "history", "evolution", "changed", "last time", "previous"]):
        return "historical"
    return "general"


def _get_system_prompt() -> str:
    """Build a system prompt including current living document state."""
    try:
        from services.document_updater import read_living_document
        doc = read_living_document()
    except Exception:
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
        "- Casual/greetings: brief, friendly, no context surfacing\n\n"

        "## Guardrails\n"
        "- You NEVER block founders from making changes — you inform, not gatekeep.\n"
        "- If asked to update or change something, acknowledge it and update immediately.\n"
        "- Do NOT invent information not in the document.\n"
        "- Do NOT surface related context on every message — only when genuinely relevant.\n"
        "- Respond in plain markdown.\n\n"
    )
    if doc:
        base += f"<startup_brain>\n{doc}\n</startup_brain>"

    # Append book framework if loaded for cross-check
    book_content = st.session_state.get("book_crosscheck_content", "")
    if book_content:
        base += f"\n\n<book_framework>{book_content}</book_framework>"

    return base


def _build_claude_prompt(user_message: str, query_type: str):
    """Build prompt components shared by streaming and non-streaming callers."""
    from services.claude_client import call_with_routing

    history = st.session_state.get("conversation_history", [])
    recent_history = history[-10:] if len(history) > 10 else history

    history_text = ""
    for msg in recent_history[:-1]:
        role_label = "Founder" if msg["role"] == "user" else "Startup Brain"
        history_text += f"{role_label}: {msg['content']}\n\n"

    if history_text:
        full_prompt = f"<conversation_history>\n{history_text}</conversation_history>\n\nFounder: {user_message}"
    else:
        full_prompt = user_message

    task_map = {
        "pitch": "pitch_generation",
        "challenge": "strategic_analysis",
        "analysis": "strategic_analysis",
        "current_state": "general",
        "historical": "general",
        "general": "general",
    }
    task_type = task_map.get(query_type, "general")
    system = _get_system_prompt()
    return full_prompt, task_type, system


def _call_claude(user_message: str, query_type: str) -> str:
    """Route to appropriate Claude model and return full response text (non-streaming)."""
    try:
        from services.claude_client import call_with_routing
        full_prompt, task_type, system = _build_claude_prompt(user_message, query_type)
        result = call_with_routing(full_prompt, task_type=task_type, system=system, stream=False)
        return result.get("text", "Sorry, I could not generate a response.")
    except Exception as e:
        return f"Error: {e}"


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
        yield f"Error: {e}"


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

        # Build synthetic claim for consistency check
        claim = {
            "claim_text": user_message,
            "claim_type": "decision",
            "confidence": "definite",
        }

        # Run lightweight consistency check (informational only)
        info_note = ""
        try:
            results = run_consistency_check([claim], session_type="Direct correction")
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
        except Exception:
            pass  # Consistency check failure should never block corrections

        # Always apply the correction
        result = update_document(
            new_info=f"Direct correction from founder: {user_message}",
            update_reason="Direct founder correction",
        )

        if result.get("success"):
            base = f"Got it — updated. {result.get('message', '')}"
            return base + info_note + "\n\nWhat else can I help with?"
        else:
            return (
                f"I heard you. The document update ran into an issue: {result.get('message', 'unknown error')}."
            )
    except Exception as e:
        return f"Understood. Could not auto-update the document: {e}."


def _apply_quick_note(note_text: str) -> str:
    """
    Apply a quick note directly to the living document.
    Skips extraction, claim confirmation, and consistency check.
    Stores a claim in MongoDB with source_type='quick_note'.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import update_document
        from services.mongo_client import insert_claim
        from datetime import datetime, timezone

        # Update the living document
        result = update_document(
            new_info=f"Quick note from founder: {note_text}",
            update_reason="Quick note",
        )

        # Store as a claim in MongoDB
        try:
            insert_claim({
                "claim_text": note_text,
                "claim_type": "claim",
                "confidence": "definite",
                "source_type": "quick_note",
                "who_said_it": "Founder",
                "confirmed": True,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception:
            pass  # MongoDB failure should not block the note

        if result.get("success"):
            section = result.get("message", "")
            return f"Noted — {section}"
        else:
            return f"Note may not have been saved — document update failed: {result.get('message', 'unknown error')}"
    except Exception as e:
        return f"Could not save note: {e}"


def _apply_hypothesis(user_message: str) -> str:
    """
    Add a new hypothesis to the living document and MongoDB.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import (
            read_living_document, write_living_document, _add_hypothesis, _git_commit,
        )
        from services.mongo_client import insert_claim, upsert_living_document
        from datetime import datetime, timezone

        hypothesis_text = _strip_hypothesis_prefix(user_message)
        if not hypothesis_text:
            return "Please provide a hypothesis after the 'hypothesis:' prefix."

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = (
            f"- [{date_str}] **{hypothesis_text}**\n"
            f"  Status: unvalidated | Test: [to be defined]\n"
            f"  Evidence: ---"
        )

        doc = read_living_document()
        doc = _add_hypothesis(doc, entry)
        write_living_document(doc)
        upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": "New hypothesis"})
        _git_commit(f"Add hypothesis: {hypothesis_text[:50]}")

        # Store in MongoDB as a hypothesis claim
        db_synced = False
        try:
            result = insert_claim({
                "claim_text": hypothesis_text,
                "claim_type": "hypothesis",
                "confidence": "speculative",
                "source_type": "hypothesis",
                "who_said_it": "Founder",
                "confirmed": True,
                "status": "unvalidated",
                "test_plan": "",
                "created_at": datetime.now(timezone.utc),
            })
            db_synced = result is not None
        except Exception:
            db_synced = False

        confirmation = (
            f"Hypothesis tracked: **{hypothesis_text}**\n\n"
            f"Status: unvalidated. You can update it later with `validated: {hypothesis_text[:30]}...` "
            f"or `invalidated: {hypothesis_text[:30]}...` in chat, or use the sidebar."
        )
        if not db_synced:
            confirmation += " (note: database sync pending)"
        return confirmation
    except Exception as e:
        return f"Could not track hypothesis: {e}"


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

        # Update living document
        doc = read_living_document()
        updated_doc = _update_hypothesis_status(doc, fragment, new_status)
        if updated_doc == doc:
            return f"Could not find a hypothesis matching: **{fragment}**. Check the sidebar for exact text."

        write_living_document(updated_doc)
        upsert_living_document(updated_doc, metadata={"last_updated": date_str})
        _git_commit(f"Hypothesis {new_status}: {fragment[:50]}")

        # Update MongoDB
        try:
            update_hypothesis_status(fragment, new_status)
        except Exception:
            pass

        return f"Hypothesis updated to **{new_status}**: {fragment}"
    except Exception as e:
        return f"Could not update hypothesis: {e}"


def _handle_quick_action(text: str, query_type: str):
    """Process a quick-action button click as a user message."""
    with st.chat_message("user"):
        st.markdown(text)
    add_message("user", text)
    with st.chat_message("assistant"):
        response = st.write_stream(_call_claude_stream(text, query_type))
    add_message("assistant", response)
    st.rerun()


def render_chat():
    """Main chat UI. Called when mode='chat'."""
    from services.mongo_client import is_mongo_available
    if not is_mongo_available():
        st.warning("MongoDB is unavailable. Running in degraded mode — chat works but ingestion and history are disabled.")

    # Display conversation history
    history = st.session_state.get("conversation_history", [])

    # Welcome message when conversation is empty
    if not history:
        st.markdown("**Welcome to Startup Brain** — your startup's AI memory.")
        st.caption("Ask me anything about your startup, or try one of these:")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("What's our current state?", key="quick_state"):
                _handle_quick_action("What's our current state?", "current_state")
                return
        with col2:
            if st.button("Any open questions?", key="quick_questions"):
                _handle_quick_action("Any open questions?", "general")
                return
        with col3:
            if st.button("Recent changes", key="quick_changes"):
                _handle_quick_action("Recent changes", "historical")
                return

    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Book framework upload for cross-check
    uploaded_file = st.file_uploader(
        "Upload .md for cross-check", type=["md"], key="book_upload",
    )
    if uploaded_file is not None:
        content = uploaded_file.read().decode("utf-8")
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

    # Chat input
    user_input = st.chat_input("Ask anything about your startup...")

    if user_input:
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)

        add_message("user", user_input)

        # Check if user pasted a transcript
        if _is_likely_transcript(user_input):
            response = (
                "That looks like a session transcript or summary. "
                "Would you like to run it through the ingestion pipeline to extract and store the key claims? "
                "Click **Ingest New Session** in the sidebar, or paste it there to get started."
            )
            with st.chat_message("assistant"):
                st.markdown(response)
            add_message("assistant", response)
            st.rerun()
            return

        # Handle quick notes — lightweight doc update, no full pipeline
        if _is_quick_note(user_input):
            note_text = _strip_quick_note_prefix(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Noting..."):
                    response = _apply_quick_note(note_text)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
            st.rerun()
            return

        # Handle hypothesis tracking
        if _is_hypothesis(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Tracking hypothesis..."):
                    response = _apply_hypothesis(user_input)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
            st.rerun()
            return

        # Handle hypothesis status updates
        if _is_hypothesis_status_update(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Updating hypothesis..."):
                    response = _apply_hypothesis_status_update(user_input)
                st.markdown(response)
            add_message("assistant", response)
            invalidate_sidebar()
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

        add_message("assistant", response)
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

    st.header(f"Contradiction {idx + 1} of {total}")
    st.progress((idx + 1) / total)

    severity = contradiction.get("severity", "Notable")
    if severity == "Critical":
        st.error(f"Severity: {severity}")
    elif severity == "Notable":
        st.warning(f"Severity: {severity}")
    else:
        st.info(f"Severity: {severity}")

    # Show the tension
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Current position")
        section = contradiction.get("existing_section", "")
        if section:
            st.caption(f"Section: {section}")
        st.write(contradiction.get("existing_position", "_Not found_"))

    with col2:
        st.subheader("New claim")
        st.write(contradiction.get("new_claim", "_Not found_"))

    tension = contradiction.get("tension_description", "") or contradiction.get("evidence_summary", "")
    if tension:
        st.info(f"**Why this matters:** {tension}")

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
                    with st.expander("Deep Analysis (Opus)", expanded=True):
                        headline = analysis.get("headline", "")
                        if headline:
                            st.markdown(f"> {headline}")
                        implications = analysis.get("downstream_implications", "")
                        if implications:
                            st.markdown(f"> **Downstream implications:** {implications}")
                        observation = analysis.get("analyst_observation", "")
                        if observation:
                            st.info(observation)
                    break

    # Resolution buttons
    new_claim_text = contradiction.get("new_claim", "the new position")
    col_update, col_keep, col_explain = st.columns(3)

    with col_update:
        if st.button("Update to new", type="primary", use_container_width=True, key=f"resolve_update_{idx}"):
            with st.spinner("Updating document..."):
                _resolve_contradiction(contradiction, "update", new_claim_text, "")
            _advance_contradiction()
        st.caption("Replace the current position with the new claim")

    with col_keep:
        if st.button("Keep current", use_container_width=True, key=f"resolve_keep_{idx}"):
            with st.spinner("Logging decision..."):
                _resolve_contradiction(contradiction, "keep", "", "")
            _advance_contradiction()
        st.caption("Dismiss the new claim and keep what we have")

    with col_explain:
        if st.button("Let me explain", use_container_width=True, key=f"resolve_explain_{idx}"):
            st.session_state[f"show_explain_{idx}"] = True
            st.rerun()
        st.caption("Provide context before updating")

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
                    _resolve_contradiction(contradiction, "explain", new_claim_text, explanation.strip())
                _advance_contradiction()
            else:
                st.error("Please enter an explanation before submitting.")


def _resolve_contradiction(contradiction: dict, action: str, new_claim: str, explanation: str):
    """
    Apply a contradiction resolution to the living document.
    action: "update" | "keep" | "explain"

    - "update" / "explain": calls update_document() AND explicitly adds a Decision Log entry.
    - "keep": does NOT call update_document(); adds a Dismissed Contradiction entry.
    All paths write the doc, mirror to MongoDB, and git commit.
    """
    try:
        from services.document_updater import (
            update_document, read_living_document, write_living_document,
            _add_decision, _add_dismissed, _git_commit,
        )
        from services.mongo_client import upsert_living_document
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        section = contradiction.get("existing_section", "Unknown Section")
        tension = contradiction.get("tension_description", "")

        if action == "update":
            new_info = (
                f"Contradiction resolved ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved — updated {section} ({date_str})"
            update_document(new_info, update_reason=reason)

            # Explicit Decision Log entry
            doc = read_living_document()
            decision_entry = f"- [{date_str}] Updated {section}: {new_claim} (resolved contradiction)"
            doc = _add_decision(doc, decision_entry)
            write_living_document(doc)
            upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": reason})
            _git_commit(f"Decision log: {reason}")

        elif action == "keep":
            # Don't call update_document — nothing to update in Current State
            # Just add a Dismissed Contradiction entry
            doc = read_living_document()
            dismissed_entry = (
                f"- [{date_str}] Dismissed: \"{contradiction.get('new_claim', '')}\"\n"
                f"  Kept: {contradiction.get('existing_position', '')}\n"
                f"  Section: {section}"
            )
            doc = _add_dismissed(doc, dismissed_entry)
            write_living_document(doc)
            upsert_living_document(doc, metadata={"last_updated": date_str})
            _git_commit(f"Dismissed contradiction in {section} ({date_str})")

        else:  # explain
            new_info = (
                f"Contradiction resolved with explanation ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Explanation: {explanation}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved with explanation — {section} ({date_str})"
            update_document(new_info, update_reason=reason)

            # Explicit Decision Log entry with explanation
            doc = read_living_document()
            decision_entry = (
                f"- [{date_str}] Updated {section}: {new_claim}\n"
                f"  Reason: {explanation}"
            )
            doc = _add_decision(doc, decision_entry)
            write_living_document(doc)
            upsert_living_document(doc, metadata={"last_updated": date_str, "update_reason": reason})
            _git_commit(f"Decision log: {reason}")

    except Exception as e:
        st.warning(f"Could not update document: {e}")


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
