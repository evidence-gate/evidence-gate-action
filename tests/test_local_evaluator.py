"""Tests for local_evaluator.py (Free mode).

Covers:
- File existence checks
- JSON validity
- Threshold checks
- Structure validation (required fields, types, nested, patterns)
- SHA-256 computation
- Pro feature upsell trigger
- evaluate_local() end-to-end
"""

from __future__ import annotations

import hashlib
import json

import pytest

from local_evaluator import (
    PRO_ONLY_GATE_TYPES,
    check_file_exists,
    check_json_valid,
    check_threshold,
    compute_sha256,
    evaluate_local,
    validate_evidence_structure,
)

# ---------------------------------------------------------------------------
# File existence checks
# ---------------------------------------------------------------------------


class TestFileExists:
    """Test check_file_exists."""

    def test_existing_file(self, evidence_file: str) -> None:
        result = check_file_exists(evidence_file)
        assert result["passed"] is True
        assert "exists" in result["message"].lower()

    def test_missing_file(self) -> None:
        result = check_file_exists("/nonexistent/path.json")
        assert result["passed"] is False
        assert "not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# JSON validity
# ---------------------------------------------------------------------------


class TestJsonValid:
    """Test check_json_valid."""

    def test_valid_json(self, evidence_dir) -> None:
        result = check_json_valid(str(evidence_dir / "valid.json"))
        assert result["passed"] is True
        assert result["data"] is not None
        assert result["data"]["name"] == "test"

    def test_invalid_json(self, evidence_dir) -> None:
        result = check_json_valid(str(evidence_dir / "invalid.json"))
        assert result["passed"] is False
        assert "Invalid JSON" in result["message"]

    def test_empty_json(self, evidence_dir) -> None:
        result = check_json_valid(str(evidence_dir / "empty.json"))
        assert result["passed"] is False

    def test_missing_file_json(self) -> None:
        result = check_json_valid("/nonexistent/file.json")
        assert result["passed"] is False
        assert result["data"] is None


# ---------------------------------------------------------------------------
# Threshold checks
# ---------------------------------------------------------------------------


class TestThreshold:
    """Test check_threshold."""

    def test_value_within_range(self) -> None:
        result = check_threshold(50, min_val=0, max_val=100)
        assert result["passed"] is True

    def test_value_below_minimum(self) -> None:
        result = check_threshold(-5, min_val=0, max_val=100)
        assert result["passed"] is False
        assert "below minimum" in result["message"]

    def test_value_above_maximum(self) -> None:
        result = check_threshold(150, min_val=0, max_val=100)
        assert result["passed"] is False
        assert "above maximum" in result["message"]

    def test_value_at_exact_minimum(self) -> None:
        result = check_threshold(0, min_val=0, max_val=100)
        assert result["passed"] is True

    def test_value_at_exact_maximum(self) -> None:
        result = check_threshold(100, min_val=0, max_val=100)
        assert result["passed"] is True

    def test_min_only(self) -> None:
        result = check_threshold(50, min_val=0)
        assert result["passed"] is True

    def test_max_only(self) -> None:
        result = check_threshold(50, max_val=100)
        assert result["passed"] is True


# ---------------------------------------------------------------------------
# Structure validation
# ---------------------------------------------------------------------------


class TestStructureValidation:
    """Test validate_evidence_structure."""

    def test_required_fields_present(self) -> None:
        data = {"name": "test", "version": "1.0"}
        schema = {"type": "object", "required": ["name", "version"]}
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is True

    def test_required_fields_missing(self) -> None:
        data = {"name": "test"}
        schema = {"type": "object", "required": ["name", "version"]}
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False
        assert any("version" in issue for issue in result["issues"])

    def test_type_check_string(self) -> None:
        data = {"name": 123}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False

    def test_type_check_number(self) -> None:
        data = {"score": "not_a_number"}
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False

    def test_type_check_boolean_not_number(self) -> None:
        """Boolean should not pass as number type."""
        data = {"count": True}
        schema = {
            "type": "object",
            "properties": {"count": {"type": "number"}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False

    def test_nested_object_validation(self) -> None:
        data = {
            "metadata": {"version": "1.0", "score": 85},
        }
        schema = {
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "required": ["version"],
                    "properties": {
                        "version": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 100},
                    },
                },
            },
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is True

    def test_pattern_matching(self) -> None:
        data = {"id": "ABC-123"}
        schema = {
            "type": "object",
            "properties": {"id": {"type": "string", "pattern": r"^[A-Z]+-\d+$"}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is True

    def test_pattern_matching_failure(self) -> None:
        data = {"id": "abc_123"}
        schema = {
            "type": "object",
            "properties": {"id": {"type": "string", "pattern": r"^[A-Z]+-\d+$"}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False

    def test_number_minimum_violation(self) -> None:
        data = {"score": -5}
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number", "minimum": 0}},
        }
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False

    def test_array_items_validation(self) -> None:
        data = ["alpha", "beta", "gamma"]
        schema = {"type": "array", "items": {"type": "string"}}
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is True

    def test_array_items_type_violation(self) -> None:
        data = ["alpha", 123, "gamma"]
        schema = {"type": "array", "items": {"type": "string"}}
        result = validate_evidence_structure(data, schema)
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# SHA-256 computation
# ---------------------------------------------------------------------------


class TestSha256:
    """Test compute_sha256."""

    def test_sha256_matches_manual(self, evidence_file: str) -> None:
        result = compute_sha256(evidence_file)
        with open(evidence_file, "rb") as f:
            expected = hashlib.sha256(f.read()).hexdigest()
        assert result == expected
        assert len(result) == 64

    def test_sha256_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            compute_sha256("/nonexistent/file.json")


# ---------------------------------------------------------------------------
# Pro feature upsell
# ---------------------------------------------------------------------------


class TestProUpsell:
    """Test Pro-only gate type upsell."""

    @pytest.mark.parametrize("gate_type", sorted(PRO_ONLY_GATE_TYPES))
    def test_pro_gate_type_triggers_upsell(self, gate_type: str) -> None:
        result = evaluate_local(gate_type=gate_type, phase_id="1a")
        assert result["upsell"] is True
        assert result["passed"] is True
        assert result["mode"] == "free"
        assert "Pro plan" in result["upsell_message"]

    def test_free_gate_type_no_upsell(self) -> None:
        result = evaluate_local(gate_type="skill", phase_id="1a")
        assert "upsell" not in result


# ---------------------------------------------------------------------------
# End-to-end evaluate_local
# ---------------------------------------------------------------------------


class TestEvaluateLocal:
    """End-to-end tests for evaluate_local."""

    def test_simple_pass(self, evidence_dir) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            evidence_files=[str(evidence_dir / "valid.json")],
        )
        assert result["passed"] is True
        assert result["mode"] == "free"
        assert result["issues"] == []

    def test_missing_evidence_file_fails(self) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            evidence_files=["/nonexistent/evidence.json"],
        )
        assert result["passed"] is False
        assert len(result["issues"]) > 0

    def test_with_schema_validation(self, evidence_dir) -> None:
        result = evaluate_local(
            gate_type="tool_invocation",
            phase_id="2b",
            evidence_files=[str(evidence_dir / "valid.json")],
            checks={
                "schema": {
                    "type": "object",
                    "required": ["name", "score"],
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 100},
                    },
                },
            },
        )
        assert result["passed"] is True

    def test_with_threshold_check(self) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            checks={"threshold": {"value": 85, "min": 70, "max": 100}},
        )
        assert result["passed"] is True

    def test_with_failing_threshold(self) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            checks={"threshold": {"value": 50, "min": 70, "max": 100}},
        )
        assert result["passed"] is False

    def test_with_required_files(self, evidence_dir) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            checks={"required_files": [str(evidence_dir / "valid.json")]},
        )
        assert result["passed"] is True

    def test_with_missing_required_files(self) -> None:
        result = evaluate_local(
            gate_type="skill",
            phase_id="1a",
            checks={"required_files": ["/nonexistent/required.json"]},
        )
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# SBOM gate (FEAT-01) -- RED until Wave 2 implements evaluate_sbom
# ---------------------------------------------------------------------------


class TestSBOMGate:
    """Test SBOM validation via evaluate_local(gate_type='sbom').

    All tests are RED until Wave 2 implements SBOM handling in local_evaluator.
    """

    def test_valid_cyclonedx_json_passes(self, tmp_path) -> None:
        """Minimal CycloneDX 1.6 SBOM passes validation."""
        sbom = tmp_path / "sbom-cyclonedx.json"
        sbom.write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [
                {"type": "library", "name": "requests", "version": "2.31.0"},
            ],
        }))
        result = evaluate_local(
            gate_type="sbom", phase_id="1a", evidence_files=[str(sbom)]
        )
        assert result["passed"] is True
        assert result["issues"] == []

    def test_valid_spdx_json_passes(self, tmp_path) -> None:
        """Minimal SPDX 2.3 SBOM passes validation."""
        sbom = tmp_path / "sbom-spdx.json"
        sbom.write_text(json.dumps({
            "SPDXID": "SPDXRef-DOCUMENT",
            "spdxVersion": "SPDX-2.3",
            "creationInfo": {
                "created": "2026-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "name": "test-sbom",
            "dataLicense": "CC0-1.0",
            "documentNamespace": "https://example.com/test",
            "packages": [
                {
                    "SPDXID": "SPDXRef-Pkg",
                    "name": "pkg",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
            ],
            "relationships": [],
        }))
        result = evaluate_local(
            gate_type="sbom", phase_id="1a", evidence_files=[str(sbom)]
        )
        assert result["passed"] is True
        assert result["issues"] == []

    def test_missing_file_fails(self) -> None:
        """Non-existent SBOM file fails with issues."""
        result = evaluate_local(
            gate_type="sbom",
            phase_id="1a",
            evidence_files=["/nonexistent/sbom.json"],
        )
        assert result["passed"] is False
        assert len(result["issues"]) > 0

    def test_unrecognized_format_fails(self, tmp_path) -> None:
        """JSON without SBOM fields fails with 'unrecognized' or 'format' message."""
        sbom = tmp_path / "not-sbom.json"
        sbom.write_text(json.dumps({"hello": "world"}))
        result = evaluate_local(
            gate_type="sbom", phase_id="1a", evidence_files=[str(sbom)]
        )
        assert result["passed"] is False
        assert any(
            "unrecognized" in issue.lower() or "format" in issue.lower()
            for issue in result["issues"]
        )

    def test_empty_components_warns(self, tmp_path) -> None:
        """CycloneDX with empty components passes but emits warning."""
        sbom = tmp_path / "sbom-empty-components.json"
        sbom.write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [],
        }))
        result = evaluate_local(
            gate_type="sbom", phase_id="1a", evidence_files=[str(sbom)]
        )
        assert result["passed"] is True  # Not a failure — just a warning
        assert any(
            "component" in issue.lower() for issue in result["issues"]
        )


# ---------------------------------------------------------------------------
# Provenance gate (FEAT-02) -- RED until Wave 2 implements evaluate_provenance
# ---------------------------------------------------------------------------


class TestProvenanceGate:
    """Test provenance validation via evaluate_local(gate_type='provenance').

    All tests are RED until Wave 2 implements provenance handling in local_evaluator.
    """

    _INTOTO_STATEMENT = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "my-artifact", "digest": {"sha256": "abc123"}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://actions.github.io/buildtypes/workflow/v1",
                "externalParameters": {},
            },
            "runDetails": {
                "builder": {"id": "https://github.com/actions/runner"},
            },
        },
    }

    def test_valid_intoto_passes(self, tmp_path) -> None:
        """Minimal SLSA v1.0 in-toto statement passes validation."""
        prov = tmp_path / "provenance.json"
        prov.write_text(json.dumps(self._INTOTO_STATEMENT))
        result = evaluate_local(
            gate_type="provenance", phase_id="1a", evidence_files=[str(prov)]
        )
        assert result["passed"] is True

    def test_github_bundle_format_passes(self, tmp_path) -> None:
        """GitHub attestation bundle with dsseEnvelope passes validation."""
        import base64

        payload = base64.b64encode(
            json.dumps(self._INTOTO_STATEMENT).encode()
        ).decode()
        bundle = {
            "dsseEnvelope": {
                "payload": payload,
                "payloadType": "application/vnd.in-toto+json",
                "signatures": [],
            },
        }
        prov = tmp_path / "provenance-bundle.json"
        prov.write_text(json.dumps(bundle))
        result = evaluate_local(
            gate_type="provenance", phase_id="1a", evidence_files=[str(prov)]
        )
        assert result["passed"] is True

    def test_missing_predicate_type_fails(self, tmp_path) -> None:
        """In-toto statement without predicateType fails."""
        stmt = dict(self._INTOTO_STATEMENT)
        del stmt["predicateType"]
        prov = tmp_path / "provenance-no-predtype.json"
        prov.write_text(json.dumps(stmt))
        result = evaluate_local(
            gate_type="provenance", phase_id="1a", evidence_files=[str(prov)]
        )
        assert result["passed"] is False

    def test_empty_subject_fails(self, tmp_path) -> None:
        """In-toto statement with empty subject list fails."""
        stmt = dict(self._INTOTO_STATEMENT)
        stmt["subject"] = []
        prov = tmp_path / "provenance-empty-subject.json"
        prov.write_text(json.dumps(stmt))
        result = evaluate_local(
            gate_type="provenance", phase_id="1a", evidence_files=[str(prov)]
        )
        assert result["passed"] is False
