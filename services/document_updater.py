"""
Diff-and-verify living document update logic for Startup Brain.
Implements Section 4.4 of the SPEC: generate a targeted diff, verify it,
then apply it — never rewriting the full document from scratch.
"""

import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LIVING_DOC_PATH = Path(__file__).parent.parent / "documents" / "startup_brain.md"


def read_living_document() -> str:
    """Read and return the current living document content."""
    if not LIVING_DOC_PATH.exists():
        return ""
    with open(LIVING_DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def write_living_document(content: str) -> None:
    """Write content to the living document file."""
    LIVING_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIVING_DOC_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def generate_diff(current_doc: str, new_info: str, update_reason: str = "") -> str:
    """
    Call Sonnet with diff_generate.md prompt to produce a structured diff.

    Args:
        current_doc: Full text of current startup_brain.md.
        new_info: New information to incorporate.
        update_reason: Context (e.g., session date).

    Returns:
        Raw diff output string from the LLM.
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_template = load_prompt("diff_generate")

    prompt = f"""{prompt_template}

<diff_input>
  <current_document>{current_doc}</current_document>
  <new_information>{escape_xml(new_info)}</new_information>
  <update_reason>{escape_xml(update_reason)}</update_reason>
</diff_input>"""

    result = call_sonnet(prompt, task_type="diff_generate")
    return result["text"]


def verify_diff(original_doc: str, proposed_changes: str, new_info: str) -> dict:
    """
    Call Sonnet with diff_verify.md prompt to verify the proposed diff.

    Returns:
        dict with keys: verified (bool), notes (str), issues (list of str)
    """
    from services.claude_client import call_sonnet, load_prompt

    prompt_template = load_prompt("diff_verify")

    prompt = f"""{prompt_template}

<verify_input>
  <original_document>{original_doc}</original_document>
  <proposed_changes>{proposed_changes}</proposed_changes>
  <new_information>{new_info}</new_information>
</verify_input>"""

    result = call_sonnet(prompt, task_type="diff_verify")
    raw = result["text"]

    # Parse the XML response
    verified = "<verdict>VERIFIED</verdict>" in raw
    issues = []
    if not verified:
        # Extract issue descriptions
        issue_matches = re.findall(r"<description>(.*?)</description>", raw, re.DOTALL)
        issues = [m.strip() for m in issue_matches]

    notes_match = re.search(r"<notes>(.*?)</notes>", raw, re.DOTALL)
    notes = notes_match.group(1).strip() if notes_match else ""

    return {"verified": verified, "notes": notes, "issues": issues, "raw": raw}


def parse_diff_output(raw_output: str) -> list:
    """
    Parse the structured diff format from LLM response.
    Each block has: SECTION, ACTION, CONTENT.

    Returns:
        List of dicts: [{section, action, content}, ...]
    """
    blocks = []
    # Split on double newlines between blocks
    # Each block starts with "SECTION:"
    pattern = re.compile(
        r"SECTION:\s*(.+?)\nACTION:\s*(.+?)\nCONTENT:\n(.*?)(?=\nSECTION:|\Z)",
        re.DOTALL,
    )
    for match in pattern.finditer(raw_output):
        blocks.append({
            "section": match.group(1).strip(),
            "action": match.group(2).strip(),
            "content": match.group(3).strip(),
        })
    return blocks


def apply_diff(document: str, diff_blocks: list) -> str:
    """
    Apply parsed diff blocks to the document.
    Handles UPDATE_POSITION, ADD_CHANGELOG, ADD_DECISION, ADD_FEEDBACK,
    ADD_DISMISSED, ADD_SECTION actions.

    Returns the updated document string.
    """
    updated = document

    for block in diff_blocks:
        action = block["action"]
        section = block["section"]
        content = block["content"]

        if action == "UPDATE_POSITION":
            updated = _update_position(updated, section, content)
        elif action == "ADD_CHANGELOG":
            updated = _add_changelog(updated, section, content)
        elif action == "ADD_DECISION":
            updated = _add_decision(updated, content)
        elif action == "ADD_FEEDBACK":
            updated = _add_feedback(updated, content)
        elif action == "ADD_DISMISSED":
            updated = _add_dismissed(updated, content)
        elif action == "ADD_SECTION":
            updated = _add_section(updated, section, content)

    return updated


def _update_position(doc: str, section: str, new_position_content: str) -> str:
    """Replace the **Current position:** line in the given section."""
    # Find the section header and replace the Current position line
    # Section headers look like "### Target Market / Initial Customer"
    # We need to find the section and replace the "**Current position:**" line

    # Extract the subsection name from "Current State → Pricing" format
    if " → " in section:
        _, subsection = section.split(" → ", 1)
        pattern = re.compile(
            rf"(### {re.escape(subsection)}\n)"
            rf"(\*\*Current position:\*\*.*?)(\n\*\*Changelog|\n###|\Z)",
            re.DOTALL,
        )
        replacement = rf"\g<1>{new_position_content}\3"
        updated = pattern.sub(replacement, doc)
        if updated != doc:
            return updated

    # Fallback: replace first occurrence of Current position after section header
    logging.warning("_update_position: section '%s' not found in document, returning unmodified", section)
    return doc


def _add_changelog(doc: str, section: str, new_entry: str) -> str:
    """Append a changelog entry to the given section."""
    if " → " in section:
        _, subsection = section.split(" → ", 1)
        # Find "**Changelog:**" under this subsection and append the entry
        pattern = re.compile(
            rf"(### {re.escape(subsection)}.*?\*\*Changelog:\*\*\n)(.*?)(\n###|\n## |\Z)",
            re.DOTALL,
        )

        def replacer(m):
            return m.group(1) + m.group(2) + new_entry + "\n" + m.group(3)

        updated = pattern.sub(replacer, doc)
        if updated != doc:
            return updated

    # If no Changelog section found, just append entry after section
    logging.warning("_add_changelog: section '%s' not found in document, returning unmodified", section)
    return doc


def _add_decision(doc: str, decision_content: str) -> str:
    """Add a new entry to the Decision Log section."""
    # Find "## Decision Log" and append after the last entry
    pattern = re.compile(r"(## Decision Log\n)(.*?)(\n## |\Z)", re.DOTALL)

    def replacer(m):
        return m.group(1) + m.group(2) + "\n" + decision_content + "\n" + m.group(3)

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    # If Decision Log section missing, append at end
    return doc + "\n\n## Decision Log\n\n" + decision_content + "\n"


def _add_feedback(doc: str, feedback_content: str) -> str:
    """Add a new entry to the Feedback Tracker section."""
    pattern = re.compile(r"(## Feedback Tracker\n)(.*?)(\n## |\Z)", re.DOTALL)

    def replacer(m):
        return m.group(1) + m.group(2) + "\n" + feedback_content + "\n" + m.group(3)

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    return doc + "\n\n## Feedback Tracker\n\n" + feedback_content + "\n"


def _add_dismissed(doc: str, dismissed_content: str) -> str:
    """Add a new entry to the Dismissed Contradictions section."""
    pattern = re.compile(r"(## Dismissed Contradictions\n)(.*?)(\Z)", re.DOTALL)

    def replacer(m):
        existing = m.group(2).strip()
        if existing == "[No dismissed contradictions]":
            existing = ""
        return m.group(1) + existing + "\n" + dismissed_content + "\n"

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    return doc + "\n\n## Dismissed Contradictions\n" + dismissed_content + "\n"


def _add_section(doc: str, section: str, section_content: str) -> str:
    """Add an entirely new section to Current State."""
    # Insert before "## Decision Log"
    if "## Decision Log" in doc:
        return doc.replace("## Decision Log", section_content + "\n\n## Decision Log")
    return doc + "\n\n" + section_content + "\n"


def _git_commit(message: str) -> bool:
    """
    Git add and commit the living document.
    Returns True on success, False on failure.
    """
    try:
        repo_root = LIVING_DOC_PATH.parent.parent
        subprocess.run(
            ["git", "add", str(LIVING_DOC_PATH)],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False


def update_document(new_info: str, update_reason: str = "", max_retries: int = 2) -> dict:
    """
    Full diff-and-verify orchestration:
    1. Read current document
    2. Generate diff
    3. Verify diff (retry up to max_retries with feedback if verification fails)
    4. Apply changes
    5. Write file
    6. Mirror to MongoDB
    7. Git commit

    Args:
        new_info: New information to incorporate.
        update_reason: Context for changelog (e.g., session date and topic).
        max_retries: Max retries if verification fails.

    Returns:
        dict with keys: success (bool), message (str), changes_applied (int)
    """
    from services.mongo_client import upsert_living_document

    current_doc = read_living_document()
    if not current_doc:
        return {"success": False, "message": "Living document not found.", "changes_applied": 0}

    diff_output = generate_diff(current_doc, new_info, update_reason)
    verification_feedback = ""

    for attempt in range(max_retries + 1):
        verify_prompt = new_info
        if verification_feedback and attempt > 0:
            # Retry with feedback: regenerate diff
            retry_info = f"{new_info}\n\nPrevious verification failed with issues:\n{verification_feedback}"
            diff_output = generate_diff(current_doc, retry_info, update_reason)

        verification = verify_diff(current_doc, diff_output, new_info)

        if verification["verified"]:
            break

        verification_feedback = "\n".join(verification["issues"])
        if attempt == max_retries:
            return {
                "success": False,
                "message": f"Diff verification failed after {max_retries + 1} attempts: {verification_feedback}",
                "changes_applied": 0,
            }

    # Parse and apply diff
    diff_blocks = parse_diff_output(diff_output)
    if not diff_blocks:
        return {"success": False, "message": "No changes detected in diff output.", "changes_applied": 0}

    updated_doc = apply_diff(current_doc, diff_blocks)

    # Write file
    try:
        write_living_document(updated_doc)
    except Exception as e:
        return {"success": False, "message": f"Failed to write living document: {e}", "changes_applied": 0}

    # Mirror to MongoDB
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    upsert_living_document(updated_doc, metadata={"last_updated": date_str, "update_reason": update_reason})

    # Git commit
    commit_msg = f"Update startup_brain.md: {update_reason or 'session update'} ({date_str})"
    git_ok = _git_commit(commit_msg)

    return {
        "success": True,
        "message": f"Document updated successfully. {len(diff_blocks)} change(s) applied."
                   + ("" if git_ok else " (git commit failed — check repo state)"),
        "changes_applied": len(diff_blocks),
    }
