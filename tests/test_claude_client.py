"""
Unit tests for services/claude_client.py.
All tests run without API keys, network access, or MongoDB.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Mock streamlit before importing the module under test
# ---------------------------------------------------------------------------
mock_st = MagicMock()
mock_st.cache_resource = lambda f=None, **kw: (lambda fn: fn) if f is None else f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)


# ---------------------------------------------------------------------------
# _get_api_key tests
# ---------------------------------------------------------------------------

class TestGetApiKey:
    """Tests for _get_api_key: retrieves key from st.secrets or os.environ."""

    def test_key_from_secrets(self):
        """st.secrets should be checked first."""
        import services.claude_client as cc
        fake_secrets = MagicMock()
        fake_secrets.__getitem__ = MagicMock(return_value="sk-secret")
        with patch.object(cc, "st", MagicMock(secrets=fake_secrets)):
            result = cc._get_api_key()
            assert result == "sk-secret"

    def test_key_from_env(self):
        """Falls back to os.environ when st.secrets raises KeyError."""
        import services.claude_client as cc
        fake_secrets = MagicMock()
        fake_secrets.__getitem__ = MagicMock(side_effect=KeyError("ANTHROPIC_API_KEY"))
        with patch.object(cc, "st", MagicMock(secrets=fake_secrets)), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-key"}):
            result = cc._get_api_key()
            assert result == "sk-env-key"

    def test_key_neither_source(self):
        """Returns None when neither st.secrets nor os.environ has the key."""
        import services.claude_client as cc
        fake_secrets = MagicMock()
        fake_secrets.__getitem__ = MagicMock(side_effect=KeyError("ANTHROPIC_API_KEY"))
        env_copy = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.object(cc, "st", MagicMock(secrets=fake_secrets)), \
             patch.dict(os.environ, env_copy, clear=True):
            result = cc._get_api_key()
            assert result is None

    def test_secrets_takes_precedence(self):
        """st.secrets should take precedence over os.environ."""
        import services.claude_client as cc
        fake_secrets = MagicMock()
        fake_secrets.__getitem__ = MagicMock(return_value="sk-secrets-win")
        with patch.object(cc, "st", MagicMock(secrets=fake_secrets)), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-loses"}):
            result = cc._get_api_key()
            assert result == "sk-secrets-win"


# ---------------------------------------------------------------------------
# _get_client tests
# ---------------------------------------------------------------------------

class TestGetClient:
    """Tests for _get_client: creates Anthropic client or returns None."""

    def test_returns_client_when_available(self):
        """Should return an Anthropic client when SDK and key are available."""
        import services.claude_client as cc
        mock_anthropic = MagicMock()
        mock_client_instance = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client_instance

        original = cc.ANTHROPIC_AVAILABLE
        try:
            cc.ANTHROPIC_AVAILABLE = True
            with patch.object(cc, "anthropic", mock_anthropic, create=True), \
                 patch.object(cc, "_get_api_key", return_value="sk-test"):
                result = cc._get_client()
                assert result is mock_client_instance
                mock_anthropic.Anthropic.assert_called_once_with(api_key="sk-test")
        finally:
            cc.ANTHROPIC_AVAILABLE = original

    def test_returns_none_without_sdk(self):
        """Should return None when ANTHROPIC_AVAILABLE is False."""
        import services.claude_client as cc
        original = cc.ANTHROPIC_AVAILABLE
        try:
            cc.ANTHROPIC_AVAILABLE = False
            result = cc._get_client()
            assert result is None
        finally:
            cc.ANTHROPIC_AVAILABLE = original

    def test_returns_none_without_key(self):
        """Should return None when no API key is found."""
        import services.claude_client as cc
        original = cc.ANTHROPIC_AVAILABLE
        try:
            cc.ANTHROPIC_AVAILABLE = True
            with patch.object(cc, "_get_api_key", return_value=None):
                result = cc._get_client()
                assert result is None
        finally:
            cc.ANTHROPIC_AVAILABLE = original


# ---------------------------------------------------------------------------
# escape_xml tests
# ---------------------------------------------------------------------------

class TestEscapeXml:
    """Tests for escape_xml: escapes special characters for XML embedding."""

    def test_ampersand(self):
        from services.claude_client import escape_xml
        assert escape_xml("a & b") == "a &amp; b"

    def test_less_than(self):
        from services.claude_client import escape_xml
        assert escape_xml("a < b") == "a &lt; b"

    def test_greater_than(self):
        from services.claude_client import escape_xml
        assert escape_xml("a > b") == "a &gt; b"

    def test_double_quote(self):
        from services.claude_client import escape_xml
        assert escape_xml('say "hello"') == "say &quot;hello&quot;"

    def test_single_quote(self):
        from services.claude_client import escape_xml
        assert escape_xml("it's") == "it&apos;s"

    def test_all_chars(self):
        from services.claude_client import escape_xml
        result = escape_xml('<tag attr="val">&\'data\'</tag>')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result
        assert "&apos;" in result


# ---------------------------------------------------------------------------
# load_prompt tests
# ---------------------------------------------------------------------------

class TestLoadPrompt:
    """Tests for load_prompt: loads prompt markdown files from /prompts."""

    EXPECTED_PROMPTS = [
        "extraction", "consistency_pass1", "consistency_pass2", "consistency_pass3",
        "diff_generate", "diff_verify", "pushback", "evolution",
        "feedback_pattern", "pitch_generation", "whiteboard", "audit",
    ]

    @pytest.mark.parametrize("prompt_name", EXPECTED_PROMPTS)
    def test_loads_prompt_file(self, prompt_name):
        """Each known prompt file should load without error."""
        from services.claude_client import load_prompt
        result = load_prompt(prompt_name)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nonexistent_raises_file_not_found(self):
        """Should raise FileNotFoundError for a missing prompt."""
        from services.claude_client import load_prompt
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt_xyz")

    def test_returns_string_type(self):
        """Return type should be str."""
        from services.claude_client import load_prompt
        result = load_prompt("extraction")
        assert type(result) is str


# ---------------------------------------------------------------------------
# call_sonnet tests
# ---------------------------------------------------------------------------

class TestCallSonnet:
    """Tests for call_sonnet: calls Claude Sonnet and returns structured result."""

    def _make_mock_response(self, text="Hello", tokens_in=100, tokens_out=50):
        resp = MagicMock()
        content_block = MagicMock()
        content_block.text = text
        resp.content = [content_block]
        resp.usage.input_tokens = tokens_in
        resp.usage.output_tokens = tokens_out
        return resp

    def test_success_returns_dict(self):
        """Successful call should return dict with text, tokens, model."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_response("Test response")

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call") as mock_log:
            result = cc.call_sonnet("Hello")
            assert result["text"] == "Test response"
            assert result["tokens_in"] == 100
            assert result["tokens_out"] == 50
            assert result["model"] == cc.SONNET_MODEL

    def test_empty_response_content(self):
        """Should return error dict when response.content is empty."""
        mock_client = MagicMock()
        resp = MagicMock()
        resp.content = []
        mock_client.messages.create.return_value = resp

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            result = cc.call_sonnet("Hello")
            assert "Error" in result["text"]
            assert result["tokens_in"] == 0

    def test_api_exception_returns_error(self):
        """API exception should be caught and returned as sanitized error dict."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API rate limit exceeded")

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            result = cc.call_sonnet("Hello")
            assert "unavailable" in result["text"].lower()
            # Raw exception details should NOT leak to user
            assert "API rate limit exceeded" not in result["text"]

    def test_cost_logged_via_tracker(self):
        """Successful call should log cost via cost_tracker."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_response()

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call") as mock_log:
            cc.call_sonnet("Hello", task_type="extraction")
            mock_log.assert_called_once_with(cc.SONNET_MODEL, 100, 50, "extraction")

    def test_no_client_returns_error(self):
        """Should return error when client is None."""
        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=None):
            result = cc.call_sonnet("Hello")
            assert "Anthropic client unavailable" in result["text"]
            assert result["tokens_in"] == 0
            assert result["tokens_out"] == 0

    def test_system_prompt_passed(self):
        """System prompt should be passed in kwargs to API."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_response()

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            cc.call_sonnet("Hello", system="Be helpful")
            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs.get("system") == "Be helpful" or \
                   (len(call_kwargs) > 1 and call_kwargs[1].get("system") == "Be helpful")


# ---------------------------------------------------------------------------
# call_opus tests
# ---------------------------------------------------------------------------

class TestCallOpus:
    """Tests for call_opus: calls Claude Opus and returns structured result."""

    def _make_mock_response(self, text="Deep analysis", tokens_in=200, tokens_out=100):
        resp = MagicMock()
        content_block = MagicMock()
        content_block.text = text
        resp.content = [content_block]
        resp.usage.input_tokens = tokens_in
        resp.usage.output_tokens = tokens_out
        return resp

    def test_success_structure(self):
        """Successful Opus call should return dict with correct model."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_response()

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            result = cc.call_opus("Analyze this")
            assert result["text"] == "Deep analysis"
            assert result["model"] == cc.OPUS_MODEL
            assert result["tokens_in"] == 200
            assert result["tokens_out"] == 100

    def test_api_exception(self):
        """API exception should be caught and returned as sanitized error dict."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Server error")

        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=mock_client), \
             patch("services.cost_tracker.log_api_call"):
            result = cc.call_opus("Analyze this")
            assert "unavailable" in result["text"].lower()
            # Raw exception details should NOT leak to user
            assert "Server error" not in result["text"]

    def test_no_client_returns_error(self):
        """Should return error when client is None."""
        import services.claude_client as cc
        with patch.object(cc, "_get_client", return_value=None):
            result = cc.call_opus("Analyze this")
            assert "Anthropic client unavailable" in result["text"]
            assert result["model"] == cc.OPUS_MODEL


# ---------------------------------------------------------------------------
# call_with_routing tests
# ---------------------------------------------------------------------------

class TestCallWithRouting:
    """Tests for call_with_routing: routes to Sonnet or Opus based on task type."""

    def test_opus_task_routes_to_opus(self):
        """OPUS_TASKS should route to call_opus."""
        import services.claude_client as cc
        with patch.object(cc, "call_opus", return_value={"text": "opus"}) as mock_opus, \
             patch.object(cc, "call_sonnet") as mock_sonnet, \
             patch("services.cost_tracker.is_over_budget", return_value=False):
            result = cc.call_with_routing("Test", task_type="consistency_pass3")
            mock_opus.assert_called_once()
            mock_sonnet.assert_not_called()
            assert result["text"] == "opus"

    @pytest.mark.parametrize("task", ["consistency_pass3", "pitch_generation", "strategic_analysis", "deep_analysis"])
    def test_all_opus_tasks(self, task):
        """Each task in OPUS_TASKS should route to Opus."""
        import services.claude_client as cc
        with patch.object(cc, "call_opus", return_value={"text": "opus"}) as mock_opus, \
             patch.object(cc, "call_sonnet"), \
             patch("services.cost_tracker.is_over_budget", return_value=False):
            cc.call_with_routing("Test", task_type=task)
            mock_opus.assert_called_once()

    def test_non_opus_task_routes_to_sonnet(self):
        """Non-OPUS tasks should route to call_sonnet."""
        import services.claude_client as cc
        with patch.object(cc, "call_opus") as mock_opus, \
             patch.object(cc, "call_sonnet", return_value={"text": "sonnet"}) as mock_sonnet, \
             patch("services.cost_tracker.is_over_budget", return_value=False):
            result = cc.call_with_routing("Test", task_type="extraction")
            mock_sonnet.assert_called_once()
            mock_opus.assert_not_called()
            assert result["text"] == "sonnet"

    def test_budget_gate_forces_sonnet(self):
        """When over budget, even OPUS tasks should route to Sonnet."""
        import services.claude_client as cc
        with patch.object(cc, "call_opus") as mock_opus, \
             patch.object(cc, "call_sonnet", return_value={"text": "sonnet"}) as mock_sonnet, \
             patch("services.cost_tracker.is_over_budget", return_value=True):
            result = cc.call_with_routing("Test", task_type="consistency_pass3")
            mock_sonnet.assert_called_once()
            mock_opus.assert_not_called()


# ---------------------------------------------------------------------------
# _build_content tests
# ---------------------------------------------------------------------------

class TestBuildContent:
    """Tests for _build_content: builds content list for Anthropic API."""

    def test_text_only(self):
        """Text only should return single text block."""
        from services.claude_client import _build_content
        result = _build_content("Hello", None)
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello"

    def test_text_with_images(self):
        """Text + images should return image blocks followed by text block."""
        from services.claude_client import _build_content
        images = [{"data": "base64data", "media_type": "image/png"}]
        result = _build_content("Describe this", images)
        assert len(result) == 2
        assert result[0]["type"] == "image"
        assert result[0]["source"]["type"] == "base64"
        assert result[0]["source"]["data"] == "base64data"
        assert result[0]["source"]["media_type"] == "image/png"
        assert result[1]["type"] == "text"

    def test_multiple_images(self):
        """Multiple images should create multiple image blocks before text."""
        from services.claude_client import _build_content
        images = [
            {"data": "img1", "media_type": "image/jpeg"},
            {"data": "img2", "media_type": "image/png"},
        ]
        result = _build_content("Describe", images)
        assert len(result) == 3
        assert result[0]["type"] == "image"
        assert result[1]["type"] == "image"
        assert result[2]["type"] == "text"
        assert result[0]["source"]["data"] == "img1"
        assert result[1]["source"]["data"] == "img2"

    def test_default_media_type(self):
        """Missing media_type should default to image/jpeg."""
        from services.claude_client import _build_content
        images = [{"data": "base64data"}]
        result = _build_content("Describe", images)
        assert result[0]["source"]["media_type"] == "image/jpeg"

    def test_empty_images_list(self):
        """Empty images list should be treated as no images (falsy)."""
        from services.claude_client import _build_content
        result = _build_content("Hello", [])
        assert len(result) == 1
        assert result[0]["type"] == "text"


# ---------------------------------------------------------------------------
# _stream_response tests
# ---------------------------------------------------------------------------

class TestStreamResponse:
    """Tests for _stream_response: yields text chunks and logs cost."""

    def test_yields_text_chunks(self):
        """Should yield text chunks from the stream."""
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["Hello", " world", "!"])
        final_msg = MagicMock()
        final_msg.usage.input_tokens = 50
        final_msg.usage.output_tokens = 30
        mock_stream_ctx.get_final_message.return_value = final_msg
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()

        from services.claude_client import _stream_response, SONNET_MODEL
        gen = _stream_response(mock_client, {}, SONNET_MODEL, "general", mock_cost_tracker)
        chunks = list(gen)
        assert chunks == ["Hello", " world", "!"]

    def test_logs_cost_on_completion(self):
        """Should log cost via cost_tracker after stream completes."""
        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["chunk"])
        final_msg = MagicMock()
        final_msg.usage.input_tokens = 200
        final_msg.usage.output_tokens = 100
        mock_stream_ctx.get_final_message.return_value = final_msg
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()

        from services.claude_client import _stream_response, SONNET_MODEL
        gen = _stream_response(mock_client, {}, SONNET_MODEL, "extraction", mock_cost_tracker)
        list(gen)  # exhaust the generator
        mock_cost_tracker.log_api_call.assert_called_once_with(SONNET_MODEL, 200, 100, "extraction")

    def test_handles_mid_stream_error(self):
        """Should yield error text on mid-stream exception and still log cost."""
        def _failing_iterator():
            yield "partial"
            raise Exception("Network timeout")

        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = _failing_iterator()
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()

        from services.claude_client import _stream_response, SONNET_MODEL
        gen = _stream_response(mock_client, {}, SONNET_MODEL, "general", mock_cost_tracker)
        chunks = list(gen)
        # Should contain the partial text and then an error message
        assert "partial" in chunks
        assert any("unavailable" in c.lower() for c in chunks)
        # Cost should still be logged (in finally block) with 0 tokens
        mock_cost_tracker.log_api_call.assert_called_once_with(SONNET_MODEL, 0, 0, "general")
