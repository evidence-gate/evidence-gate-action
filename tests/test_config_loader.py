"""Unit tests for config_loader.py -- Phase 20 Configuration DX.

Tests cover CONFIG-01..CONFIG-05 behaviors.
These tests are RED until config_loader.py is implemented (Plan 02).
"""

from __future__ import annotations

import sys

import pytest

# This import will fail (RED) until Plan 02 creates config_loader.py
import config_loader
from config_loader import ConfigError, load_config, resolve_config, validate_config


class TestLoadConfig:
    """CONFIG-01, CONFIG-02: load_config() parses .evidencegate.yml."""

    def test_missing_file_returns_empty_dict(self, tmp_path) -> None:
        """load_config() returns {} when file does not exist."""
        result = load_config(str(tmp_path / "nonexistent.yml"))
        assert result == {}

    def test_valid_yaml_returns_dict(self, tmp_path) -> None:
        """load_config() returns parsed dict for valid YAML."""
        config_file = tmp_path / ".evidencegate.yml"
        config_file.write_text("gate_type: test_coverage\n")
        result = load_config(str(config_file))
        assert result == {"gate_type": "test_coverage"}

    def test_empty_file_returns_empty_dict(self, tmp_path) -> None:
        """load_config() returns {} for an empty config file."""
        config_file = tmp_path / ".evidencegate.yml"
        config_file.write_text("")
        result = load_config(str(config_file))
        assert result == {}

    def test_non_mapping_emits_error_annotation(self, tmp_path, capsys) -> None:
        """load_config() prints ::error:: and raises ConfigError for non-mapping YAML."""
        config_file = tmp_path / ".evidencegate.yml"
        config_file.write_text("- list\n- items\n")
        with pytest.raises(ConfigError):
            load_config(str(config_file))
        captured = capsys.readouterr()
        assert "::error" in captured.out

    def test_syntax_error_emits_annotation_with_line(self, tmp_path, capsys) -> None:
        """load_config() emits ::error file=...,line=N:: on YAML syntax error."""
        config_file = tmp_path / ".evidencegate.yml"
        config_file.write_text("key: {bad:\nyaml")
        with pytest.raises(ConfigError):
            load_config(str(config_file))
        captured = capsys.readouterr()
        assert "::error file=" in captured.out
        assert ",line=" in captured.out

    def test_syntax_error_line_number_is_1_based(self, tmp_path, capsys) -> None:
        """Line number in annotation is 1-based (not 0-based)."""
        config_file = tmp_path / ".evidencegate.yml"
        # Error on line 1 (0-based=0, 1-based=1)
        config_file.write_text("key: {bad:\nyaml")
        with pytest.raises(ConfigError):
            load_config(str(config_file))
        captured = capsys.readouterr()
        # Extract line number from annotation
        import re

        match = re.search(r"line=(\d+)", captured.out)
        assert match is not None, f"No line= found in: {captured.out}"
        line_num = int(match.group(1))
        assert line_num >= 1, f"Line number must be 1-based, got {line_num}"


class TestValidateConfig:
    """CONFIG-02: validate_config() checks schema of parsed config dict."""

    def test_valid_keys_accepted(self, capsys) -> None:
        """All valid top-level keys pass validation with no errors."""
        config = {
            "version": 1,
            "gate_type": "test_coverage",
            "phase_id": "ci",
            "evidence_files": "report.json",
            "mode": "enforce",
            "gate_preset": "web-app-baseline",
        }
        errors = validate_config(config, ".evidencegate.yml")
        assert errors == []

    def test_unknown_key_emits_error(self, capsys) -> None:
        """Unknown config key produces an error and ::error:: annotation."""
        config = {"unknown_key": "x"}
        errors = validate_config(config, ".evidencegate.yml")
        assert len(errors) > 0
        captured = capsys.readouterr()
        assert "::error" in captured.out

    def test_invalid_mode_emits_error(self, capsys) -> None:
        """Invalid mode value produces an error and ::error:: annotation."""
        config = {"mode": "invalid_mode"}
        errors = validate_config(config, ".evidencegate.yml")
        assert len(errors) > 0
        captured = capsys.readouterr()
        assert "::error" in captured.out

    def test_valid_modes_accepted(self) -> None:
        """All valid mode values pass validation."""
        for mode_val in ("warn", "fail", "enforce", "observe"):
            config = {"mode": mode_val}
            errors = validate_config(config, ".evidencegate.yml")
            assert errors == [], f"mode={mode_val!r} should be valid, got errors: {errors}"

    def test_version_1_accepted(self) -> None:
        """version: 1 passes validation."""
        config = {"version": 1}
        errors = validate_config(config, ".evidencegate.yml")
        assert errors == []

    def test_invalid_version_emits_error(self) -> None:
        """version: 99 produces a validation error."""
        config = {"version": 99}
        errors = validate_config(config, ".evidencegate.yml")
        assert len(errors) > 0


class TestPrecedence:
    """CONFIG-03: Precedence resolution (explicit input > config file > default)."""

    def test_explicit_env_wins_over_config(self) -> None:
        """Explicit env input takes precedence over config file value."""
        resolved = resolve_config(
            env_gate_type="explicit",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={"gate_type": "from_config"},
        )
        assert resolved.gate_type == "explicit"

    def test_config_wins_over_empty_env(self) -> None:
        """Config file value wins when env is empty string."""
        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={"gate_type": "from_config"},
        )
        assert resolved.gate_type == "from_config"

    def test_default_used_when_both_empty(self) -> None:
        """Default is used when both env and config are empty."""
        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={},
        )
        assert resolved.gate_type == ""

    def test_mode_default_is_enforce(self) -> None:
        """When both env and config are empty, mode defaults to 'enforce'."""
        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={},
        )
        assert resolved.mode == "enforce"


class TestErrors:
    """CONFIG-04: Error handling and fail-closed behavior."""

    def test_config_error_causes_sys_exit_in_main(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Config file syntax error causes entrypoint.main() to sys.exit(1)."""
        import entrypoint

        config_file = tmp_path / ".evidencegate.yml"
        config_file.write_text("key: {bad:\nyaml")

        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        monkeypatch.setenv("EG_GATE_TYPE", "")
        monkeypatch.setenv("EG_PHASE_ID", "")
        monkeypatch.delenv("EG_API_KEY", raising=False)
        monkeypatch.delenv("EG_CONFIG_PATH", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            entrypoint.main()
        assert exc_info.value.code == 1


class TestConfigPath:
    """CONFIG-05: Custom config file path via EG_CONFIG_PATH."""

    def test_eg_config_path_env_overrides_default(self) -> None:
        """EG_CONFIG_PATH overrides the default config path."""
        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="/custom/path.yml",
            file_config={},
        )
        assert resolved.config_path == "/custom/path.yml"

    def test_github_workspace_prepended_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GITHUB_WORKSPACE is prepended to the default config path."""
        monkeypatch.setenv("GITHUB_WORKSPACE", "/repo")
        monkeypatch.delenv("EG_CONFIG_PATH", raising=False)

        # resolve_config with empty config_path should use GITHUB_WORKSPACE
        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={},
        )
        assert resolved.config_path == "/repo/.evidencegate.yml"

    def test_fallback_to_cwd_when_no_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config path falls back gracefully when GITHUB_WORKSPACE is unset."""
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        monkeypatch.delenv("EG_CONFIG_PATH", raising=False)

        resolved = resolve_config(
            env_gate_type="",
            env_phase_id="",
            env_mode="",
            env_evidence_files="",
            env_gate_preset="",
            env_config_path="",
            file_config={},
        )
        # Should not crash; path should end with .evidencegate.yml
        assert resolved.config_path.endswith(".evidencegate.yml")
