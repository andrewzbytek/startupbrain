"""
Persistent top bar for Startup Brain.
Renders app title, action buttons, and status pills across all views.
"""

import streamlit as st

from app.state import set_mode


def render_top_bar():
    """Render the persistent top bar with title, actions, and status pills."""
    col_title, col_spacer, col_actions, col_status = st.columns([2, 3, 3.5, 2.5])

    with col_title:
        st.markdown(
            '<div class="top-bar-title">Startup Brain</div>'
            '<div class="top-bar-subtitle">Your startup\'s memory</div>',
            unsafe_allow_html=True,
        )

    # col_spacer intentionally left empty

    with col_actions:
        btn_col1, btn_col2 = st.columns(2)
        mode = st.session_state.get("mode", "chat")

        with btn_col1:
            if st.button(
                "Ingest Session",
                type="primary",
                disabled=mode != "chat",
                use_container_width=True,
                key="top_bar_ingest",
            ):
                set_mode("ingesting")
                st.rerun()

        with btn_col2:
            if st.button(
                "Run Audit",
                disabled=mode != "chat",
                use_container_width=True,
                key="top_bar_audit",
            ):
                try:
                    from services.consistency import run_audit

                    with st.spinner("Running audit..."):
                        result = run_audit()
                    if result.get("has_contradictions"):
                        st.warning(
                            f"Audit found {result.get('contradiction_count', 0)} issue(s). "
                            "Review recommended."
                        )
                    else:
                        st.success("Audit clean — no contradictions found.")
                except Exception as e:
                    st.warning(f"Audit failed: {e}")

    with col_status:
        # API Cost pill
        cost_html = ""
        try:
            from services.cost_tracker import get_monthly_cost

            cost = get_monthly_cost()
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
        except Exception:
            cost_html = (
                '<span class="status-pill" style="background:rgba(139,148,158,0.12);'
                'color:#8B949E;">Cost: N/A</span>'
            )

        # RAG Health pill
        rag_html = ""
        try:
            from services.consistency import check_rag_health

            health = check_rag_health()
            claim_count = health.get("claim_count", 0)
            threshold = health.get("threshold", 200)
            needs_upgrade = health.get("needs_upgrade", False)
            rag_color = "#F85149" if needs_upgrade else "#3FB950"
            rag_html = (
                f'<span class="status-pill" style="background:rgba({_hex_to_rgb(rag_color)},0.12);'
                f'color:{rag_color};margin-left:0.4rem;">'
                f'RAG: {claim_count}/{threshold}</span>'
            )
        except Exception:
            rag_html = (
                '<span class="status-pill" style="background:rgba(139,148,158,0.12);'
                'color:#8B949E;margin-left:0.4rem;">'
                'RAG: N/A</span>'
            )

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
