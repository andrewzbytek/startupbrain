"""
Chat interface for Startup Brain.
Handles conversation, query routing, and contradiction resolution UI.
"""

import streamlit as st

from app.state import add_message, set_mode, reset_ingestion


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


def _classify_query(text: str) -> str:
    """
    Classify user query for routing.
    Returns: "current_state" | "historical" | "pitch" | "analysis" | "general"
    """
    lower = text.lower()
    if any(kw in lower for kw in ["what is our current", "what's our", "where are we on", "current position", "right now"]):
        return "current_state"
    if any(kw in lower for kw in ["pitch", "investor", "deck", "slide", "one-pager", "elevator"]):
        return "pitch"
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
        "You have access to the startup's living knowledge document below. "
        "Your job is to help the founders think clearly by answering questions from this document, "
        "surfacing relevant history, and flagging any tensions you notice. "
        "Be direct, concise, and opinionated when asked for analysis. "
        "You NEVER block founders from making changes — you inform, not gatekeep. "
        "If asked to update or change something, acknowledge it and update immediately. "
        "Respond in plain markdown.\n\n"
    )
    if doc:
        base += f"<startup_brain>\n{doc}\n</startup_brain>"
    return base


def _call_claude(user_message: str, query_type: str) -> str:
    """
    Route to appropriate Claude model and return response text.
    For streaming, returns plain text (non-streaming fallback used here for simplicity).
    """
    try:
        from services.claude_client import call_with_routing

        # Build conversation history for context
        history = st.session_state.get("conversation_history", [])
        # Include last 10 messages for context
        recent_history = history[-10:] if len(history) > 10 else history

        # Build the full prompt with history context
        history_text = ""
        for msg in recent_history[:-1]:  # Exclude the message just added
            role_label = "Founder" if msg["role"] == "user" else "Startup Brain"
            history_text += f"{role_label}: {msg['content']}\n\n"

        if history_text:
            full_prompt = f"<conversation_history>\n{history_text}</conversation_history>\n\nFounder: {user_message}"
        else:
            full_prompt = user_message

        # Map query type to task type for routing
        task_map = {
            "pitch": "pitch_generation",
            "analysis": "strategic_analysis",
            "current_state": "general",
            "historical": "general",
            "general": "general",
        }
        task_type = task_map.get(query_type, "general")

        system = _get_system_prompt()
        result = call_with_routing(full_prompt, task_type=task_type, system=system)
        return result.get("text", "Sorry, I could not generate a response.")
    except Exception as e:
        return f"Error: {e}"


def _apply_direct_correction(user_message: str) -> str:
    """
    Apply a direct correction to the living document immediately.
    Returns a confirmation message.
    """
    try:
        from services.document_updater import update_document
        result = update_document(
            new_info=f"Direct correction from founder: {user_message}",
            update_reason="Direct founder correction",
        )
        if result.get("success"):
            return (
                f"Got it — updated. {result.get('message', '')}\n\n"
                f"What else can I help with?"
            )
        else:
            return (
                f"I heard you. The document update ran into an issue: {result.get('message', 'unknown error')}. "
                f"You may want to try the ingestion flow for a more structured update."
            )
    except Exception as e:
        return f"Understood. Could not auto-update the document: {e}. Use the ingestion flow for structured updates."


def render_chat():
    """Main chat UI. Called when mode='chat'."""
    # Display conversation history
    history = st.session_state.get("conversation_history", [])
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

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

        # Handle direct corrections — apply immediately, zero pushback
        if _is_direct_correction(user_input):
            with st.chat_message("assistant"):
                with st.spinner("Updating..."):
                    response = _apply_direct_correction(user_input)
                st.markdown(response)
            add_message("assistant", response)
            # Invalidate sidebar cache so it reflects the update
            st.session_state.sidebar_data = {}
            st.rerun()
            return

        # Normal query — classify and route
        query_type = _classify_query(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = _call_claude(user_input, query_type)
            st.markdown(response)

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

    severity = contradiction.get("severity", "Notable")
    severity_color = {"Critical": "red", "Notable": "orange", "Minor": "blue"}.get(severity, "gray")
    st.markdown(f"**Severity:** :{severity_color}[{severity}]")

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
                        st.write(f"**{analysis.get('headline', '')}**")
                        implications = analysis.get("downstream_implications", "")
                        if implications:
                            st.write(f"**Downstream implications:** {implications}")
                        observation = analysis.get("analyst_observation", "")
                        if observation:
                            st.write(f"**Analyst observation:** {observation}")
                    break

    # Resolution buttons
    new_claim_text = contradiction.get("new_claim", "the new position")
    col_update, col_keep, col_explain = st.columns(3)

    with col_update:
        update_label = f"Update to new"
        if st.button(update_label, type="primary", use_container_width=True, key=f"resolve_update_{idx}"):
            with st.spinner("Updating document..."):
                _resolve_contradiction(contradiction, "update", new_claim_text, "")
            _advance_contradiction()

    with col_keep:
        if st.button("Keep current", use_container_width=True, key=f"resolve_keep_{idx}"):
            with st.spinner("Logging decision..."):
                _resolve_contradiction(contradiction, "keep", "", "")
            _advance_contradiction()

    with col_explain:
        if st.button("Let me explain the change", use_container_width=True, key=f"resolve_explain_{idx}"):
            st.session_state[f"show_explain_{idx}"] = True
            st.rerun()

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
    """
    try:
        from services.document_updater import update_document
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
        elif action == "keep":
            new_info = (
                f"Contradiction reviewed ({date_str}): Keeping current position in {section}.\n"
                f"Rejected new claim: {contradiction.get('new_claim', '')}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction reviewed — kept current position in {section} ({date_str})"
        else:  # explain
            new_info = (
                f"Contradiction resolved with explanation ({date_str}): Updating {section}.\n"
                f"New position: {new_claim}\n"
                f"Explanation: {explanation}\n"
                f"Tension was: {tension}"
            )
            reason = f"Contradiction resolved with explanation — {section} ({date_str})"

        update_document(new_info, update_reason=reason)
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
        st.session_state.sidebar_data = {}  # Invalidate sidebar cache
        set_mode("done")
    else:
        st.session_state.contradiction_index = next_idx

    st.rerun()
