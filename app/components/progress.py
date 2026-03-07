"""
Progress indicator wrapper for the ingestion pipeline.
Wraps st.status to show multi-step pipeline progress.
"""

from contextlib import contextmanager
from typing import Optional

import streamlit as st



class IngestionProgress:
    """
    Wraps st.status to show step-by-step ingestion pipeline progress.
    Usage:
        progress = IngestionProgress()
        with progress.start("Processing session..."):
            progress.update_step("Extracting claims...")
            # do work
            progress.update_step("Claims extracted", n_claims=5)
            progress.complete("Session ingested successfully.")
    """

    def __init__(self):
        self._status = None
        self._completed_steps: list = []

    @contextmanager
    def start(self, label: str = "Processing session..."):
        """Creates the st.status container. Use as a context manager."""
        with st.status(label, expanded=True) as status:
            self._status = status
            self._completed_steps = []
            yield self
            # Don't auto-complete here — caller calls complete() explicitly

    def update_step(self, step_name: str, status: str = "running", n_claims: Optional[int] = None):
        """
        Write a step update to the status container.
        status: "running" | "complete" | "error"
        """
        if self._status is None:
            return

        label = step_name
        if n_claims is not None:
            # Replace "Claims extracted" with actual count
            label = f"Claims extracted (found {n_claims} claims)"

        icon = {
            "running": "\u231b",
            "complete": "\u2713",
            "error": "\u2717",
        }.get(status, "\u231b")

        self._completed_steps.append(f"{icon} {label}")
        # Rewrite all steps so far
        display = "\n".join(self._completed_steps)
        self._status.write(display)

    def complete(self, label: str = "Done."):
        """Mark the status container as complete."""
        if self._status is None:
            return
        self.update_step(label, status="complete")
        self._status.update(label=label, state="complete", expanded=False)


def render_step_indicator(current_step: int, total_steps: int = 4, labels: list = None):
    """Render a horizontal progress indicator. current_step is 1-based."""
    steps = labels if labels else ["Input", "Review Claims", "Consistency Check", "Done"]

    parts = []
    for i, label in enumerate(steps, 1):
        # Determine state for this step
        if i < current_step:
            circle_cls = "completed"
            label_cls = "completed"
        elif i == current_step:
            circle_cls = "active"
            label_cls = "active"
        else:
            circle_cls = "pending"
            label_cls = ""

        # Add connector before steps 2-4
        if i > 1:
            conn_cls = "completed" if i < current_step else "pending"
            parts.append(
                f'<div class="step-connector {conn_cls}"></div>'
            )

        # Circle + label
        parts.append(
            f'<div class="step-item">'
            f'<div class="step-circle {circle_cls}">{i}</div>'
            f'<div class="step-label {label_cls}">{label}</div>'
            f'</div>'
        )

    html = f'<div class="step-indicator">{"".join(parts)}</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_simple_progress(steps: list, current_step: int) -> None:
    """
    Simple non-interactive progress display using st.write.
    Shows all steps with checkmarks for completed ones.
    Used when we can't use the context manager form.
    """
    lines = []
    for i, step in enumerate(steps):
        if i < current_step:
            lines.append(f"\u2713 {step}")
        elif i == current_step:
            lines.append(f"\u231b {step}")
        else:
            lines.append(f"  {step}")
    st.code("\n".join(lines), language=None)
