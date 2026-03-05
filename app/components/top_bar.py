"""
Persistent top bar for Startup Brain.
Renders app title, action buttons, and status pills across all views.
"""

import streamlit as st

from app.state import set_mode


def render_top_bar():
    """Render the persistent top bar with title, actions, and status pills."""
    import time as _time

    # TTL cache for MongoDB calls (lock status, cost, RAG health)
    _cache_key = "_top_bar_cache"
    _cache_ts_key = "_top_bar_cache_ts"
    _TTL = 60  # seconds
    _now = _time.time()
    _use_cache = (
        _cache_key in st.session_state
        and _cache_ts_key in st.session_state
        and _now - st.session_state[_cache_ts_key] < _TTL
    )

    col_title, col_brain, col_spacer, col_actions, col_status = st.columns([2, 1.5, 1.5, 3.5, 2.5])

    with col_title:
        st.markdown(
            '<div class="top-bar-title">Startup Brain</div>'
            '<div class="top-bar-subtitle">Your startup\'s memory</div>',
            unsafe_allow_html=True,
        )

    with col_brain:
        brain_options = ["Pitch", "Ops"]
        current_brain = st.session_state.get("active_brain", "pitch")
        default_idx = 0 if current_brain == "pitch" else 1
        selected = st.radio(
            "Brain",
            brain_options,
            index=default_idx,
            horizontal=True,
            label_visibility="collapsed",
            key="brain_toggle",
        )
        new_brain = selected.lower()
        if new_brain != current_brain:
            st.session_state.active_brain = new_brain
            st.session_state.chat_brain_context = new_brain
            st.session_state.sidebar_data = {}
            st.rerun()

    # col_spacer intentionally left empty

    with col_actions:
        btn_col1, btn_col2 = st.columns(2)
        mode = st.session_state.get("mode", "chat")

        # Check ingestion lock status (with TTL cache)
        ingestion_locked = False
        if _use_cache:
            lock_status = st.session_state[_cache_key].get("lock_status", {})
            ingestion_locked = lock_status.get("locked", False) and not lock_status.get("stale", False)
        else:
            try:
                from services.ingestion_lock import check_lock
                lock_status = check_lock()
                ingestion_locked = lock_status.get("locked", False) and not lock_status.get("stale", False)
            except Exception:
                lock_status = {}

        with btn_col1:
            ingest_disabled = mode != "chat" or ingestion_locked
            brain_label = st.session_state.get("active_brain", "pitch").capitalize()
            ingest_label = "Ingestion in progress..." if ingestion_locked else f"Ingest → {brain_label}"
            if st.button(
                ingest_label,
                type="primary",
                disabled=ingest_disabled,
                use_container_width=True,
                key="top_bar_ingest",
            ):
                if st.session_state.get("active_brain", "pitch") == "ops":
                    set_mode("ops_ingesting")
                else:
                    set_mode("ingesting")
                st.rerun()

        with btn_col2:
            if st.button(
                "Run Audit",
                disabled=mode != "chat" or st.session_state.get("active_brain", "pitch") == "ops",
                use_container_width=True,
                key="top_bar_audit",
            ):
                try:
                    from services.consistency import run_audit

                    with st.spinner("Running audit..."):
                        result = run_audit()
                    discrepancies = result.get("discrepancies", [])
                    if discrepancies:
                        st.warning(
                            f"Audit found {len(discrepancies)} issue(s). "
                            "Review recommended."
                        )
                    else:
                        st.success("Audit clean — no discrepancies found.")
                except Exception as e:
                    import logging
                    logging.error("Audit failed: %s", e)
                    st.warning("Audit failed. Please try again.")

    with col_status:
        # API Cost pill (with TTL cache)
        cost_html = ""
        if _use_cache:
            cost = st.session_state[_cache_key].get("monthly_cost", 0)
        else:
            try:
                from services.cost_tracker import get_monthly_cost
                cost = get_monthly_cost()
            except Exception:
                cost = None

        if cost is not None:
            budget = 300
            ratio = cost / budget if budget else 0
            if ratio < 0.5:
                pill_color = "#3FB950"
            elif ratio < 0.8:
                pill_color = "#D29922"
            else:
                pill_color = "#F85149"
            cost_html = (
                f'<span class="status-pill" style="background:rgba({_hex_to_rgb(pill_color)},0.12);'
                f'color:{pill_color};">${cost:.0f} / ${budget}</span>'
            )
        else:
            cost_html = (
                '<span class="status-pill" style="background:rgba(139,148,158,0.12);'
                'color:#8B949E;">Cost: N/A</span>'
            )

        # RAG Health pill (with TTL cache)
        rag_html = ""
        if _use_cache:
            health = st.session_state[_cache_key].get("rag_health", {})
        else:
            try:
                from services.consistency import check_rag_health
                health = check_rag_health()
            except Exception:
                health = {}

        if health:
            claim_count = health.get("claim_count", 0)
            threshold = health.get("threshold", 200)
            needs_upgrade = health.get("needs_upgrade", False)
            rag_color = "#F85149" if needs_upgrade else "#3FB950"
            rag_html = (
                f'<span class="status-pill" style="background:rgba({_hex_to_rgb(rag_color)},0.12);'
                f'color:{rag_color};margin-left:0.4rem;">'
                f'RAG: {claim_count}/{threshold}</span>'
            )
        else:
            rag_html = (
                '<span class="status-pill" style="background:rgba(139,148,158,0.12);'
                'color:#8B949E;margin-left:0.4rem;">'
                'RAG: N/A</span>'
            )

        # Store cache if we just fetched fresh data
        if not _use_cache:
            st.session_state[_cache_key] = {
                "lock_status": lock_status,
                "monthly_cost": cost,
                "rag_health": health,
            }
            st.session_state[_cache_ts_key] = _now

        st.markdown(
            f'<div style="text-align:right;padding-top:0.5rem;">{cost_html}{rag_html}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<hr style="margin:0.5rem 0 0.75rem;border-color:var(--border-default);">',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    """Convert a hex color like '#3FB950' to an 'r,g,b' string."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
