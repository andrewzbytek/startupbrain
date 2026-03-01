"""Tests for _stream_response() generator in claude_client."""
import pytest
from unittest.mock import MagicMock, patch


class TestStreamResponse:
    def test_yields_text_chunks(self):
        """_stream_response should yield text chunks from the stream."""
        from services.claude_client import _stream_response

        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["Hello", " world", "!"])
        mock_final = MagicMock()
        mock_final.usage.input_tokens = 100
        mock_final.usage.output_tokens = 50
        mock_stream_ctx.get_final_message.return_value = mock_final
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()
        kwargs = {"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "messages": []}

        gen = _stream_response(mock_client, kwargs, "claude-sonnet-4-20250514", "test", mock_cost_tracker)
        chunks = list(gen)

        assert chunks == ["Hello", " world", "!"]

    def test_error_yields_error_string(self):
        """On API error, should yield an error string."""
        from services.claude_client import _stream_response

        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(side_effect=Exception("API down"))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()
        kwargs = {"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "messages": []}

        gen = _stream_response(mock_client, kwargs, "claude-sonnet-4-20250514", "test", mock_cost_tracker)
        chunks = list(gen)

        assert len(chunks) == 1
        assert "Error" in chunks[0]

    def test_cost_logged_on_completion(self):
        """Cost tracker should be called after stream completes."""
        from services.claude_client import _stream_response

        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["chunk"])
        mock_final = MagicMock()
        mock_final.usage.input_tokens = 200
        mock_final.usage.output_tokens = 100
        mock_stream_ctx.get_final_message.return_value = mock_final
        mock_client.messages.stream.return_value = mock_stream_ctx

        mock_cost_tracker = MagicMock()
        kwargs = {"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "messages": []}

        gen = _stream_response(mock_client, kwargs, "claude-sonnet-4-20250514", "test_task", mock_cost_tracker)
        list(gen)  # exhaust the generator

        mock_cost_tracker.log_api_call.assert_called_once_with(
            "claude-sonnet-4-20250514", 200, 100, "test_task"
        )
