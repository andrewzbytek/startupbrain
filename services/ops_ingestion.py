"""
Simplified ingestion pipeline for Ops Brain.
No consistency check, no DeferredWriter — direct document update.
"""

from datetime import datetime, timezone
from typing import Optional


def run_ops_ingestion(
    transcript: str,
    confirmed_claims: list,
    metadata: Optional[dict] = None,
    session_summary: str = "",
    topic_tags: Optional[list] = None,
    session_type: str = "",
    brain: str = "ops",
) -> dict:
    """
    Simplified Ops Brain ingestion pipeline:
    1. Update ops living document with confirmed claims
    2. Store session and claims in MongoDB (tagged brain=brain)
    3. No consistency check, no deferred writes

    Returns:
        dict with: success, document_updated, claims_stored, session_id, message
    """
    from services.document_updater import update_document
    from services.ingestion import store_session, store_confirmed_claims

    metadata = metadata or {}
    date_str = metadata.get("session_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # Build update reason
    if session_type:
        update_reason = f"{session_type} — {date_str}"
    else:
        update_reason = f"Session {date_str}"
    participants = metadata.get("participants", "")
    if participants:
        update_reason += f" ({participants})"

    # Build new_info from confirmed claims
    claims_text_parts = [f"Session summary: {session_summary}", "", "Confirmed items:"]
    for i, claim in enumerate(confirmed_claims, 1):
        claims_text_parts.append(
            f"{i}. [{claim.get('claim_type', 'claim')}] {claim.get('claim_text', '')} "
            f"(confidence: {claim.get('confidence', 'definite')})"
        )
    new_info = "\n".join(claims_text_parts)

    # Update ops document
    doc_result = update_document(new_info, update_reason=update_reason, brain=brain)

    # Store session
    session_id = store_session(
        transcript,
        metadata=metadata,
        session_summary=session_summary,
        topic_tags=topic_tags,
        brain=brain,
    )

    # Store claims
    claims_stored = 0
    if session_id:
        inserted = store_confirmed_claims(
            confirmed_claims, session_id, metadata=metadata, brain=brain,
        )
        claims_stored = len(inserted)

    success = doc_result.get("success", False) or claims_stored > 0

    return {
        "success": success,
        "document_updated": doc_result.get("success", False),
        "document_update_message": doc_result.get("message", ""),
        "changes_applied": doc_result.get("changes_applied", 0),
        "claims_stored": claims_stored,
        "session_id": session_id or "",
        "message": f"Ops ingestion complete: {claims_stored} claims stored."
                   + (f" {doc_result.get('changes_applied', 0)} doc changes." if doc_result.get("success") else ""),
    }
