"""Gate preset bundles for Evidence Gate.

Provides curated gate type bundles so users don't need to know
which of the 22+ gate types to pick. Each preset is a named
list of gate types that are evaluated sequentially.

Uses only stdlib -- no third-party dependencies.
"""

from __future__ import annotations

PRESETS: dict[str, list[str]] = {
    "web-app-baseline": [
        "test_coverage",
        "security",
        "dependency",
        "build",
    ],
    "enterprise-compliance": [
        "compliance",
        "legal",
        "xac",
        "procedure_trace",
        "privacy",
        "security",
        "accessibility",
        "documentation",
        "build",
        "test_coverage",
    ],
    "api-service": [
        "documentation",
        "route_compliance",
        "performance",
        "security",
        "test_coverage",
        "dependency",
        "build",
    ],
    "supply-chain": [
        "security",
        "dependency",
        "compliance",
        "build",
    ],
    "nemoclaw-baseline": [
        "nemoclaw_blueprint",
        "nemoclaw_policy",
        "security",
        "build",
    ],
}


def expand_preset(name: str) -> list[str]:
    """Expand a preset name into a list of gate types.

    Args:
        name: Preset name (e.g., "web-app-baseline").

    Returns:
        Copy of the gate type list for the given preset.

    Raises:
        ValueError: If the preset name is not recognized.
    """
    if name not in PRESETS:
        valid = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(
            f"Unknown preset '{name}'. Valid presets: {valid}"
        )
    return list(PRESETS[name])
