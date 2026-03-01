"""Tests for escape_xml() utility — SPEC Section 3.2 safety requirement."""
from services.claude_client import escape_xml


class TestEscapeXml:
    def test_ampersand(self):
        assert escape_xml("foo & bar") == "foo &amp; bar"

    def test_less_than(self):
        assert escape_xml("a < b") == "a &lt; b"

    def test_greater_than(self):
        assert escape_xml("a > b") == "a &gt; b"

    def test_double_quote(self):
        assert escape_xml('say "hello"') == "say &quot;hello&quot;"

    def test_single_quote(self):
        assert escape_xml("it's") == "it&apos;s"

    def test_empty_string(self):
        assert escape_xml("") == ""

    def test_no_special_chars(self):
        assert escape_xml("plain text 123") == "plain text 123"

    def test_combined(self):
        assert escape_xml('<a href="x">&</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"

    def test_idempotence(self):
        """Double-escaping should not break (each pass escapes further)."""
        once = escape_xml("a & b")
        twice = escape_xml(once)
        assert twice == "a &amp;amp; b"
