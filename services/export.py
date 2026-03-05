"""
Full context export for Startup Brain.
Generates a single markdown file containing the living document
plus session history with claims for sharing with external LLMs/advisors.
"""

from datetime import datetime, timezone


def generate_context_export(brain: str = "pitch") -> str:
    """
    Generate a complete context export as a single markdown string.
    Includes the living document + all session history with claims.
    Gracefully handles missing MongoDB.
    """
    from services.document_updater import read_living_document
    from services.mongo_client import get_sessions, get_claims

    lines = []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Header
    lines.append("# Startup Context Export")
    lines.append(f"_Exported: {date_str}_")
    lines.append("")

    # Usage instructions
    lines.append("## How to Use This Document")
    lines.append(
        "This is a complete export of our startup's knowledge base. It contains "
        "our current strategic positions, decision history, and the full "
        "session-by-session record of how we got here. Use this as context for "
        "any AI assistant or share with advisors/investors who need full background."
    )
    lines.append("")

    # Living document
    lines.append("## Living Document")
    lines.append("")
    doc = read_living_document(brain=brain)
    lines.append(doc if doc else "_No living document found._")
    lines.append("")

    # Session history
    lines.append("## Session History")
    lines.append("")

    sessions = get_sessions(limit=100, brain=brain)
    def _safe_sort_dt(s):
        dt = s.get("created_at")
        if dt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    sessions.sort(key=_safe_sort_dt)  # oldest first

    if not sessions:
        lines.append("_No sessions recorded yet._")
    else:
        for i, session in enumerate(sessions, 1):
            meta = session.get("metadata", {})
            session_type = meta.get("session_type", "Session")
            participants = meta.get("participants", "")
            session_date = session.get("session_date", "Unknown date")
            summary = session.get("summary", "")

            # Session header
            header = f"### Session {i} — {session_date}"
            if session_type or participants:
                parts = []
                if session_type:
                    parts.append(session_type)
                if participants:
                    parts.append(participants)
                header += f" ({', '.join(parts)})"
            lines.append(header)

            if summary:
                lines.append(f"**Summary:** {summary}")
            lines.append("")

            # Claims for this session
            session_id = str(session["_id"])
            claims = get_claims(session_id=session_id, limit=500)
            claims.sort(key=lambda c: c.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))  # chronological

            if claims:
                lines.append(f"**Claims extracted ({len(claims)}):**")
                for claim in claims:
                    confidence = claim.get("confidence", "unknown")
                    claim_text = claim.get("claim_text", "")
                    lines.append(f"- [{confidence}] {claim_text}")
            else:
                lines.append("_No claims extracted._")

            lines.append("")

    return "\n".join(lines)
