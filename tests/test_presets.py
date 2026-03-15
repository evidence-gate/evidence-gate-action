"""Tests for presets.py -- Gate preset expansion.

Verifies:
- 4 named presets expand to correct gate type lists
- Unknown preset names raise ValueError with valid preset list
- PRESETS dict has exactly 4 entries
- expand_preset returns copies (not original references)
"""

from __future__ import annotations

import pytest

from presets import PRESETS, expand_preset


class TestExpandPreset:
    """Tests for expand_preset function."""

    def test_expand_preset_web_app_baseline(self) -> None:
        """web-app-baseline returns 4 gates: test_coverage, security, dependency, build."""
        result = expand_preset("web-app-baseline")
        assert result == ["test_coverage", "security", "dependency", "build"]

    def test_expand_preset_enterprise_compliance(self) -> None:
        """enterprise-compliance returns 10 gates including compliance, legal, xac, etc."""
        result = expand_preset("enterprise-compliance")
        assert len(result) == 10
        assert "compliance" in result
        assert "legal" in result
        assert "xac" in result
        assert "procedure_trace" in result
        assert "privacy" in result

    def test_expand_preset_api_service(self) -> None:
        """api-service returns 7 gates including documentation, route_compliance, performance."""
        result = expand_preset("api-service")
        assert len(result) == 7
        assert "documentation" in result
        assert "route_compliance" in result
        assert "performance" in result

    def test_expand_preset_supply_chain(self) -> None:
        """supply-chain returns 4 gates: security, dependency, compliance, build."""
        result = expand_preset("supply-chain")
        assert result == ["security", "dependency", "compliance", "build"]

    def test_expand_preset_unknown_raises_value_error(self) -> None:
        """Unknown preset name raises ValueError with descriptive message listing valid presets."""
        with pytest.raises(ValueError, match="Unknown preset") as exc_info:
            expand_preset("nonexistent-preset")
        error_msg = str(exc_info.value)
        assert "web-app-baseline" in error_msg
        assert "enterprise-compliance" in error_msg
        assert "api-service" in error_msg
        assert "supply-chain" in error_msg

    def test_presets_dict_has_four_entries(self) -> None:
        """PRESETS dict has exactly 4 entries."""
        assert len(PRESETS) == 4

    def test_expand_preset_returns_copy(self) -> None:
        """expand_preset returns a copy, not the original list reference."""
        result = expand_preset("web-app-baseline")
        assert result is not PRESETS["web-app-baseline"]
        # Mutating the returned copy should not affect the original
        result.append("extra")
        assert "extra" not in PRESETS["web-app-baseline"]
