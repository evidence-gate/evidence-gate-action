"""C1 regression: Free mode must fail closed (2026-10-17 QA)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from local_evaluator import KNOWN_GATE_TYPES, evaluate_local  # noqa: E402


def test_missing_evidence_fails() -> None:
    result = evaluate_local(gate_type="test_coverage", phase_id="testing", evidence_files=[])
    assert result["passed"] is False
    assert any("EVIDENCE_MISSING" in i for i in result["issues"])


def test_nonexistent_evidence_file_fails(tmp_path) -> None:
    result = evaluate_local(
        gate_type="test_coverage",
        phase_id="testing",
        evidence_files=[str(tmp_path / "nope.json")],
    )
    assert result["passed"] is False


@pytest.mark.parametrize("payload", [{}, [], None])
def test_empty_evidence_fails(tmp_path, payload) -> None:
    f = tmp_path / "coverage.json"
    f.write_text(json.dumps(payload))
    result = evaluate_local(gate_type="test_coverage", phase_id="testing", evidence_files=[str(f)])
    assert result["passed"] is False


def test_unknown_gate_type_fails(tmp_path) -> None:
    f = tmp_path / "e.json"
    f.write_text('{"a": 1}')
    result = evaluate_local(gate_type="made_up_gate", phase_id="x", evidence_files=[str(f)])
    assert result["passed"] is False
    assert any("UNKNOWN_GATE_TYPE" in i for i in result["issues"])


def test_valid_evidence_passes(tmp_path) -> None:
    f = tmp_path / "coverage.json"
    f.write_text('{"line_rate": 0.9}')
    result = evaluate_local(gate_type="test_coverage", phase_id="testing", evidence_files=[str(f)])
    assert result["passed"] is True


def test_known_gate_types_include_documented_ones() -> None:
    for g in ("test_coverage", "security", "build", "skill", "sbom", "provenance",
              "nemoclaw_blueprint", "nemoclaw_policy", "custom"):
        assert g in KNOWN_GATE_TYPES
