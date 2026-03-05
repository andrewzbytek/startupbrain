"""
Diff-and-verify living document update logic for Startup Brain.
Implements Section 4.4 of the SPEC: generate a targeted diff, verify it,
then apply it — never rewriting the full document from scratch.
"""

import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_BRAIN_DOC_PATHS = {
    "pitch": Path(__file__).parent.parent / "documents" / "pitch_brain.md",
    "ops": Path(__file__).parent.parent / "documents" / "ops_brain.md",
}

# Backward-compat alias — points to pitch brain path
LIVING_DOC_PATH = _BRAIN_DOC_PATHS["pitch"]


def _doc_path(brain: str = "pitch") -> Path:
    """Return the filesystem path for the given brain's living document."""
    if brain not in _BRAIN_DOC_PATHS:
        logging.warning("Unknown brain value %r — defaulting to pitch", brain)
    return _BRAIN_DOC_PATHS.get(brain, _BRAIN_DOC_PATHS["pitch"])


def read_living_document(brain: str = "pitch") -> str:
    """Read and return the current living document content.

    If the file is missing or empty (e.g. ephemeral filesystem after restart),
    attempts to recover from MongoDB mirror.
    """
    path = _doc_path(brain)
    content = ""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

    if not content:
        # Recover from MongoDB mirror
        try:
            from services.mongo_client import get_living_document
            doc = get_living_document(brain=brain)
            if doc and isinstance(doc.get("content"), str) and doc["content"]:
                content = doc["content"]
                # Write back to disk for current session
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logging.info("Living document (%s) recovered from MongoDB", brain)
                except Exception:
                    pass  # Disk write failed — return content from memory anyway
        except Exception as e:
            logging.warning("Failed to recover living document (%s) from MongoDB: %s", brain, e)

    return content


def write_living_document(content: str, brain: str = "pitch") -> None:
    """Write content to the living document file."""
    path = _doc_path(brain)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def generate_diff(current_doc: str, new_info: str, update_reason: str = "", brain: str = "pitch") -> str:
    """
    Call Sonnet with diff_generate.md prompt to produce a structured diff.

    Args:
        current_doc: Full text of current living document.
        new_info: New information to incorporate.
        update_reason: Context (e.g., session date).
        brain: Which brain document ("pitch" or "ops").

    Returns:
        Raw diff output string from the LLM.
    """
    from services.claude_client import call_sonnet, escape_xml, load_prompt

    prompt_name = "ops_diff_generate" if brain == "ops" else "diff_generate"
    prompt_template = load_prompt(prompt_name)

    prompt = f"""{prompt_template}

<diff_input>
  <current_document>{escape_xml(current_doc)}</current_document>
  <new_information>{escape_xml(new_info)}</new_information>
  <update_reason>{escape_xml(update_reason)}</update_reason>
</diff_input>"""

    result = call_sonnet(prompt, task_type="diff_generate")
    return result["text"]


def verify_diff(original_doc: str, proposed_changes: str, new_info: str, brain: str = "pitch") -> dict:
    """
    Call Sonnet with diff_verify.md prompt to verify the proposed diff.

    Returns:
        dict with keys: verified (bool), notes (str), issues (list of str)
    """
    from services.claude_client import call_sonnet, load_prompt, escape_xml

    prompt_name = "ops_diff_verify" if brain == "ops" else "diff_verify"
    prompt_template = load_prompt(prompt_name)

    prompt = f"""{prompt_template}

<verify_input>
  <original_document>{escape_xml(original_doc)}</original_document>
  <proposed_changes>{escape_xml(proposed_changes)}</proposed_changes>
  <new_information>{escape_xml(new_info)}</new_information>
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
    # Strip wrapping code fences (```markdown ... ``` or ``` ... ```)
    stripped = raw_output.strip()
    if stripped.startswith("```"):
        first_newline = stripped.index("\n") if "\n" in stripped else 3
        stripped = stripped[first_newline + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    raw_output = stripped.strip()

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


def apply_diff(document: str, diff_blocks: list, brain: str = "pitch") -> str:
    """
    Apply parsed diff blocks to the document.
    Handles UPDATE_POSITION, ADD_CHANGELOG, ADD_DECISION, ADD_FEEDBACK,
    ADD_DISMISSED, ADD_HYPOTHESIS, ADD_CONTACT, UPDATE_CONTACT,
    ADD_SECTION actions.

    Args:
        document: The current document content.
        diff_blocks: Parsed diff blocks from ``parse_diff_output``.
        brain: Which brain document ("pitch" or "ops") — threaded to
            brain-aware helpers like ``_add_contact``.

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
        elif action == "ADD_HYPOTHESIS":
            updated = _add_hypothesis(updated, content)
        elif action == "ADD_CONTACT":
            updated = _add_contact(updated, content, brain=brain)
        elif action == "UPDATE_CONTACT":
            name_match = re.search(r"\*\*(.+?)\*\*", content)
            if name_match:
                updated = _update_contact(updated, name_match.group(1), content)
        elif action == "ADD_SECTION":
            updated = _add_section(updated, section, content)

    return updated


def _update_position(doc: str, section: str, new_position_content: str) -> str:
    """Replace the **Current position:** line in the given section."""
    # Extract the subsection name from "Current State → Pricing" format
    if " → " in section:
        _, subsection = section.split(" → ", 1)

        # Strip duplicate header from content if LLM included it
        header_line = f"### {subsection}"
        if new_position_content.startswith(header_line):
            new_position_content = new_position_content[len(header_line):].lstrip("\n")

        # Try sections with **Current position:** format first
        pattern = re.compile(
            rf"(### {re.escape(subsection)}\n)"
            rf"(\*\*Current position:\*\*.*?)(\n\*\*Changelog|\n###|\Z)",
            re.DOTALL,
        )
        def replacer(m):
            return m.group(1) + new_position_content + m.group(3)

        updated = pattern.sub(replacer, doc)
        if updated != doc:
            return updated

        # Fallback for sections without **Current position:** (e.g. Key Assumptions, Open Questions)
        # Replace bare content between section header and next section
        bare_pattern = re.compile(
            rf"(### {re.escape(subsection)}\n)(.*?)(\n###|\n## |\Z)",
            re.DOTALL,
        )
        def bare_replacer(m):
            return m.group(1) + new_position_content + "\n" + m.group(3)

        updated = bare_pattern.sub(bare_replacer, doc)
        if updated != doc:
            return updated

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
    pattern = re.compile(r"(## Dismissed Contradictions\n)(.*?)(\n## |\Z)", re.DOTALL)

    def replacer(m):
        existing = m.group(2).strip()
        if existing.lower().strip() == "[no dismissed contradictions]":
            existing = ""
        if existing:
            return m.group(1) + existing + "\n" + dismissed_content + "\n" + m.group(3)
        return m.group(1) + dismissed_content + "\n" + m.group(3)

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    return doc + "\n\n## Dismissed Contradictions\n" + dismissed_content + "\n"


def _add_hypothesis(doc: str, hypothesis_content: str) -> str:
    """Add a new entry to the Active Hypotheses section."""
    pattern = re.compile(r"(## Active Hypotheses\n)(.*?)(\n## |\Z)", re.DOTALL)

    def replacer(m):
        existing = m.group(2).strip()
        if existing.lower().strip() == "[no hypotheses tracked yet]":
            existing = ""
        return m.group(1) + existing + "\n" + hypothesis_content + "\n" + m.group(3)

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    # Fallback: insert before Decision Log (pitch brain only; ops falls through to append)
    if "## Decision Log" in doc:
        return doc.replace("## Decision Log", "## Active Hypotheses\n" + hypothesis_content + "\n\n## Decision Log")
    return doc + "\n\n## Active Hypotheses\n" + hypothesis_content + "\n"


def _add_contact(doc: str, contact_content: str, brain: str = "pitch") -> str:
    """Add a new entry to the contacts section.

    Pitch brain uses ``### Key Contacts / Prospects`` (subsection under Current State).
    Ops brain uses ``## Contacts / Prospects`` (top-level section).
    """
    if brain == "ops":
        # ops_brain.md uses top-level ## Contacts / Prospects
        section_pattern = re.compile(r"(## Contacts / Prospects\n)(.*?)(\n## |\Z)", re.DOTALL)
        match = section_pattern.search(doc)
        if match:
            existing = match.group(2).strip()
            if existing in ("[No contacts tracked yet]", ""):
                return doc[:match.start(2)] + contact_content + "\n" + doc[match.end(2):]
            return doc[:match.end(2)] + "\n" + contact_content + "\n" + doc[match.end(2):]
        return doc + "\n\n## Contacts / Prospects\n" + contact_content + "\n"

    # Pitch brain: match ### Key Contacts / Prospects within ## Current State
    pattern = re.compile(
        r"(### Key Contacts / Prospects\n)(.*?)(\n###|\n## |\Z)",
        re.DOTALL,
    )

    def replacer(m):
        existing = m.group(2).strip()
        # Replace placeholder or old format with Current position/Changelog
        if existing == "[No contacts tracked yet]":
            existing = ""
        elif "**Current position:**" in existing and "**Changelog:**" in existing:
            # Old format — replace entirely
            existing = ""
        if existing:
            return m.group(1) + existing + "\n" + contact_content + "\n" + m.group(3)
        return m.group(1) + contact_content + "\n" + m.group(3)

    updated = pattern.sub(replacer, doc)
    if updated != doc:
        return updated

    # If section missing, insert before Decision Log
    if "## Decision Log" in doc:
        return doc.replace(
            "## Decision Log",
            "### Key Contacts / Prospects\n" + contact_content + "\n\n## Decision Log",
        )
    return doc + "\n\n### Key Contacts / Prospects\n" + contact_content + "\n"


def _update_contact(doc: str, contact_name: str, updated_fields: str) -> str:
    """Update an existing contact entry by name (case-insensitive match on bold name)."""
    escaped_name = re.escape(contact_name)
    # Match from "- [date] **Name**" through to the next "- [" entry or section/doc boundary
    pattern = re.compile(
        rf"- \[\d{{4}}-\d{{2}}-\d{{2}}\] \*\*{escaped_name}\*\*.*?(?=\n- \[|\n###|\n## |\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    _replacement = updated_fields.strip()
    updated = pattern.sub(lambda _m: _replacement, doc)
    return updated


def _update_hypothesis_status(doc: str, hypothesis_fragment: str, new_status: str, evidence_update: str = "") -> str:
    """Update the status of an existing hypothesis. Finds by bold text fragment."""
    escaped = re.escape(hypothesis_fragment)
    pattern = re.compile(
        rf"(- \[\d{{4}}-\d{{2}}-\d{{2}}\] \*\*{escaped}\*\*\n\s+Status: )\w+( \| .*?\n\s+Evidence: )(.*?)(?=\n- \[|\n## |\Z)",
        re.DOTALL,
    )

    def replacer(m):
        result = m.group(1) + new_status + m.group(2)
        if evidence_update:
            current_evidence = m.group(3).strip()
            if current_evidence == "---":
                result += evidence_update
            else:
                result += current_evidence + "; " + evidence_update
        else:
            result += m.group(3)
        return result

    return pattern.sub(replacer, doc)


def _add_section(doc: str, section: str, section_content: str) -> str:
    """Add an entirely new section to Current State.

    If the section already exists (even with placeholder content like
    '[Not yet defined]'), replace it instead of creating a duplicate.
    Inserts inside ## Current State, before the first ## boundary after it.
    """
    # Extract subsection name from "Current State → Foo" or content header
    subsection = ""
    if " → " in section:
        _, subsection = section.split(" → ", 1)
    else:
        header_match = re.search(r"^### (.+)", section_content)
        if header_match:
            subsection = header_match.group(1).strip()

    # If the subsection already exists in the document, replace it in-place
    if subsection:
        existing_pattern = re.compile(
            rf"(### {re.escape(subsection)}\n)(.*?)(\n###|\n## |\Z)",
            re.DOTALL,
        )
        match = existing_pattern.search(doc)
        if match:
            # Strip the header from section_content if it duplicates the existing one
            content_body = section_content
            header_line = f"### {subsection}"
            if content_body.strip().startswith(header_line):
                content_body = content_body.strip()[len(header_line):].lstrip("\n")
            _g1 = match.group(1)
            _g3 = match.group(3)
            _body = content_body
            return existing_pattern.sub(
                lambda _m: _g1 + _body + "\n" + _g3,
                doc,
            )

    # Section doesn't exist — insert at end of ## Current State
    # Find ## Current State first, then the next ## heading after it
    cs_start = doc.find("\n## Current State")
    if cs_start != -1:
        cs_match = re.search(r"\n(## (?!Current State))", doc[cs_start + 1:])
    else:
        cs_match = re.search(r"\n(## (?!Current State))", doc)
    if cs_match:
        insert_pos = (cs_start + 1 + cs_match.start()) if cs_start != -1 else cs_match.start()
        return doc[:insert_pos] + "\n" + section_content + "\n" + doc[insert_pos:]

    # Fallback: insert before ## Decision Log
    if "## Decision Log" in doc:
        return doc.replace("## Decision Log", section_content + "\n\n## Decision Log")
    return doc + "\n\n" + section_content + "\n"


def _git_commit(message: str, brain: str = "pitch") -> bool:
    """
    Git add and commit the living document.
    Returns True on success, False on failure.
    Skips gracefully if git is not installed or not in a repo (e.g. Render).
    """
    # Check if git is available
    if shutil.which("git") is None:
        return False

    path = _doc_path(brain)
    try:
        repo_root = path.parent.parent
        # Check if we're in a git repo
        check = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(repo_root),
            capture_output=True,
        )
        if check.returncode != 0:
            return False

        subprocess.run(
            ["git", "add", str(path)],
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


def update_document(new_info: str, update_reason: str = "", max_retries: int = 2, brain: str = "pitch") -> dict:
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
        brain: Which brain document to update ("pitch" or "ops").

    Returns:
        dict with keys: success (bool), message (str), changes_applied (int)
    """
    from services.mongo_client import upsert_living_document
    from services.ingestion_lock import acquire_doc_lock, release_doc_lock

    if not acquire_doc_lock(timeout_seconds=60):
        return {"success": False, "message": "Could not acquire document lock — another update is in progress.", "changes_applied": 0}

    try:
        current_doc = read_living_document(brain=brain)
        if not current_doc:
            return {"success": False, "message": "Living document not found.", "changes_applied": 0}

        diff_output = generate_diff(current_doc, new_info, update_reason, brain=brain)
        verification_feedback = ""

        for attempt in range(max_retries + 1):
            if verification_feedback and attempt > 0:
                # Retry with feedback: regenerate diff
                retry_info = f"{new_info}\n\nPrevious verification failed with issues:\n{verification_feedback}"
                diff_output = generate_diff(current_doc, retry_info, update_reason, brain=brain)

            verification = verify_diff(current_doc, diff_output, new_info, brain=brain)

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
            return {"success": True, "message": "No changes needed — information already present.", "changes_applied": 0}

        updated_doc = apply_diff(current_doc, diff_blocks, brain=brain)

        # Write file
        try:
            write_living_document(updated_doc, brain=brain)
        except Exception as e:
            return {"success": False, "message": f"Failed to write living document: {e}", "changes_applied": 0}

        # Mirror to MongoDB
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        upsert_living_document(updated_doc, metadata={"last_updated": date_str, "update_reason": update_reason}, brain=brain)

        # Git commit
        brain_label = "pitch_brain.md" if brain == "pitch" else "ops_brain.md"
        commit_msg = f"Update {brain_label}: {update_reason or 'session update'} ({date_str})"
        git_ok = _git_commit(commit_msg, brain=brain)

        return {
            "success": True,
            "message": f"Document updated successfully. {len(diff_blocks)} change(s) applied."
                       + ("" if git_ok else " (git commit failed — check repo state)"),
            "changes_applied": len(diff_blocks),
        }
    finally:
        release_doc_lock()
