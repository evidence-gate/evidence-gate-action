"""Tests for entrypoint.py.

Verifies:
- Pro mode: summary + outputs (ported)
- Error summary on exception (ported)
- Free mode routing to local_evaluator (new)
- Enterprise mode detection (new)
- Mode output value (new)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import entrypoint


class TestProMode:
    """Pro mode tests (ported from SaaS contract tests)."""

    def test_main_writes_summary_and_outputs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Pro mode writes summary and outputs correctly."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"
        evidence_file = tmp_path / "evidence.json"
        evidence_file.write_text('{"ok": true}')

        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("EG_RUN_ID", "12345")
        monkeypatch.setenv("EG_EVIDENCE_FILES", str(evidence_file))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setenv("GITHUB_RUN_ID", "12345")
        monkeypatch.setenv("EG_DASHBOARD_BASE_URL", "https://dashboard.example.com")
        monkeypatch.delenv("EG_API_BASE", raising=False)  # Pro mode = no custom base

        def _fake_evaluate(**kwargs):
            assert kwargs["github_run_url"] == "https://github.com/org/repo/actions/runs/12345"
            return {
                "passed": False,
                "issues": ["critical issue"],
                "metadata": {
                    "trace_url": "https://langfuse.example/trace/t-1",
                    "evidence_url": "https://dashboard.example.com?run_id=12345",
                },
            }

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        result = entrypoint.main()
        assert result["passed"] is False

        summary_text = summary.read_text()
        assert "Evidence Gate" in summary_text
        assert "12345" in summary_text

        output_text = output.read_text()
        assert "passed=false" in output_text
        assert "run_id=12345" in output_text
        assert "mode=pro" in output_text

    def test_main_writes_error_summary_on_exception(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Pro mode writes error summary when evaluation raises."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"

        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("EG_RUN_ID", "99999")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))

        def _raise_error(**kwargs):
            raise RuntimeError("network failed")

        monkeypatch.setattr(entrypoint, "evaluate", _raise_error)

        with pytest.raises(RuntimeError, match="network failed"):
            entrypoint.main()

        assert "FAIL" in summary.read_text()
        assert "network failed" in summary.read_text()
        assert "passed=false" in output.read_text()


class TestFreeMode:
    """Free mode tests (new)."""

    def test_main_free_mode_routes_to_local_evaluator(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """When no api_key, main() delegates to evaluate_local."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        evidence = tmp_path / "evidence.json"
        evidence.write_text('{"test": true}')
        monkeypatch.setenv("EG_EVIDENCE_FILES", str(evidence))

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()
        assert result["mode"] == "free"
        assert result["passed"] is True

        output_text = output.read_text()
        assert "mode=free" in output_text

    def test_free_mode_with_no_evidence_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Free mode works with no evidence files."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "2a")
        monkeypatch.setenv("EG_EVIDENCE_FILES", "")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()
        assert result["passed"] is True
        assert result["mode"] == "free"


class TestEnterpriseMode:
    """Enterprise mode detection (new)."""

    def test_main_detects_enterprise_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """api_key + custom api_base = enterprise mode."""
        monkeypatch.setenv("EG_API_KEY", "eg_enterprise_key")
        monkeypatch.setenv("EG_API_BASE", "https://eg.corp.example.com")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        result = entrypoint.main()
        output_text = output.read_text()
        assert "mode=enterprise" in output_text


class TestModeOutput:
    """Mode output value tests (new)."""

    def test_mode_output_is_set_free(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Mode output is 'free' when no api_key."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        result = entrypoint.main()
        assert "mode=free" in output.read_text()

    def test_mode_output_is_set_pro(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Mode output is 'pro' when api_key set without custom base."""
        monkeypatch.setenv("EG_API_KEY", "eg_pro_key")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        result = entrypoint.main()
        assert "mode=pro" in output.read_text()
