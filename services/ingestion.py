"""
Ingestion pipeline orchestration for Startup Brain.
Section 3.2 of the SPEC — handles transcript → claims → consistency → document update.
"""

import base64
import re
from datetime import datetime, timezone
from typing import Optional


def _extract_tag(text: str, tag: str) -> str:
    """Extract content of first XML tag from text."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_claims(
    transcript: str,
    participants: str = "",
    topic_hint: str = "",
    whiteboard_text: str = "",
) -> dict:
    """
    Call Sonnet with extraction.md prompt to extract structured claims.

    Args:
        transcript: Clean post-session summary text.
        participants: Who was in the session (optional).
        topic_hint: Rough topic of the session (optional).
        whiteboard_text: Pre-extracted whiteboard text (optional).

    Returns:
        dict with keys:
            session_summary (str)
            topic_tags (list of str)
            claims (list of claim dicts)
            raw (str)
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_template = load_prompt("extraction")

    prompt = f"""{prompt_template}

<session_input>
<participants>{escape_xml(participants)}</participants>
<topic_hint>{escape_xml(topic_hint)}</topic_hint>
<transcript>{escape_xml(transcript)}</transcript>
<whiteboard_extraction>{whiteboard_text}</whiteboard_extraction>
</session_input>"""

    result = call_sonnet(prompt, task_type="extraction")
    raw = result["text"]

    # Parse XML output
    session_summary = _extract_tag(raw, "session_summary")

    topic_tags = re.findall(r"<tag>(.*?)</tag>", _extract_tag(raw, "topic_tags"))

    claims = []
    for m in re.finditer(r"<claim>(.*?)</claim>", raw, re.DOTALL):
        block = m.group(1)
        claim = {
            "claim_text": _extract_tag(block, "claim_text"),
            "claim_type": _extract_tag(block, "claim_type"),
            "confidence": _extract_tag(block, "confidence"),
            "who_said_it": _extract_tag(block, "who_said_it"),
            "topic_tags": re.findall(r"<tag>(.*?)</tag>", _extract_tag(block, "topic_tags")),
            "confirmed": True,  # default confirmed; UI can uncheck
        }
        if claim["claim_text"]:
            claims.append(claim)

    return {
        "session_summary": session_summary,
        "topic_tags": topic_tags,
        "claims": claims,
        "raw": raw,
    }


def process_whiteboard(image_bytes: bytes, transcript_context: str = "", session_date: str = "") -> dict:
    """
    Process a whiteboard photo using Sonnet vision.

    Args:
        image_bytes: Raw image bytes.
        transcript_context: Session transcript for cross-reference.
        session_date: Date string for the session.

    Returns:
        dict with: extraction_confidence, legibility_notes, extracted_content (list),
                   cross_reference (dict), confirmation_message (str), raw (str)
    """
    from services.claude_client import call_sonnet, load_prompt
    from services.mongo_client import insert_whiteboard_extraction

    prompt_template = load_prompt("whiteboard")

    # Encode image as base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Detect media type (simple heuristic based on magic bytes)
    if image_bytes[:3] == b"\xff\xd8\xff":
        media_type = "image/jpeg"
    elif image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        media_type = "image/png"
    else:
        media_type = "image/jpeg"  # default

    images = [{"data": image_b64, "media_type": media_type}]

    prompt = f"""{prompt_template}

<whiteboard_input>
  <image>[attached above]</image>
  <transcript_context>{transcript_context}</transcript_context>
  <session_date>{session_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}</session_date>
</whiteboard_input>"""

    result = call_sonnet(prompt, images=images, task_type="whiteboard")
    raw = result["text"]

    # Parse XML output
    extraction_confidence = _extract_tag(raw, "extraction_confidence")
    legibility_notes = _extract_tag(raw, "legibility_notes")
    confirmation_message = _extract_tag(raw, "confirmation_message")

    extracted_content = []
    for m in re.finditer(r"<item>(.*?)</item>", raw, re.DOTALL):
        block = m.group(1)
        extracted_content.append({
            "type": _extract_tag(block, "type"),
            "content": _extract_tag(block, "content"),
            "location": _extract_tag(block, "location"),
            "legibility": _extract_tag(block, "legibility"),
            "emphasis": _extract_tag(block, "emphasis"),
        })

    # Store extraction in MongoDB
    doc = {
        "session_date": session_date,
        "extraction_confidence": extraction_confidence,
        "legibility_notes": legibility_notes,
        "extracted_content": extracted_content,
        "confirmation_message": confirmation_message,
        "raw_output": raw,
    }
    insert_whiteboard_extraction(doc)

    return {
        "extraction_confidence": extraction_confidence,
        "legibility_notes": legibility_notes,
        "extracted_content": extracted_content,
        "confirmation_message": confirmation_message,
        "raw": raw,
    }


def store_session(
    transcript: str,
    metadata: Optional[dict] = None,
    session_summary: str = "",
    topic_tags: Optional[list] = None,
) -> Optional[str]:
    """
    Save a raw transcript session to MongoDB sessions collection.

    Returns:
        Inserted session_id string, or None on failure.
    """
    from services.mongo_client import insert_session

    doc = {
        "transcript": transcript,
        "summary": session_summary,
        "topic_tags": topic_tags or [],
        "metadata": metadata or {},
        "session_date": (metadata or {}).get("session_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    }
    return insert_session(doc)


def store_confirmed_claims(claims: list, session_id: str) -> list:
    """
    Save each confirmed claim as a separate document in MongoDB claims collection.
    This provides fine-grained RAG retrieval (one embedding per claim).

    Args:
        claims: List of confirmed claim dicts (with confirmed=True).
        session_id: The session_id these claims belong to.

    Returns:
        List of inserted claim ids.
    """
    from services.mongo_client import insert_claim

    inserted_ids = []
    for claim in claims:
        if not claim.get("confirmed", True):
            continue  # Skip unchecked claims
        doc = {
            "session_id": session_id,
            "claim_text": claim.get("claim_text", ""),
            "claim_type": claim.get("claim_type", "claim"),
            "confidence": claim.get("confidence", "definite"),
            "who_said_it": claim.get("who_said_it", ""),
            "topic_tags": claim.get("topic_tags", []),
        }
        claim_id = insert_claim(doc)
        if claim_id:
            inserted_ids.append(claim_id)
    return inserted_ids


def run_ingestion_pipeline(
    transcript: str,
    confirmed_claims: list,
    session_id: str,
    metadata: Optional[dict] = None,
    session_summary: str = "",
) -> dict:
    """
    Orchestrate post-confirmation ingestion:
    1. Run consistency check
    2. Update living document
    3. Store session and claims in MongoDB
    4. Return results

    Args:
        transcript: Original transcript text.
        confirmed_claims: Claims confirmed (and optionally edited) by the founder.
        session_id: Pre-stored session id (or will store now).
        metadata: Session metadata dict.
        session_summary: Summary string from extraction.

    Returns:
        dict with:
            consistency_results (dict)
            document_updated (bool)
            document_update_message (str)
            claims_stored (int)
            session_id (str)
    """
    from services import consistency, document_updater

    # Step 1: Consistency check
    consistency_results = consistency.run_consistency_check(confirmed_claims)

    # Step 2: Update living document
    # Build new_info string from confirmed claims
    date_str = (metadata or {}).get("session_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    update_reason = f"Session {date_str}"
    if metadata and metadata.get("participants"):
        update_reason += f" ({metadata['participants']})"

    # Compile claims into a readable summary for the document updater
    claims_text_parts = [f"Session summary: {session_summary}", "", "Confirmed claims:"]
    for i, claim in enumerate(confirmed_claims, 1):
        claims_text_parts.append(
            f"{i}. [{claim.get('claim_type', 'claim')}] {claim.get('claim_text', '')} "
            f"(confidence: {claim.get('confidence', 'definite')})"
        )
    new_info = "\n".join(claims_text_parts)

    doc_result = document_updater.update_document(new_info, update_reason=update_reason)

    # Step 3: Store session in MongoDB (if not already stored)
    if not session_id:
        session_id = store_session(
            transcript,
            metadata=metadata,
            session_summary=session_summary,
        )

    # Step 4: Store confirmed claims
    claims_stored = 0
    if session_id:
        inserted = store_confirmed_claims(confirmed_claims, session_id)
        claims_stored = len(inserted)

    return {
        "consistency_results": consistency_results,
        "document_updated": doc_result.get("success", False),
        "document_update_message": doc_result.get("message", ""),
        "claims_stored": claims_stored,
        "session_id": session_id,
    }
