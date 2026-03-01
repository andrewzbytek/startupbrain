"""
Claim confirmation UI for Startup Brain.
Displays extracted claims as an interactive checklist per SPEC Section 3.2.
"""

import streamlit as st

from app.state import set_mode, reset_ingestion


def render_claim_editor():
    """
    Display the claim confirmation UI.
    Called when mode="confirming_claims".
    Users can check/uncheck, edit, remove, and add claims before proceeding.
    """
    st.header("Confirm Extracted Claims")
    st.caption("Paste your post-session summary (not raw brainstorming)")

    claims = st.session_state.get("pending_claims", [])
    count = len(claims)
    confirmed_count = sum(1 for c in claims if c.get("confirmed", True))
    st.metric("Confirmed", f"{confirmed_count} / {count}")

    if not claims:
        st.warning("No claims were extracted. You can add claims manually below, or cancel and try again.")
    else:
        st.markdown("---")
        # Render each claim as checkbox + text input + metadata + remove button
        updated_claims = []
        to_remove = set()

        for i, claim in enumerate(claims):
            col_check, col_text, col_meta, col_remove = st.columns([1, 8, 2, 1])

            with col_check:
                checked = st.checkbox(
                    label="",
                    value=claim.get("confirmed", True),
                    key=f"claim_check_{i}",
                    label_visibility="collapsed",
                )

            with col_text:
                edited_text = st.text_input(
                    label="Claim text",
                    value=claim.get("claim_text", ""),
                    key=f"claim_text_{i}",
                    label_visibility="collapsed",
                )

            with col_meta:
                claim_type = claim.get("claim_type", "claim")
                confidence = claim.get("confidence", "")
                badge_color = "#DBEAFE" if claim_type == "claim" else "#FEF3C7"
                text_color = "#1E40AF" if claim_type == "claim" else "#92400E"
                st.markdown(
                    f'<span style="background:{badge_color};color:{text_color};padding:2px 6px;border-radius:4px;font-size:0.75rem;">'
                    f'{claim_type}</span>'
                    + (f' <span style="font-size:0.75rem;color:#6B7280;">{confidence}</span>' if confidence else ""),
                    unsafe_allow_html=True,
                )

            with col_remove:
                if st.button("🗑️", key=f"claim_remove_{i}", help="Remove this claim"):
                    to_remove.add(i)
                    st.toast("Claim removed")

            if i not in to_remove:
                updated_claim = {**claim, "confirmed": checked, "claim_text": edited_text}
                updated_claims.append(updated_claim)

        # If any removes were clicked, update and rerun
        if to_remove:
            st.session_state.pending_claims = updated_claims
            st.rerun()
        else:
            pass

    st.markdown("---")

    # Add new claim input
    st.subheader("Add a claim")
    col_input, col_add = st.columns([8, 2])
    with col_input:
        new_claim_text = st.text_input(
            "New claim",
            key="new_claim_input",
            placeholder="Type a new claim and click Add",
            label_visibility="collapsed",
        )
    with col_add:
        if st.button("Add", key="add_claim_btn", use_container_width=True):
            if new_claim_text.strip():
                new_claim = {
                    "claim_text": new_claim_text.strip(),
                    "claim_type": "claim",
                    "confidence": "definite",
                    "who_said_it": "",
                    "topic_tags": [],
                    "confirmed": True,
                }
                if "pending_claims" not in st.session_state:
                    st.session_state.pending_claims = []
                st.session_state.pending_claims.append(new_claim)
                st.toast("Claim added!")
                st.rerun()

    st.markdown("---")

    # Action buttons
    col_proceed, col_cancel = st.columns([2, 1])

    with col_proceed:
        proceed_label = "Proceed with these claims"
        if st.button(proceed_label, type="primary", use_container_width=True, key="proceed_btn"):
            # Sync final state of claim texts from session_state widget keys
            current_claims = st.session_state.get("pending_claims", [])
            final_claims = []
            for i, claim in enumerate(current_claims):
                text_key = f"claim_text_{i}"
                check_key = f"claim_check_{i}"
                claim_text = st.session_state.get(text_key, claim.get("claim_text", ""))
                confirmed = st.session_state.get(check_key, claim.get("confirmed", True))
                if confirmed and claim_text.strip():
                    final_claims.append({
                        **claim,
                        "claim_text": claim_text.strip(),
                        "confirmed": True,
                    })

            if not final_claims:
                st.error("No confirmed claims to proceed with. Check at least one claim or add a new one.")
            else:
                st.session_state.pending_claims = final_claims
                set_mode("checking_consistency")
                st.rerun()

    with col_cancel:
        if st.button("Cancel ingestion", use_container_width=True, key="cancel_ingestion_btn"):
            reset_ingestion()
            st.rerun()
