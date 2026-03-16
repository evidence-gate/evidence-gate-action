"""Config file loader for Evidence Gate GitHub Action.

Loads, validates, and resolves `.evidencegate.yml` config files.
Provides the core logic for CONFIG-01..CONFIG-05.

Public API:
    ConfigError         -- exception for parse/validation failures
    ResolvedConfig      -- dataclass holding resolved configuration
    load_config()       -- parse YAML config file (returns {} if absent)
    validate_config()   -- check schema (returns error strings)
    resolve_config()    -- apply env > config > default precedence
    get_config_path()   -- resolve config file path from env
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class ConfigError(Exception):
    """Raised when config file cannot be parsed or fails schema validation."""


@dataclass
class ResolvedConfig:
    """Resolved configuration after applying env > config > default precedence."""

    gate_type: str
    phase_id: str
    mode: str
    evidence_files: str
    gate_preset: str
    config_path: str


VALID_TOP_LEVEL_KEYS = frozenset(
    {
        "version",
        "gate_type",
        "phase_id",
        "evidence_files",
        "mode",
        "gate_preset",
    }
)

# "warn" accepted in schema now; behavior added in Phase 21 (QUAL-04).
VALID_MODES = frozenset({"warn", "fail", "enforce", "observe"})


def load_config(config_path: str) -> dict[str, Any]:
    """Load .evidencegate.yml. Returns empty dict if file missing.

    Emits ``::error::`` annotation and raises :class:`ConfigError` on
    parse failures or non-mapping root types.
    """
    if not os.path.isfile(config_path):
        return {}

    if not _HAS_YAML:
        print(
            "::error::PyYAML is required to read the config file. "
            "Ensure 'pip install pyyaml' runs before this action step."
        )
        raise ConfigError("PyYAML not available")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return {}

        if not isinstance(data, dict):
            print(
                f"::error file={config_path},line=1::"
                f"Config file must be a YAML mapping, got {type(data).__name__}. "
                "Wrap your settings in a top-level mapping."
            )
            raise ConfigError("Config file must be a YAML mapping")

        return data

    except yaml.YAMLError as exc:
        line = 1
        problem = str(getattr(exc, "problem", exc))
        suggestion = (
            "Check for tabs (use spaces), unquoted colons, "
            "or incorrect indentation."
        )
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            line = exc.problem_mark.line + 1  # Convert 0-based to 1-based
        print(
            f"::error file={config_path},line={line}::"
            f"YAML syntax error: {problem}. {suggestion}"
        )
        raise ConfigError(f"YAML syntax error in {config_path}") from exc


def validate_config(config: dict[str, Any], config_path: str) -> list[str]:
    """Validate config dict schema.

    Returns list of validation error strings; emits ``::error::``
    annotations for each failure.
    """
    errors: list[str] = []

    for key in config:
        if key not in VALID_TOP_LEVEL_KEYS:
            msg = (
                f"Unknown key '{key}'. "
                f"Valid keys: {', '.join(sorted(VALID_TOP_LEVEL_KEYS))}"
            )
            print(f"::error file={config_path},line=1::{msg}")
            errors.append(msg)

    if "mode" in config:
        mode_val = config["mode"]
        if mode_val not in VALID_MODES:
            msg = (
                f"Invalid mode '{mode_val}'. "
                f"Valid values: {', '.join(sorted(VALID_MODES))}"
            )
            print(f"::error file={config_path},line=1::{msg}")
            errors.append(msg)

    if "version" in config:
        version_val = config["version"]
        if version_val not in (1, "1"):
            msg = (
                f"Unsupported config version '{version_val}'. "
                "Only version: 1 is supported."
            )
            print(f"::error file={config_path},line=1::{msg}")
            errors.append(msg)

    return errors


def get_config_path(env_config_path: str) -> str:
    """Resolve config file path.

    Priority: *env_config_path* > ``GITHUB_WORKSPACE/.evidencegate.yml``
    > ``.evidencegate.yml`` (fallback for unit tests).
    """
    if env_config_path:
        return env_config_path

    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if workspace:
        return os.path.join(workspace, ".evidencegate.yml")

    return ".evidencegate.yml"


def resolve_config(
    *,
    env_gate_type: str,
    env_phase_id: str,
    env_mode: str,
    env_evidence_files: str,
    env_gate_preset: str,
    env_config_path: str,
    file_config: dict[str, Any],
) -> ResolvedConfig:
    """Apply ``env > config > default`` precedence.

    Empty string is treated as "not provided" (the sentinel used by
    ``action.yml`` ``default: ""``).
    """
    return ResolvedConfig(
        gate_type=env_gate_type or file_config.get("gate_type", ""),
        phase_id=env_phase_id or file_config.get("phase_id", ""),
        mode=env_mode or file_config.get("mode", "enforce"),
        evidence_files=env_evidence_files or file_config.get("evidence_files", ""),
        gate_preset=env_gate_preset or file_config.get("gate_preset", ""),
        config_path=get_config_path(env_config_path),
    )
