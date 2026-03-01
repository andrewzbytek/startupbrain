"""
Feedback pattern detection tests for Startup Brain.

Tests feedback ingestion, pattern detection, and recurring theme alerting.
All tests mock external APIs and run without API keys.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: build mock feedback pattern detection XML response
# ---------------------------------------------------------------------------

def _make_feedback_pattern_xml(
    source: str,
    summary: str,
    themes: list,
    alerts: list = None,
    updated_themes: list = None,
) -> str:
    """Build a mock feedback pattern detection output XML."""
    themes_xml = "\n".join(f"      <theme>{t}</theme>" for t in themes)
    alerts_xml = ""
    if alerts:
        for a in alerts:
            sources_list = ", ".join(a.get("sources", []))
            alerts_xml += f"""  <alert>
    <theme>{a['theme']}</theme>
    <source_count>{a['source_count']}</source_count>
    <sources>{sources_list}</sources>
    <severity>{a.get('severity', 'signal')}</severity>
    <description>{a.get('description', '')}</description>
    <current_strategy_alignment>{a.get('alignment', 'misaligned')}</current_strategy_alignment>
  </alert>\n"""

    updated_themes_xml = ""
    if updated_themes:
        theme_items = []
        for t in updated_themes:
            sources_list = ", ".join(t.get("sources", []))
            theme_items.append(f"""  <theme>
    <name>{t['name']}</name>
    <count>{t['count']}</count>
    <sources>{sources_list}</sources>
    <status>{t.get('status', 'active')}</status>
    <notes>{t.get('notes', '')}</notes>
  </theme>""")
        updated_themes_xml = "\n".join(theme_items)

    return f"""<feedback_output>
  <new_feedback_entry>
    <date>2026-02-18</date>
    <source>{source}</source>
    <summary>{summary}</summary>
    <themes>
{themes_xml}
    </themes>
  </new_feedback_entry>
  <pattern_alerts>
{alerts_xml}  </pattern_alerts>
  <updated_recurring_themes>
{updated_themes_xml}
  </updated_recurring_themes>
  <document_updates_needed>
    <update>Add feedback entry to Feedback Tracker section</update>
  </document_updates_needed>
</feedback_output>"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIngestFeedback:
    """test_ingest_feedback: Verify feedback stored correctly in MongoDB mock."""

    def test_feedback_stored_with_correct_fields(self, sample_living_document):
        stored_docs = []

        def mock_insert_feedback(doc):
            stored_docs.append(doc)
            return "mock_feedback_id_1"

        feedback_pattern_xml = _make_feedback_pattern_xml(
            source="Sarah Chen (Beacon Capital)",
            summary="Positive on technical approach. Concerns about branding.",
            themes=["branding", "logo"],
        )

        mock_pattern_response = {
            "text": feedback_pattern_xml,
            "tokens_in": 500,
            "tokens_out": 400,
            "model": "claude-sonnet-4-20250514",
        }

        mock_doc_update = {"success": True, "message": "Updated.", "changes_applied": 1}

        with patch("services.mongo_client.insert_feedback", side_effect=mock_insert_feedback), \
             patch("services.claude_client.call_sonnet", return_value=mock_pattern_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.document_updater.update_document", return_value=mock_doc_update), \
             patch("services.feedback._get_feedback_tracker_section", return_value=""), \
             patch("services.feedback._get_current_strategy_summary", return_value=""):
            from services.feedback import ingest_feedback
            result = ingest_feedback(
                text="Positive on technical approach. Concerned about branding — name and logo feel like government contractor.",
                source_name="Sarah Chen",
                source_type="investor",
                date="2026-02-10",
                meeting_context="Beacon Capital meeting",
            )

        assert result["feedback_id"] == "mock_feedback_id_1", "Should return the feedback ID"
        assert len(stored_docs) == 1, "Should store exactly one feedback document"

        stored = stored_docs[0]
        assert stored["source_name"] == "Sarah Chen", "Source name should be stored"
        assert stored["source_type"] == "investor", "Source type should be stored"
        assert stored["date"] == "2026-02-10", "Date should be stored"
        assert "feedback_text" in stored, "Feedback text should be stored"

    def test_feedback_id_returned(self, sample_living_document):
        with patch("services.mongo_client.insert_feedback", return_value="mock_id_42"), \
             patch("services.claude_client.call_sonnet", return_value={"text": _make_feedback_pattern_xml("Test", "Summary", ["theme1"]), "tokens_in": 300, "tokens_out": 200, "model": "claude-sonnet-4-20250514"}), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.document_updater.update_document", return_value={"success": True, "message": "OK", "changes_applied": 1}), \
             patch("services.feedback._get_feedback_tracker_section", return_value=""), \
             patch("services.feedback._get_current_strategy_summary", return_value=""):
            from services.feedback import ingest_feedback
            result = ingest_feedback("Feedback text", "Test Source", "advisor")

        assert result["feedback_id"] == "mock_id_42", "Should return the MongoDB-assigned ID"


class TestDetectRecurringTheme:
    """test_detect_recurring_theme: Verify theme detected after 3 similar feedbacks."""

    def test_three_feedbacks_with_same_theme_detected(self):
        # Simulate feedback storage with 3 entries sharing the "branding" theme
        feedback_entries = [
            {"source_name": "Sarah Chen", "themes": ["branding", "logo"], "source_type": "investor"},
            {"source_name": "Marcus Webb", "themes": ["branding", "name"], "source_type": "investor"},
            {"source_name": "Priya Sharma", "themes": ["branding", "logo", "visual-identity"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import get_recurring_themes
            themes = get_recurring_themes()

        theme_names = [t["theme"] for t in themes]
        assert "branding" in theme_names, "Branding theme should be detected after 3 feedbacks"

        branding_theme = next(t for t in themes if t["theme"] == "branding")
        assert branding_theme["count"] == 3, "Branding count should be 3"
        assert len(branding_theme["sources"]) == 3, "Should list all 3 sources"

    def test_theme_counts_across_multiple_entries(self):
        feedback_entries = [
            {"source_name": "Investor A", "themes": ["unit-economics", "pricing"], "source_type": "investor"},
            {"source_name": "Investor B", "themes": ["unit-economics", "branding"], "source_type": "investor"},
            {"source_name": "Customer A", "themes": ["unit-economics"], "source_type": "customer"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import get_recurring_themes
            themes = get_recurring_themes()

        unit_economics = next((t for t in themes if t["theme"] == "unit-economics"), None)
        assert unit_economics is not None, "unit-economics should be detected"
        assert unit_economics["count"] == 3, "Should count across all 3 feedback entries"


class TestThemeAlertThreshold:
    """test_theme_alert_threshold: Verify should_alert() returns True at 3+ sources."""

    def test_should_alert_true_at_three_sources(self):
        feedback_entries = [
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
            {"source_name": "Marcus Webb", "themes": ["branding"], "source_type": "investor"},
            {"source_name": "Priya Sharma", "themes": ["branding"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import should_alert
            result = should_alert("branding")

        assert result is True, "should_alert should return True at 3 distinct sources"

    def test_should_alert_false_at_two_sources(self):
        feedback_entries = [
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
            {"source_name": "Marcus Webb", "themes": ["branding"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import should_alert
            result = should_alert("branding")

        assert result is False, "should_alert should return False at only 2 sources"

    def test_should_alert_false_same_source_repeated(self):
        """Multiple feedback from same source counts as ONE source."""
        feedback_entries = [
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import should_alert
            result = should_alert("branding")

        assert result is False, "Same source repeated 3 times should NOT trigger alert (only 1 distinct source)"

    def test_should_alert_false_for_unknown_theme(self):
        feedback_entries = [
            {"source_name": "Sarah Chen", "themes": ["branding"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import should_alert
            result = should_alert("nonexistent-theme")

        assert result is False, "Unknown theme should not trigger alert"

    def test_should_alert_true_exactly_at_threshold(self):
        """Exactly 3 sources should trigger alert (not just >3)."""
        feedback_entries = [
            {"source_name": "Investor X", "themes": ["logo"], "source_type": "investor"},
            {"source_name": "Investor Y", "themes": ["logo"], "source_type": "investor"},
            {"source_name": "Investor Z", "themes": ["logo"], "source_type": "investor"},
        ]

        with patch("services.mongo_client.get_feedback", return_value=feedback_entries):
            from services.feedback import should_alert
            result = should_alert("logo")

        assert result is True, "Exactly 3 distinct sources should trigger alert"


class TestEvolutionNarrative:
    """test_evolution_narrative: Verify narrative generation from changelog entries."""

    def test_evolution_narrative_generated(self, sample_living_document):
        evolution_xml = """<evolution_output>
  <narrative>The pricing model for NuclearCompliance.ai has undergone significant exploration. Starting from an annual per-facility licence at £50K, the team has been evaluating a hybrid model in response to specific customer feedback about procurement budget lines.</narrative>
  <key_inflection_points>
    <inflection>
      <date>2026-02-05</date>
      <what_changed>Initial pricing set: £50K per facility per year, annual in advance</what_changed>
      <why>Revenue predictability and VC preference for fixed MRR</why>
    </inflection>
    <inflection>
      <date>2026-02-15</date>
      <what_changed>Hybrid pricing model under evaluation: £15K-£20K base + £0.10/document</what_changed>
      <why>Customer feedback: OpEx approval faster for variable cost billing</why>
    </inflection>
  </key_inflection_points>
  <current_position_summary>£50K per facility per year (active), with hybrid model under evaluation pending further customer validation.</current_position_summary>
</evolution_output>"""

        mock_response = {
            "text": evolution_xml,
            "tokens_in": 600,
            "tokens_out": 500,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.document_updater.read_living_document", return_value=sample_living_document):
            from services.feedback import generate_evolution_narrative
            result = generate_evolution_narrative("Pricing")

        assert result["narrative"] != "", "Evolution narrative should not be empty"
        assert len(result["key_inflection_points"]) > 0, "Should have at least one inflection point"
        assert result["current_position_summary"] != "", "Should have a current position summary"

        # Verify the inflection points have the required structure
        for point in result["key_inflection_points"]:
            assert "date" in point, "Inflection point should have a date"
            assert "what_changed" in point, "Inflection point should have what_changed"
            assert "why" in point, "Inflection point should have why"

    def test_evolution_narrative_includes_pricing_context(self, sample_living_document):
        evolution_xml = """<evolution_output>
  <narrative>The pricing model started at £50K per facility per year and is now under review.</narrative>
  <key_inflection_points>
    <inflection>
      <date>2026-02-05</date>
      <what_changed>£50K annual per-facility licence set</what_changed>
      <why>VC preference and revenue predictability</why>
    </inflection>
  </key_inflection_points>
  <current_position_summary>£50K/year active position</current_position_summary>
</evolution_output>"""

        mock_response = {
            "text": evolution_xml,
            "tokens_in": 400,
            "tokens_out": 300,
            "model": "claude-sonnet-4-20250514",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.document_updater.read_living_document", return_value=sample_living_document):
            from services.feedback import generate_evolution_narrative
            result = generate_evolution_narrative("Pricing")

        assert "£50K" in result["key_inflection_points"][0]["what_changed"] or \
               "50K" in result["key_inflection_points"][0]["what_changed"], \
               "Pricing narrative should reference the specific price point"

    def test_detect_patterns_returns_correct_structure(self):
        feedback_pattern_xml = _make_feedback_pattern_xml(
            source="Priya Sharma (Nucleus Fund)",
            summary="Concerned about branding and logo quality. Offered warm intros to nuclear operators.",
            themes=["branding", "logo", "warm-intros"],
            alerts=[{
                "theme": "branding",
                "source_count": 3,
                "sources": ["Sarah Chen", "Marcus Webb", "Priya Sharma"],
                "severity": "signal",
                "description": "Three investors independently raised branding concerns",
                "alignment": "misaligned with modern software positioning",
            }],
            updated_themes=[{
                "name": "branding",
                "count": 3,
                "sources": ["Sarah Chen", "Marcus Webb", "Priya Sharma"],
                "status": "active",
                "notes": "Consistent feedback on logo quality and name",
            }],
        )

        mock_response = {
            "text": feedback_pattern_xml,
            "tokens_in": 600,
            "tokens_out": 500,
            "model": "claude-sonnet-4-20250514",
        }

        feedback_tracker = "### Recurring Themes\n- branding: 2 sources\n"
        new_feedback = {
            "date": "2026-02-18",
            "source_name": "Priya Sharma",
            "source_type": "investor",
            "feedback_text": "Logo looks outdated. Brand needs work.",
            "meeting_context": "Nucleus Fund meeting",
        }

        with patch("services.claude_client.call_sonnet", return_value=mock_response), \
             patch("services.claude_client.load_prompt", return_value="mock prompt"), \
             patch("services.feedback._get_current_strategy_summary", return_value="Small nuclear plants focus."):
            from services.feedback import detect_patterns
            result = detect_patterns(feedback_tracker, new_feedback)

        # Check structure
        assert "new_feedback_entry" in result, "Result should have new_feedback_entry"
        assert "pattern_alerts" in result, "Result should have pattern_alerts"
        assert "updated_recurring_themes" in result, "Result should have updated_recurring_themes"
        assert "document_updates_needed" in result, "Result should have document_updates_needed"

        # Check alert detected
        assert len(result["pattern_alerts"]) > 0, "Should detect branding alert at 3 sources"
        branding_alert = result["pattern_alerts"][0]
        assert branding_alert["theme"] == "branding", "Alert should be for branding theme"
        assert branding_alert["source_count"] == 3, "Alert should show 3 sources"
