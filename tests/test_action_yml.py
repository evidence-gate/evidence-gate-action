"""Contract tests for action.yml — Marketplace compliance and input/output schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ACTION_YML_PATH = Path(__file__).resolve().parent.parent / "action.yml"

# ---------------------------------------------------------------------------
# Helper: load YAML (pyyaml preferred, regex fallback)
# ---------------------------------------------------------------------------

try:
    import yaml  # type: ignore[import-untyped]

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def _load_action() -> dict:
    """Parse action.yml into a dict. Falls back to regex if pyyaml is missing."""
    content = ACTION_YML_PATH.read_text(encoding="utf-8")
    if _HAS_YAML:
        return yaml.safe_load(content)
    # Minimal fallback for CI environments without pyyaml
    raise RuntimeError("pyyaml not available — install pyyaml for full contract tests")


def _load_raw() -> str:
    """Return raw action.yml content."""
    return ACTION_YML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestActionYml:
    """action.yml Marketplace contract tests."""

    def test_action_yml_is_valid_yaml(self) -> None:
        """action.yml must be parseable as valid YAML."""
        data = _load_action()
        assert isinstance(data, dict), "action.yml did not parse as a YAML mapping"

    def test_action_yml_has_required_marketplace_fields(self) -> None:
        """Marketplace requires name, description, branding, and runs."""
        data = _load_action()
        for field in ("name", "description", "branding", "runs"):
            assert field in data, f"Missing required Marketplace field: {field}"
        # author is strongly recommended
        assert "author" in data, "Missing recommended field: author"

    def test_action_yml_branding_values(self) -> None:
        """Branding must use icon: shield, color: blue."""
        data = _load_action()
        branding = data["branding"]
        assert branding["icon"] == "shield", f"Expected icon 'shield', got '{branding['icon']}'"
        assert branding["color"] == "blue", f"Expected color 'blue', got '{branding['color']}'"

    def test_action_yml_api_key_is_optional(self) -> None:
        """api_key input must be required: false with default: '' for Free mode."""
        data = _load_action()
        api_key = data["inputs"]["api_key"]
        assert api_key["required"] is False, (
            f"api_key.required must be false, got {api_key['required']}"
        )
        assert api_key["default"] == "", (
            f"api_key.default must be empty string, got {api_key['default']!r}"
        )

    def test_action_yml_outputs_include_mode(self) -> None:
        """mode output must exist for Free/Pro/Enterprise detection."""
        data = _load_action()
        assert "mode" in data["outputs"], (
            f"'mode' not in outputs: {list(data['outputs'].keys())}"
        )
        mode_desc = data["outputs"]["mode"]["description"]
        assert mode_desc, "mode output must have a non-empty description"

    def test_version_input_exists(self) -> None:
        """action.yml must have a 'version' input with default 'latest'."""
        data = _load_action()
        assert "version" in data["inputs"], (
            f"'version' not in inputs: {list(data['inputs'].keys())}"
        )
        version_input = data["inputs"]["version"]
        assert version_input["default"] == "latest", (
            f"version.default must be 'latest', got {version_input['default']!r}"
        )
        assert version_input["required"] is False, (
            f"version.required must be false, got {version_input['required']}"
        )

    def test_cache_step_exists(self) -> None:
        """action.yml must have a step using actions/cache for pip caching."""
        raw = _load_raw()
        assert "actions/cache@" in raw, (
            "action.yml must contain an actions/cache step for pip caching"
        )

    def test_pip_install_step_exists(self) -> None:
        """action.yml must have a conditional pip install step."""
        raw = _load_raw()
        assert "pip install" in raw, (
            "action.yml must contain a 'pip install' step for version pinning"
        )
