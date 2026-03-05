"""
Prompt file integrity tests for Startup Brain.
Verifies all 14 prompt files exist, are loadable, non-empty, and valid UTF-8.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock streamlit before importing any services
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = {}
sys.modules.setdefault("streamlit", mock_st)

import pytest

from services.claude_client import PROMPTS_DIR, load_prompt

# All 14 prompt files (12 from SPEC + 2 ops-brain prompts)
ALL_PROMPT_NAMES = [
    "extraction",
    "ops_extraction",
    "consistency_pass1",
    "consistency_pass2",
    "consistency_pass3",
    "diff_generate",
    "ops_diff_generate",
    "diff_verify",
    "pushback",
    "evolution",
    "feedback_pattern",
    "pitch_generation",
    "whiteboard",
    "audit",
]


# ---------------------------------------------------------------------------
# Parametrized tests over all 14 prompts
# ---------------------------------------------------------------------------

class TestPromptFilesExist:
    """Verify prompt files are present on disk."""

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_prompt_file_exists(self, prompt_name):
        """Each prompt .md file must exist in the prompts directory."""
        path = PROMPTS_DIR / f"{prompt_name}.md"
        assert path.exists(), f"Prompt file missing: {path}"

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_prompt_file_is_file(self, prompt_name):
        """Each prompt path must be a regular file, not a directory."""
        path = PROMPTS_DIR / f"{prompt_name}.md"
        assert path.is_file(), f"Prompt path is not a file: {path}"


class TestLoadPrompt:
    """Verify load_prompt returns valid content for all prompts."""

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_load_prompt_returns_string(self, prompt_name):
        """load_prompt must return a str, not bytes."""
        result = load_prompt(prompt_name)
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_load_prompt_non_empty(self, prompt_name):
        """load_prompt must return a non-empty string."""
        result = load_prompt(prompt_name)
        assert len(result) > 0, f"Prompt '{prompt_name}' loaded as empty string"

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_load_prompt_has_meaningful_content(self, prompt_name):
        """Prompt content should be at least 50 characters (not just whitespace)."""
        result = load_prompt(prompt_name)
        assert len(result.strip()) >= 50, (
            f"Prompt '{prompt_name}' has suspiciously short content ({len(result.strip())} chars)"
        )


class TestPromptContentValidity:
    """Verify prompt file contents are valid UTF-8 and well-formed."""

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_prompt_valid_utf8(self, prompt_name):
        """Prompt files must be valid UTF-8."""
        path = PROMPTS_DIR / f"{prompt_name}.md"
        # Reading with encoding='utf-8' should not raise
        content = path.read_text(encoding="utf-8")
        assert content is not None

    @pytest.mark.parametrize("prompt_name", ALL_PROMPT_NAMES)
    def test_prompt_no_null_bytes(self, prompt_name):
        """Prompt files must not contain null bytes (corruption indicator)."""
        content = load_prompt(prompt_name)
        assert "\x00" not in content, f"Prompt '{prompt_name}' contains null bytes"


class TestPromptErrorHandling:
    """Verify error handling for missing or invalid prompts."""

    def test_nonexistent_prompt_raises_file_not_found(self):
        """Loading a prompt that does not exist must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt_xyz")

    def test_nonexistent_prompt_with_empty_name(self):
        """Loading an empty prompt name should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_prompt("")

    def test_nonexistent_prompt_with_path_traversal(self):
        """Prompt names with path traversal should fail gracefully."""
        with pytest.raises((FileNotFoundError, OSError)):
            load_prompt("../../etc/passwd")


class TestPromptsDirectory:
    """Verify the prompts directory structure."""

    def test_prompts_dir_exists(self):
        """The prompts directory must exist."""
        assert PROMPTS_DIR.exists(), f"Prompts directory missing: {PROMPTS_DIR}"

    def test_prompts_dir_is_directory(self):
        """The prompts path must be a directory."""
        assert PROMPTS_DIR.is_dir(), f"PROMPTS_DIR is not a directory: {PROMPTS_DIR}"

    def test_prompts_dir_contains_at_least_14_md_files(self):
        """The prompts directory should contain at least the 14 expected .md files."""
        md_files = list(PROMPTS_DIR.glob("*.md"))
        assert len(md_files) >= 14, (
            f"Expected at least 14 .md files, found {len(md_files)}: "
            f"{[f.stem for f in md_files]}"
        )

    def test_all_expected_prompts_present(self):
        """All 14 expected prompt names should be present in the directory."""
        existing_stems = {f.stem for f in PROMPTS_DIR.glob("*.md")}
        missing = set(ALL_PROMPT_NAMES) - existing_stems
        assert not missing, f"Missing prompt files: {missing}"
