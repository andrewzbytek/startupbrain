"""
Claude API wrapper for Startup Brain.
Handles cost-aware routing between Sonnet and Opus.
Every call logs via cost_tracker.
"""

import os
from pathlib import Path
from typing import Generator, Optional

import streamlit as st

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Model IDs
SONNET_MODEL = "claude-sonnet-4-20250514"
OPUS_MODEL = "claude-opus-4-20250514"

# Tasks that warrant Opus
OPUS_TASKS = {"consistency_pass3", "pitch_generation", "strategic_analysis", "deep_analysis"}

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _get_api_key() -> Optional[str]:
    """Get Anthropic API key from st.secrets or os.environ."""
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, AttributeError, FileNotFoundError):
        return os.environ.get("ANTHROPIC_API_KEY")


def _get_client() -> Optional[object]:
    """Get anthropic client, or None if unavailable."""
    if not ANTHROPIC_AVAILABLE:
        return None
    api_key = _get_api_key()
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def escape_xml(text: str) -> str:
    """Escape user-controlled content for safe XML embedding."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt from prompts/{prompt_name}.md.
    Returns the file contents as a string.
    Raises FileNotFoundError if the prompt doesn't exist.
    """
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def call_sonnet(
    prompt: str,
    system: Optional[str] = None,
    images: Optional[list] = None,
    stream: bool = False,
    task_type: str = "general",
) -> dict:
    """
    Call Claude Sonnet with the given prompt.

    Args:
        prompt: User prompt text.
        system: Optional system prompt.
        images: Optional list of image dicts (base64 encoded) for vision.
        stream: If True, returns a generator yielding text chunks.
        task_type: Task label for cost tracking.

    Returns:
        dict with keys: text, tokens_in, tokens_out, model
        If stream=True, returns a generator that yields text chunks,
        and logs cost after the stream is exhausted.
    """
    from services import cost_tracker

    client = _get_client()
    if client is None:
        return {"text": "Error: Anthropic client unavailable.", "tokens_in": 0, "tokens_out": 0, "model": SONNET_MODEL}

    content = _build_content(prompt, images)
    messages = [{"role": "user", "content": content}]

    kwargs = {
        "model": SONNET_MODEL,
        "max_tokens": 8096,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    if stream:
        return _stream_response(client, kwargs, SONNET_MODEL, task_type, cost_tracker)

    try:
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.log_api_call(SONNET_MODEL, tokens_in, tokens_out, task_type)
        return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out, "model": SONNET_MODEL}
    except Exception as e:
        return {"text": f"Error: {e}", "tokens_in": 0, "tokens_out": 0, "model": SONNET_MODEL}


def call_opus(
    prompt: str,
    system: Optional[str] = None,
    stream: bool = False,
    task_type: str = "deep_analysis",
) -> dict:
    """
    Call Claude Opus with the given prompt.

    Args:
        prompt: User prompt text.
        system: Optional system prompt.
        stream: If True, returns a generator yielding text chunks.
        task_type: Task label for cost tracking.

    Returns:
        dict with keys: text, tokens_in, tokens_out, model
    """
    from services import cost_tracker

    client = _get_client()
    if client is None:
        return {"text": "Error: Anthropic client unavailable.", "tokens_in": 0, "tokens_out": 0, "model": OPUS_MODEL}

    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": OPUS_MODEL,
        "max_tokens": 8096,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    if stream:
        return _stream_response(client, kwargs, OPUS_MODEL, task_type, cost_tracker)

    try:
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_tracker.log_api_call(OPUS_MODEL, tokens_in, tokens_out, task_type)
        return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out, "model": OPUS_MODEL}
    except Exception as e:
        return {"text": f"Error: {e}", "tokens_in": 0, "tokens_out": 0, "model": OPUS_MODEL}


def call_with_routing(
    prompt: str,
    task_type: str,
    system: Optional[str] = None,
    images: Optional[list] = None,
    stream: bool = False,
) -> dict:
    """
    Auto-route to Sonnet or Opus based on task_type and budget.

    Opus tasks: consistency_pass3, pitch_generation, strategic_analysis, deep_analysis
    Everything else: Sonnet
    If over $300/month budget, force Sonnet for all non-explicit Opus requests.

    Args:
        prompt: User prompt text.
        task_type: Determines model routing.
        system: Optional system prompt.
        images: Optional list of image dicts (vision, Sonnet only).
        stream: If True, stream the response.

    Returns:
        dict with keys: text, tokens_in, tokens_out, model
    """
    from services import cost_tracker

    use_opus = task_type in OPUS_TASKS

    # Budget gate: force Sonnet if over $300/month
    if use_opus and cost_tracker.is_over_budget(threshold=300.0):
        use_opus = False

    if use_opus:
        return call_opus(prompt, system=system, stream=stream, task_type=task_type)
    else:
        return call_sonnet(prompt, system=system, images=images, stream=stream, task_type=task_type)


def _build_content(prompt: str, images: Optional[list]) -> list:
    """Build content list for Anthropic messages API (text + optional images)."""
    if not images:
        return [{"type": "text", "text": prompt}]

    content = []
    for img in images:
        # img should be dict with keys: data (base64), media_type
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.get("media_type", "image/jpeg"),
                "data": img["data"],
            },
        })
    content.append({"type": "text", "text": prompt})
    return content


def _stream_response(client, kwargs: dict, model: str, task_type: str, cost_tracker) -> Generator:
    """
    Internal generator that streams the response and logs cost after completion.
    Yields text chunk strings.
    """
    def _generate():
        tokens_in = 0
        tokens_out = 0
        try:
            with client.messages.stream(**kwargs) as stream_ctx:
                for text in stream_ctx.text_stream:
                    yield text
                # After stream completes, get usage
                final = stream_ctx.get_final_message()
                tokens_in = final.usage.input_tokens
                tokens_out = final.usage.output_tokens
        except Exception as e:
            yield f"Error: {e}"
        finally:
            cost_tracker.log_api_call(model, tokens_in, tokens_out, task_type)

    return _generate()
