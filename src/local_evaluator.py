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

import base64
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

NEMOCLAW_GATE_TYPES = frozenset({
    "nemoclaw_blueprint",
    "nemoclaw_policy",
})

PRICING_URL = "https://evidence-gate.dev#pricing"


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
# YAML parsing (optional, for NemoClaw gates)
# ---------------------------------------------------------------------------


def _parse_yaml_or_json(path: str) -> dict[str, Any]:
    """Parse a file as JSON or YAML. Returns parsed dict.

    YAML support requires PyYAML (``pip install pyyaml``).
    Falls back to JSON parsing for .json files.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise ValueError(f"File not found: {abs_path}")

    with open(abs_path, encoding="utf-8") as f:
        content = f.read()

    if abs_path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as err:
            raise ValueError(
                "YAML evidence files require PyYAML: pip install pyyaml"
            ) from err
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a mapping, got {type(data).__name__}")
        return data

    # Default: JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# NemoClaw blueprint validation
# ---------------------------------------------------------------------------

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+")


def _check_blueprint(data: dict[str, Any]) -> list[str]:
    """Validate NemoClaw blueprint.yaml structure.

    Checks:
    - Required fields: version, profiles, sandbox
    - version is semver-like
    - profiles has at least one entry, each with required keys
    - sandbox has image field
    - Optional version constraints are semver-like
    """
    issues: list[str] = []

    # version
    version = data.get("version")
    if not version:
        issues.append("BLUEPRINT_MISSING_VERSION: 'version' field is required")
    elif not isinstance(version, str) or not _SEMVER_PATTERN.match(version):
        issues.append(f"BLUEPRINT_INVALID_VERSION: version '{version}' is not valid semver")

    # profiles
    profiles = data.get("profiles")
    if profiles is None:
        issues.append("BLUEPRINT_MISSING_PROFILES: 'profiles' section is required")
    elif not isinstance(profiles, dict):
        issues.append("BLUEPRINT_INVALID_PROFILES: 'profiles' must be a mapping")
    elif len(profiles) == 0:
        issues.append("BLUEPRINT_EMPTY_PROFILES: at least one profile is required")
    else:
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                issues.append(f"BLUEPRINT_INVALID_PROFILE: profile '{name}' must be a mapping")
                continue
            for required_key in ("model",):
                if required_key not in profile:
                    issues.append(
                        f"BLUEPRINT_PROFILE_MISSING_{required_key.upper()}: "
                        f"profile '{name}' missing '{required_key}'"
                    )

    # sandbox
    sandbox = data.get("sandbox")
    if not sandbox:
        issues.append("BLUEPRINT_MISSING_SANDBOX: 'sandbox' section is required")
    elif not isinstance(sandbox, dict):
        issues.append("BLUEPRINT_INVALID_SANDBOX: 'sandbox' must be a mapping")
    else:
        if "image" not in sandbox:
            issues.append("BLUEPRINT_MISSING_IMAGE: 'sandbox.image' is required")

    # Optional version constraints
    for field in ("min_openshell_version", "min_openclaw_version"):
        val = data.get(field)
        if val is not None and (not isinstance(val, str) or not _SEMVER_PATTERN.match(val)):
            issues.append(
                f"BLUEPRINT_INVALID_{field.upper()}: '{val}' is not valid semver"
            )

    return issues


# ---------------------------------------------------------------------------
# NemoClaw policy validation (security audit)
# ---------------------------------------------------------------------------


def _check_policy(data: dict[str, Any]) -> list[str]:
    """Validate NemoClaw OpenShell policy YAML security posture.

    Checks:
    - Required fields: version, network_policies
    - All endpoints have enforcement: enforce
    - Port 443 endpoints have tls: terminate
    - No wildcard method rules on any endpoint
    - Binary scoping present (endpoints have process restrictions)
    - filesystem_policy does not include dangerous writable paths
    """
    issues: list[str] = []

    # version
    if "version" not in data:
        issues.append("POLICY_MISSING_VERSION: 'version' field is required")

    # network_policies
    policies = data.get("network_policies")
    if not policies:
        issues.append("POLICY_MISSING_NETWORK: 'network_policies' section is required")
    elif not isinstance(policies, dict):
        issues.append("POLICY_INVALID_NETWORK: 'network_policies' must be a mapping")
    else:
        for policy_name, policy in policies.items():
            if not isinstance(policy, dict):
                issues.append(f"POLICY_INVALID_ENTRY: '{policy_name}' must be a mapping")
                continue
            endpoints = policy.get("endpoints", [])
            if not isinstance(endpoints, list):
                issues.append(f"POLICY_INVALID_ENDPOINTS: '{policy_name}.endpoints' must be a list")
                continue

            for i, ep in enumerate(endpoints):
                if not isinstance(ep, dict):
                    continue
                ep_id = f"{policy_name}.endpoints[{i}] ({ep.get('host', '?')})"

                # enforcement check
                enforcement = ep.get("enforcement")
                if enforcement and enforcement != "enforce":
                    issues.append(
                        f"POLICY_WEAK_ENFORCEMENT: {ep_id} has "
                        f"enforcement='{enforcement}', expected 'enforce'"
                    )

                # TLS check for port 443
                port = ep.get("port")
                tls = ep.get("tls")
                if port == 443 and tls != "terminate":
                    issues.append(
                        f"POLICY_MISSING_TLS: {ep_id} on port 443 "
                        f"should have tls='terminate'"
                    )

                # Wildcard method check
                rules = ep.get("rules", [])
                if isinstance(rules, list):
                    for rule in rules:
                        if isinstance(rule, dict):
                            allow = rule.get("allow", {})
                            if isinstance(allow, dict):
                                method = allow.get("method", "")
                                if method == "*":
                                    issues.append(
                                        f"POLICY_WILDCARD_METHOD: {ep_id} "
                                        f"has wildcard method rule (method='*')"
                                    )

    # filesystem_policy dangerous writable paths
    fs_policy = data.get("filesystem_policy")
    if isinstance(fs_policy, dict):
        dangerous_paths = {"/usr", "/etc", "/lib", "/bin", "/sbin", "/var", "/root"}
        rw_paths = fs_policy.get("read_write", [])
        if isinstance(rw_paths, list):
            for rw_path in rw_paths:
                if isinstance(rw_path, str):
                    for dangerous in dangerous_paths:
                        if rw_path == dangerous or rw_path.startswith(dangerous + "/"):
                            issues.append(
                                f"POLICY_DANGEROUS_WRITABLE: filesystem allows "
                                f"write to '{rw_path}'"
                            )

    return issues


def _evaluate_nemoclaw(
    gate_type: str,
    phase_id: str,
    evidence_files: list[str],
) -> dict[str, Any]:
    """Evaluate NemoClaw blueprint or policy evidence files.

    Parses each evidence file (JSON or YAML) and runs gate-specific checks.
    """
    issues: list[str] = []

    if not evidence_files:
        issues.append(f"No evidence files provided for {gate_type} gate")
        return {
            "passed": False,
            "mode": "free",
            "gate_type": gate_type,
            "phase_id": phase_id,
            "issues": issues,
        }

    for path in evidence_files:
        try:
            data = _parse_yaml_or_json(path)
        except ValueError as exc:
            issues.append(str(exc))
            continue

        if gate_type == "nemoclaw_blueprint":
            issues.extend(_check_blueprint(data))
        elif gate_type == "nemoclaw_policy":
            issues.extend(_check_policy(data))

    passed = len(issues) == 0
    return {
        "passed": passed,
        "mode": "free",
        "gate_type": gate_type,
        "phase_id": phase_id,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# SBOM evaluation
# ---------------------------------------------------------------------------

MAX_ISSUES = 10


def _detect_sbom_format(data: dict[str, Any]) -> str | None:
    """Detect SBOM format from parsed JSON data.

    Returns:
        "cyclonedx", "spdx", or None if unrecognized.
    """
    # CycloneDX detection: bomFormat == "CycloneDX" and specVersion present
    if data.get("bomFormat") == "CycloneDX" and "specVersion" in data:
        return "cyclonedx"

    # SPDX detection: spdxVersion or SPDXVersion starts with "SPDX-" and SPDXID present
    spdx_ver = data.get("spdxVersion") or data.get("SPDXVersion") or ""
    if isinstance(spdx_ver, str) and spdx_ver.startswith("SPDX-") and "SPDXID" in data:
        return "spdx"

    return None


def evaluate_sbom(
    phase_id: str,
    evidence_files: list[str],
) -> dict[str, Any]:
    """Evaluate SBOM evidence files (CycloneDX or SPDX).

    Performs structural validation -- not cryptographic.
    Unrecognized formats fail; empty components/packages produce a warning
    but the result still passes.

    Returns:
        Result dict with keys: passed, mode, gate_type, phase_id, issues.
    """
    issues: list[str] = []

    for efile in evidence_files:
        if len(issues) >= MAX_ISSUES:
            break

        # File existence check
        exists_result = check_file_exists(efile)
        if not exists_result["passed"]:
            issues.append(exists_result["message"])
            continue

        # Parse JSON
        json_result = check_json_valid(efile)
        if not json_result["passed"]:
            issues.append(json_result["message"])
            continue

        data = json_result["data"]
        if not isinstance(data, dict):
            issues.append(f"SBOM root must be an object, got {type(data).__name__}")
            continue

        # Detect format
        fmt = _detect_sbom_format(data)
        if fmt is None:
            issues.append(
                "Unrecognized SBOM format: neither CycloneDX nor SPDX fields found"
            )
            continue

        # Validate components/packages
        if fmt == "cyclonedx":
            components = data.get("components")
            if not components:
                issues.append(
                    "Warning: CycloneDX SBOM has empty or missing components array"
                )
        elif fmt == "spdx":
            packages = data.get("packages")
            if not packages:
                issues.append(
                    "Warning: SPDX SBOM has empty or missing packages array"
                )

    # Warnings (component/package emptiness) do not cause failure
    failed = any(
        not issue.startswith("Warning:") for issue in issues
    )
    return {
        "passed": not failed,
        "mode": "free",
        "gate_type": "sbom",
        "phase_id": phase_id,
        "issues": issues[:MAX_ISSUES],
    }


# ---------------------------------------------------------------------------
# Provenance evaluation
# ---------------------------------------------------------------------------


def _validate_intoto_statement(
    stmt: dict[str, Any],
    issues: list[str],
    source_label: str = "",
) -> None:
    """Validate an in-toto v1 statement structure.

    Appends issues for missing/invalid fields.
    """
    prefix = f"{source_label}: " if source_label else ""

    # _type field
    stmt_type = stmt.get("_type", "")
    if not isinstance(stmt_type, str) or not stmt_type.startswith(
        "https://in-toto.io/Statement/"
    ):
        issues.append(
            f"{prefix}Missing or invalid '_type' field "
            "(expected 'https://in-toto.io/Statement/...')"
        )

    # subject: non-empty list with name + digest
    subject = stmt.get("subject")
    if not isinstance(subject, list) or len(subject) == 0:
        issues.append(f"{prefix}Missing or empty 'subject' list")
    else:
        for i, subj in enumerate(subject):
            if not isinstance(subj, dict):
                issues.append(f"{prefix}subject[{i}]: expected object")
                continue
            if "name" not in subj:
                issues.append(f"{prefix}subject[{i}]: missing 'name'")
            if "digest" not in subj or not isinstance(subj.get("digest"), dict):
                issues.append(f"{prefix}subject[{i}]: missing or invalid 'digest'")

    # predicateType
    if "predicateType" not in stmt:
        issues.append(f"{prefix}Missing 'predicateType' field")

    # predicate
    predicate = stmt.get("predicate")
    if not isinstance(predicate, dict):
        issues.append(f"{prefix}Missing or invalid 'predicate' object")
    else:
        # SLSA v1.0 specific checks
        build_def = predicate.get("buildDefinition")
        if isinstance(build_def, dict) and "buildType" not in build_def:
            issues.append(
                f"{prefix}predicate.buildDefinition missing 'buildType'"
            )
        run_details = predicate.get("runDetails")
        if isinstance(run_details, dict):
            builder = run_details.get("builder")
            if isinstance(builder, dict) and "id" not in builder:
                issues.append(
                    f"{prefix}predicate.runDetails.builder missing 'id'"
                )


def evaluate_provenance(
    phase_id: str,
    evidence_files: list[str],
) -> dict[str, Any]:
    """Evaluate provenance evidence files (in-toto DSSE or GitHub attestation bundle).

    Detects format:
    - dsseEnvelope key -> GitHub attestation bundle (base64 payload decoded)
    - _type key -> raw in-toto statement

    Performs structural validation of the in-toto statement.

    Returns:
        Result dict with keys: passed, mode, gate_type, phase_id, issues.
    """
    issues: list[str] = []

    for efile in evidence_files:
        if len(issues) >= MAX_ISSUES:
            break

        # File existence check
        exists_result = check_file_exists(efile)
        if not exists_result["passed"]:
            issues.append(exists_result["message"])
            continue

        # Parse JSON
        json_result = check_json_valid(efile)
        if not json_result["passed"]:
            issues.append(json_result["message"])
            continue

        data = json_result["data"]
        if not isinstance(data, dict):
            issues.append(
                f"Provenance root must be an object, got {type(data).__name__}"
            )
            continue

        # Detect format: dsseEnvelope first, then raw in-toto
        if "dsseEnvelope" in data:
            envelope = data["dsseEnvelope"]
            if not isinstance(envelope, dict) or "payload" not in envelope:
                issues.append("dsseEnvelope missing 'payload' field")
                continue
            try:
                raw_payload = base64.b64decode(envelope["payload"])
                stmt = json.loads(raw_payload)
            except (ValueError, json.JSONDecodeError):
                issues.append(
                    "Failed to decode attestation bundle payload"
                )
                continue
            if not isinstance(stmt, dict):
                issues.append("Decoded payload is not a JSON object")
                continue
            _validate_intoto_statement(stmt, issues, source_label="bundle")
        elif "_type" in data:
            _validate_intoto_statement(data, issues)
        else:
            issues.append(
                "Unrecognized provenance format: "
                "neither dsseEnvelope nor _type field found"
            )

    passed = len(issues) == 0
    return {
        "passed": passed,
        "mode": "free",
        "gate_type": "provenance",
        "phase_id": phase_id,
        "issues": issues[:MAX_ISSUES],
    }


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
    # NemoClaw gate types -- specialized evaluation
    if gate_type in NEMOCLAW_GATE_TYPES:
        return _evaluate_nemoclaw(gate_type, phase_id, evidence_files or [])

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

    # Specialised gate type dispatch (Free mode)
    if gate_type == "sbom":
        return evaluate_sbom(phase_id, evidence_files or [])
    if gate_type == "provenance":
        return evaluate_provenance(phase_id, evidence_files or [])

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
