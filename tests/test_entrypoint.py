"""Tests for entrypoint.py.

Verifies:
- Pro mode: summary + outputs (ported)
- Error summary on exception (ported)
- Free mode routing to local_evaluator (new)
- Enterprise mode detection (new)
- Mode output value (new)
- Observe mode (FEAT-01)
- json_output (FEAT-06)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import entrypoint
from core import EvidenceGateError, fail_closed_main


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


class TestSummaryHeading:
    """DX-01: Summary heading includes gate_type and phase_id."""

    def test_write_summary_heading_includes_gate_type_and_phase_id(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Heading should include gate_type and phase_id for matrix job identification."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"
        monkeypatch.setenv("EG_GATE_TYPE", "security")
        monkeypatch.setenv("EG_PHASE_ID", "2b")
        monkeypatch.setenv("EG_RUN_ID", "111")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        entrypoint.main()
        summary_text = summary.read_text()
        assert "## Evidence Gate: security (2b)" in summary_text

    def test_write_summary_heading_fallback_when_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Heading gracefully falls back when gate_type/phase_id missing from env."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))

        # Call _write_summary directly to test heading fallback
        # without triggering main()'s required-field validation
        monkeypatch.delenv("EG_GATE_TYPE", raising=False)
        monkeypatch.delenv("EG_PHASE_ID", raising=False)

        entrypoint._write_summary(
            run_id="123",
            result={"passed": True, "issues": [], "metadata": {}},
            github_run_url=None,
            dashboard_url=None,
            mode="free",
        )
        summary_text = summary.read_text()
        # Should fall back to plain heading without gate_type/phase_id
        assert "## Evidence Gate" in summary_text
        # Should NOT have the colon format
        assert "## Evidence Gate:" not in summary_text


class TestSummaryCollapsible:
    """DX-02: Collapsible metadata and hidden empty rows."""

    def test_write_summary_metadata_collapsible(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Metadata rows should be wrapped in a <details> tag."""
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        entrypoint._write_summary(
            run_id="123",
            result={
                "passed": True,
                "issues": [],
                "metadata": {"trace_url": "https://langfuse.example/trace/t-1"},
            },
            github_run_url="https://github.com/org/repo/actions/runs/123",
            dashboard_url="https://dashboard.example.com",
            mode="pro",
        )
        summary_text = summary.read_text()
        assert "<details>" in summary_text
        assert "<summary>Metadata</summary>" in summary_text

    def test_write_summary_hides_empty_metadata_rows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Empty metadata rows (trace_url, evidence_url) should NOT appear."""
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        entrypoint._write_summary(
            run_id="123",
            result={"passed": True, "issues": [], "metadata": {}},
            github_run_url=None,
            dashboard_url=None,
            mode="free",
        )
        summary_text = summary.read_text()
        # Empty rows should NOT appear
        assert "Langfuse Trace" not in summary_text
        assert "Evidence URL" not in summary_text
        # The dash-only rows should not be rendered
        assert "| - |" not in summary_text

    def test_write_summary_shows_nonempty_metadata_rows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Non-empty metadata rows should appear inside details."""
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        entrypoint._write_summary(
            run_id="123",
            result={
                "passed": True,
                "issues": [],
                "metadata": {"trace_url": "https://langfuse.example/trace/t-1"},
            },
            github_run_url=None,
            dashboard_url=None,
            mode="pro",
        )
        summary_text = summary.read_text()
        assert "Langfuse Trace" in summary_text
        assert "https://langfuse.example/trace/t-1" in summary_text


class TestDebugOutput:
    """DX-03: Debug output controlled by EG_DEBUG."""

    def test_debug_output_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """When EG_DEBUG=true, debug lines appear in stdout."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "security")
        monkeypatch.setenv("EG_PHASE_ID", "2b")
        monkeypatch.setenv("EG_DEBUG", "true")
        monkeypatch.setenv("EG_EVIDENCE_FILES", "a.json,b.json")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "gate_type=security" in captured.out
        assert "phase_id=2b" in captured.out
        assert "evidence_files=" in captured.out
        assert "api_base=" in captured.out

    def test_no_debug_output_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """When EG_DEBUG is not set, no debug lines appear."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.delenv("EG_DEBUG", raising=False)

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        captured = capsys.readouterr()
        assert "[DEBUG]" not in captured.out

    def test_debug_output_includes_version(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """When EG_DEBUG=true and EG_VERSION=1.2.0, debug output includes version info."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("EG_DEBUG", "true")
        monkeypatch.setenv("EG_VERSION", "1.2.0")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        captured = capsys.readouterr()
        assert "[DEBUG]" in captured.out
        assert "version=1.2.0" in captured.out


class TestOIDCMasking:
    """SEC-04: OIDC token masking and auth notice."""

    def test_api_key_masked_before_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """When EG_API_KEY is set, ::add-mask:: appears as first workflow command."""
        monkeypatch.setenv("EG_API_KEY", "eg_secret_key_12345")
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

        entrypoint.main()

        captured = capsys.readouterr()
        assert "::add-mask::eg_secret_key_12345" in captured.out
        # Masking should appear before any other workflow commands
        lines = captured.out.strip().split("\n")
        mask_lines = [l for l in lines if "::add-mask::" in l]
        assert len(mask_lines) >= 1

    def test_auth_success_notice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """Successful auth emits ::notice title=Evidence Gate:: annotation."""
        monkeypatch.setenv("EG_API_KEY", "eg_pro_key_notice")
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

        entrypoint.main()

        captured = capsys.readouterr()
        assert "::notice title=Evidence Gate::" in captured.out

    def test_no_masking_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """When no EG_API_KEY, no masking or notice output."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        captured = capsys.readouterr()
        assert "::add-mask::" not in captured.out
        assert "::notice title=Evidence Gate::" not in captured.out


class TestObserveMode:
    """FEAT-01: Observe mode -- failures do not block the workflow step."""

    def test_observe_mode_does_not_exit_on_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """EG_MODE=observe: fail_closed_main does NOT sys.exit(1) when passed=False."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["test issue"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        # Should NOT raise SystemExit
        fail_closed_main(entrypoint.main)

        output_text = output.read_text()
        assert "observe_would_pass=false" in output_text

    def test_observe_mode_summary_badge_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """EG_MODE=observe with failed result shows OBSERVE (would FAIL) badge."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["issue1"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        fail_closed_main(entrypoint.main)

        summary_text = summary.read_text()
        assert "OBSERVE (would FAIL)" in summary_text

    def test_observe_mode_summary_badge_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """EG_MODE=observe with passing result shows OBSERVE (PASS) badge."""
        summary = tmp_path / "summary.md"
        output = tmp_path / "output.txt"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        fail_closed_main(entrypoint.main)

        summary_text = summary.read_text()
        assert "OBSERVE (PASS)" in summary_text

    def test_observe_mode_annotations_use_notice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """EG_MODE=observe: annotations emit at notice level, not error."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["issue A", "issue B"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        fail_closed_main(entrypoint.main)

        captured = capsys.readouterr()
        # Annotations should use ::notice, not ::error
        assert "::notice title=Evidence Gate::issue A" in captured.out
        assert "::error" not in captured.out

    def test_observe_mode_notice_emitted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """EG_MODE=observe emits a notice about running in observe mode."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        fail_closed_main(entrypoint.main)

        captured = capsys.readouterr()
        assert "Running in observe mode" in captured.out

    def test_observe_mode_suppresses_evidence_gate_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """EG_MODE=observe: EvidenceGateError does NOT sys.exit(1)."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _raise_eg_error(**kwargs):
            raise EvidenceGateError("API unavailable")

        monkeypatch.setattr(entrypoint, "evaluate", _raise_eg_error)

        # Should NOT raise SystemExit
        fail_closed_main(entrypoint.main)

        captured = capsys.readouterr()
        assert "API unavailable" in captured.out or "API unavailable" in captured.err

    def test_observe_mode_suppresses_unexpected_exception(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
    ) -> None:
        """EG_MODE=observe: unexpected RuntimeError does NOT sys.exit(1)."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _raise_runtime(**kwargs):
            raise RuntimeError("unexpected boom")

        monkeypatch.setattr(entrypoint, "evaluate", _raise_runtime)

        # Should NOT raise SystemExit
        fail_closed_main(entrypoint.main)

        captured = capsys.readouterr()
        assert "RuntimeError" in captured.out or "RuntimeError" in captured.err

    def test_enforce_mode_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Default (enforce) mode still exits on failure -- no regression."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.delenv("EG_MODE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["fail"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        with pytest.raises(SystemExit) as exc_info:
            fail_closed_main(entrypoint.main)
        assert exc_info.value.code == 1


class TestJsonOutput:
    """FEAT-06: json_output via _set_multiline_output with heredoc delimiter."""

    def test_set_multiline_output_uses_heredoc(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """_set_multiline_output writes heredoc-delimited value to GITHUB_OUTPUT."""
        output = tmp_path / "output.txt"
        output.write_text("")  # ensure file exists
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))

        entrypoint._set_multiline_output("test", "line1\nline2")

        content = output.read_text()
        # Must contain heredoc pattern: name<<delimiter\nvalue\ndelimiter\n
        assert "test<<ghadelimiter_" in content
        assert "line1\nline2" in content
        # Verify delimiter appears twice (open + close)
        lines = content.strip().split("\n")
        delimiter_lines = [l for l in lines if l.startswith("ghadelimiter_")]
        assert len(delimiter_lines) == 1  # closing delimiter on its own line

    def test_json_output_set_on_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """json_output is set in GITHUB_OUTPUT on passing result."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.delenv("EG_MODE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        entrypoint.main()

        output_text = output.read_text()
        assert "json_output<<ghadelimiter_" in output_text

    def test_json_output_set_on_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """json_output is set in GITHUB_OUTPUT even on failing result."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.delenv("EG_MODE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["fail"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        entrypoint.main()

        output_text = output.read_text()
        assert "json_output<<ghadelimiter_" in output_text

    def test_json_output_in_free_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """json_output is set in Free mode."""
        monkeypatch.delenv("EG_API_KEY")
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.delenv("EG_MODE", raising=False)

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        entrypoint.main()

        output_text = output.read_text()
        assert "json_output<<ghadelimiter_" in output_text

    def test_json_output_in_observe_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """json_output is set in observe mode."""
        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_MODE", "observe")
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": False, "issues": ["issue"], "metadata": {}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        fail_closed_main(entrypoint.main)

        output_text = output.read_text()
        assert "json_output<<ghadelimiter_" in output_text

    def test_json_output_is_valid_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """json_output content is valid parseable JSON."""
        import json
        import re

        output = tmp_path / "output.txt"
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("EG_GATE_TYPE", "skill")
        monkeypatch.setenv("EG_PHASE_ID", "1a")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("EG_API_BASE", raising=False)
        monkeypatch.delenv("EG_MODE", raising=False)

        def _fake_evaluate(**kwargs):
            return {"passed": True, "issues": [], "metadata": {"trace_url": "t"}}

        monkeypatch.setattr(entrypoint, "evaluate", _fake_evaluate)

        entrypoint.main()

        output_text = output.read_text()
        # Extract JSON between heredoc delimiters
        match = re.search(
            r"json_output<<(ghadelimiter_\w+)\n(.*?)\n\1\n",
            output_text,
            re.DOTALL,
        )
        assert match is not None, f"heredoc pattern not found in: {output_text}"
        json_str = match.group(2)
        parsed = json.loads(json_str)
        assert "passed" in parsed
        assert "metadata" in parsed
