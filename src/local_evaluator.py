"""Free mode client-side evaluator for Evidence Gate.

Provides local evaluation without an API key. Supports:
- File existence checks
- JSON structure validation
- Numeric threshold checks
- SHA-256 integrity hashes

Pro-only gate types (blind_gate, quality_state, remediation, composite, wave)
produce a warning-level upsell result instead of failure.

Uses only stdlib -- no third-party dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Pro feature boundary
# ---------------------------------------------------------------------------

PRO_ONLY_GATE_TYPES = frozenset({
    "blind_gate",
    "quality_state",
    "remediation",
    "composite",
    "wave",
})

PRICING_URL = "https://evidence-gate.com/pricing"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_file_exists(path: str) -> dict[str, Any]:
    """Verify that an evidence file exists on disk.

    Returns:
        {"passed": bool, "message": str}
    """
    abs_path = os.path.abspath(path)
    exists = os.path.isfile(abs_path)
    return {
        "passed": exists,
        "message": f"File exists: {abs_path}" if exists else f"File not found: {abs_path}",
    }


def check_json_valid(path: str) -> dict[str, Any]:
    """Parse a JSON file and validate it is well-formed.

    Returns:
        {"passed": bool, "message": str, "data": parsed_dict | None}
    """
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        return {"passed": False, "message": f"File not found: {abs_path}", "data": None}

    try:
        with open(abs_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return {"passed": False, "message": f"Invalid JSON: {exc}", "data": None}
    except OSError as exc:
        return {"passed": False, "message": f"Read error: {exc}", "data": None}

    if not isinstance(data, (dict, list)):
        return {
            "passed": False,
            "message": f"JSON root must be object or array, got {type(data).__name__}",
            "data": None,
        }

    return {"passed": True, "message": "Valid JSON", "data": data}


def check_threshold(
    value: float | int,
    *,
    min_val: float | int | None = None,
    max_val: float | int | None = None,
) -> dict[str, Any]:
    """Validate a numeric value against min/max thresholds.

    Returns:
        {"passed": bool, "message": str, "value": number}
    """
    issues: list[str] = []

    if min_val is not None and value < min_val:
        issues.append(f"Value {value} is below minimum {min_val}")
    if max_val is not None and value > max_val:
        issues.append(f"Value {value} is above maximum {max_val}")

    passed = len(issues) == 0
    message = "Threshold check passed" if passed else "; ".join(issues)
    return {"passed": passed, "message": message, "value": value}


def compute_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    h = hashlib.sha256()
    with open(abs_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# JSON structure validation
# ---------------------------------------------------------------------------


def validate_evidence_structure(
    data: Any,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Lightweight JSON structure validator.

    Schema format (subset of JSON Schema):
        {
            "type": "object",           # string | number | boolean | array | object
            "required": ["field1"],     # required field names (object only)
            "properties": {             # nested schemas per field (object only)
                "field1": {"type": "string", "pattern": "^[A-Z]+$"},
                "field2": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "items": {"type": "string"},  # item schema (array only)
        }

    Returns:
        {"passed": bool, "issues": list[str]}
    """
    issues: list[str] = []
    _validate_node(data, schema, path="$", issues=issues)
    return {"passed": len(issues) == 0, "issues": issues}


_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate_node(
    data: Any,
    schema: dict[str, Any],
    *,
    path: str,
    issues: list[str],
) -> None:
    """Recursively validate a data node against a schema node."""
    # Type check
    expected_type = schema.get("type")
    if expected_type:
        # Special case: bool is a subclass of int in Python, but
        # "number" should not accept booleans
        if expected_type == "number" and isinstance(data, bool):
            issues.append(f"{path}: expected {expected_type}, got boolean")
            return
        py_type = _TYPE_MAP.get(expected_type)
        if py_type and not isinstance(data, py_type):
            issues.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
            return

    # String validations
    if expected_type == "string" and isinstance(data, str):
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, data):
            issues.append(f"{path}: string does not match pattern '{pattern}'")

    # Number validations
    if expected_type == "number" and isinstance(data, (int, float)) and not isinstance(data, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and data < minimum:
            issues.append(f"{path}: value {data} is below minimum {minimum}")
        if maximum is not None and data > maximum:
            issues.append(f"{path}: value {data} is above maximum {maximum}")

    # Object validations
    if expected_type == "object" and isinstance(data, dict):
        # Required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                issues.append(f"{path}: missing required field '{field}'")

        # Property schemas
        properties = schema.get("properties", {})
        for field, field_schema in properties.items():
            if field in data:
                _validate_node(data[field], field_schema, path=f"{path}.{field}", issues=issues)

    # Array validations
    if expected_type == "array" and isinstance(data, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                _validate_node(item, items_schema, path=f"{path}[{i}]", issues=issues)


# ---------------------------------------------------------------------------
# Main evaluation entry point
# ---------------------------------------------------------------------------


def evaluate_local(
    gate_type: str,
    phase_id: str,
    evidence_files: list[str] | None = None,
    checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Client-side evaluation for Free mode.

    Args:
        gate_type: Type of quality gate (e.g., "skill", "tool_invocation").
        phase_id: Phase identifier (e.g., "1a", "2b").
        evidence_files: List of file paths to validate.
        checks: Optional dict with check parameters:
            - "threshold": {"value": N, "min": M, "max": X}
            - "schema": JSON-Schema-like dict for structure validation
            - "required_files": list of paths that must exist

    Returns:
        Result dict with keys: passed, mode, gate_type, phase_id, issues,
        and optionally upsell/upsell_message.
    """
    # Pro-only gate type detection
    if gate_type in PRO_ONLY_GATE_TYPES:
        return {
            "passed": True,
            "mode": "free",
            "gate_type": gate_type,
            "phase_id": phase_id,
            "issues": [],
            "upsell": True,
            "upsell_message": (
                f"'{gate_type}' requires a Pro plan. "
                f"Upgrade at {PRICING_URL} to unlock advanced gate types."
            ),
        }

    issues: list[str] = []
    evidence_files = evidence_files or []
    checks = checks or {}

    # 1. Check required files
    required_files = checks.get("required_files", [])
    for req_path in required_files:
        result = check_file_exists(req_path)
        if not result["passed"]:
            issues.append(result["message"])

    # 2. Validate evidence files exist and are valid JSON
    for efile in evidence_files:
        exists_result = check_file_exists(efile)
        if not exists_result["passed"]:
            issues.append(exists_result["message"])
            continue
        json_result = check_json_valid(efile)
        if not json_result["passed"]:
            issues.append(json_result["message"])
            continue

        # 3. Schema validation if provided
        schema = checks.get("schema")
        if schema and json_result["data"] is not None:
            struct_result = validate_evidence_structure(json_result["data"], schema)
            issues.extend(struct_result["issues"])

    # 4. Threshold check if provided
    threshold_cfg = checks.get("threshold")
    if threshold_cfg and isinstance(threshold_cfg, dict):
        value = threshold_cfg.get("value")
        if value is not None and isinstance(value, (int, float)):
            thr_result = check_threshold(
                value,
                min_val=threshold_cfg.get("min"),
                max_val=threshold_cfg.get("max"),
            )
            if not thr_result["passed"]:
                issues.append(thr_result["message"])

    passed = len(issues) == 0
    return {
        "passed": passed,
        "mode": "free",
        "gate_type": gate_type,
        "phase_id": phase_id,
        "issues": issues,
    }
