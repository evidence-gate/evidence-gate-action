"""Tests for upsell UX in entrypoint.py.

Verifies:
- Pro-only gate type triggers upsell message
- Free gate type does NOT trigger upsell
- Upsell annotation is warning level (not error)
- Upsell message contains pricing URL
- Exit code is 0 when upsell triggered
"""

from __future__ import annotations

import pytest

import entrypoint
from local_evaluator import PRICING_URL


class TestUpsellEntrypoint:
    """Test upsell behavior through entrypoint main()."""

    def test_pro_gate_triggers_upsell_summary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """Pro-only gate in free mode writes upsell to STEP_SUMMARY."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "blind_gate")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()

        assert result["upsell"] is True
        assert result["passed"] is True
        assert "Upgrade" in summary.read_text()
        assert "upsell=true" in output.read_text()

    def test_free_gate_no_upsell(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Free gate type does not produce upsell."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()
        assert "upsell" not in result
        assert "upsell" not in output.read_text()

    def test_upsell_annotation_is_warning_level(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """Upsell annotation uses ::warning (not ::error)."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "composite")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        captured = capsys.readouterr()
        assert "::warning" in captured.out
        assert "::error" not in captured.out

    def test_upsell_message_contains_pricing_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Upsell message includes the pricing URL."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "wave")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()
        assert PRICING_URL in result.get("upsell_message", "")
        assert PRICING_URL in summary.read_text()

    def test_upsell_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Upsell triggered gate does NOT fail (passed=true, no SystemExit)."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "quality_state")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        # Should not raise SystemExit
        result = entrypoint.main()
        assert result["passed"] is True
        assert "passed=true" in output.read_text()
