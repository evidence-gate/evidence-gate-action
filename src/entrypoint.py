"""GitHub Actions adapter for Evidence Gate.

Reads configuration from environment variables set by action.yml,
runs evaluation, and exits non-zero on failure (fail-closed).

Supports three modes:
- Free: no API key -> local evaluation via local_evaluator
- Pro: API key set -> SaaS API evaluation
- Enterprise: API key + custom API base -> self-hosted evaluation
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from fnmatch import fnmatch
from urllib.parse import urlencode

from config_loader import (
    ConfigError,
    get_config_path,
    load_config,
    resolve_config,
    validate_config,
)
from core import (
    collect_evidence_refs,
    evaluate,
    fail_closed_main,
)
from local_evaluator import evaluate_local
from presets import expand_preset
from sticky_comment import _get_pr_context, post_sticky_comment

MAX_ANNOTATIONS = 10
MAX_MAJOR_ISSUES = 5

PRICING_URL = "https://evidence-gate.dev#pricing"


def _escape_workflow_command(value: str) -> str:
    """Escape GitHub workflow command value."""
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _github_run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if not server:
        server = "https://github.com"
    if repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None


def _build_dashboard_url(run_id: str | None, evidence_id: str | None = None) -> str | None:
    base = os.environ.get("EG_DASHBOARD_BASE_URL", "").strip().rstrip("/")
    if not base or not run_id:
        return None
    params = {"run_id": run_id}
    if evidence_id:
        params["evidence_id"] = evidence_id
    return f"{base}?{urlencode(params)}"


def _append_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)
        f.write("\n")


def _set_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    safe = value.replace("\n", " ").strip()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{name}={safe}\n")


def _set_multiline_output(name: str, value: str) -> None:
    """Write a multi-line value to GITHUB_OUTPUT using heredoc delimiter.

    Uses a uuid-based delimiter to avoid collision with value content.
    """
    path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    delimiter = f"ghadelimiter_{uuid.uuid4().hex[:8]}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def _extract_missing_evidence(result: dict) -> list[dict]:
    """Extract missing evidence items from evaluation result.

    Pro/Enterprise: extracts from structured_issues where code contains "MISSING".
    Free: extracts from plain issues containing "missing" or "not found".
    Returns list of {code, message, field_path} dicts.
    """
    if result.get("passed", False):
        return []

    missing: list[dict] = []

    # Try structured_issues first (Pro/Enterprise)
    structured = result.get("structured_issues")
    if isinstance(structured, list):
        for item in structured:
            if not isinstance(item, dict):
                continue
            code = item.get("code", "")
            if isinstance(code, str) and "MISSING" in code.upper():
                missing.append({
                    "code": code,
                    "message": item.get("message", ""),
                    "field_path": item.get("field_path"),
                })
        if missing:
            return missing

    # Fallback to plain issues (Free mode)
    issues = result.get("issues", [])
    for issue in issues:
        if not isinstance(issue, str):
            continue
        text_lower = issue.lower()
        if "missing" in text_lower or "not found" in text_lower:
            missing.append({
                "code": "MISSING_EVIDENCE",
                "message": issue,
                "field_path": None,
            })

    return missing


# Recommendation table ported from SaaS remediation_recommender.
# Tuple: (gate_pattern, issue_code_pattern, action_dict)
# Uses fnmatch wildcards. First match wins per issue. Fallback at end.
_RECOMMENDATION_TABLE: list[tuple[str, str, dict]] = [
    ("security", "SECURITY_SCAN_*", {"action_id": "security-patch-vulnerabilities", "description": "Review and patch vulnerabilities in scan report", "priority": "high"}),
    ("build", "BUILD_FAIL*", {"action_id": "build-fix-compilation", "description": "Fix compilation errors before re-evaluation", "priority": "high"}),
    ("test_coverage", "COVERAGE_BELOW*", {"action_id": "coverage-add-tests", "description": "Add tests to improve code coverage", "priority": "medium"}),
    ("privacy", "PRIVACY_*", {"action_id": "privacy-update-manifest", "description": "Update privacy manifest and data handling declarations", "priority": "medium"}),
    ("*", "MISSING_EVIDENCE*", {"action_id": "missing-evidence-provide", "description": "Provide required evidence for this gate", "priority": "high"}),
    ("*", "*", {"action_id": "generic-review-issue", "description": "Review and address the reported issue", "priority": "low"}),
]

# Keyword patterns for extracting synthetic issue codes from plain text.
# Tuple: (regex_pattern, synthetic_issue_code)
_KEYWORD_PATTERNS: list[tuple[str, str]] = [
    (r"\bvulnerabilit", "SECURITY_SCAN_DETECTED"),
    (r"\bsecurity\b", "SECURITY_SCAN_DETECTED"),
    (r"\bcoverage\b", "COVERAGE_BELOW_THRESHOLD"),
    (r"\bmissing\b", "MISSING_EVIDENCE_REQUIRED"),
    (r"\bfailed\b", "BUILD_FAILURE"),
    (r"\bcompil", "BUILD_FAILURE"),
    (r"\btimeout\b", "BUILD_FAILURE"),
    (r"\bprivacy\b", "PRIVACY_ISSUE"),
]

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _extract_issue_code(issue_text: str) -> str:
    """Extract synthetic issue code from plain text using keyword patterns."""
    for pattern, code in _KEYWORD_PATTERNS:
        if re.search(pattern, issue_text, re.IGNORECASE):
            return code
    return "UNKNOWN_ISSUE"


def _match_recommendation(gate_type: str, issue_code: str) -> dict | None:
    """Match gate_type + issue_code against recommendation table."""
    for gate_pat, code_pat, action in _RECOMMENDATION_TABLE:
        if fnmatch(gate_type, gate_pat) and fnmatch(issue_code, code_pat):
            return action
    return None


def _generate_suggested_actions(gate_type: str, result: dict) -> list[str]:
    """Generate human-readable repair steps from evaluation result.

    Uses _RECOMMENDATION_TABLE and _KEYWORD_PATTERNS ported from SaaS.
    Returns list of "- [priority] description" strings, sorted high > medium > low.
    """
    if result.get("passed", False):
        return []

    seen_action_ids: set[str] = set()
    actions: list[tuple[int, str]] = []  # (priority_order, formatted_string)

    # Collect issue codes
    issue_codes: list[str] = []
    structured = result.get("structured_issues")
    if isinstance(structured, list):
        for item in structured:
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                issue_codes.append(item["code"])

    # Fallback to plain issues
    if not issue_codes:
        for issue in result.get("issues", []):
            if isinstance(issue, str):
                issue_codes.append(_extract_issue_code(issue))

    # Match and deduplicate
    for code in issue_codes:
        rec = _match_recommendation(gate_type, code)
        if rec and rec["action_id"] not in seen_action_ids:
            seen_action_ids.add(rec["action_id"])
            priority = rec.get("priority", "low")
            order = _PRIORITY_ORDER.get(priority, 2)
            actions.append((order, f"- [{priority}] {rec['description']}"))

    # Sort by priority (high first)
    actions.sort(key=lambda x: x[0])
    return [a[1] for a in actions]


def _emit_annotations(
    issues: list[str], passed: bool, *, observe_mode: bool = False
) -> None:
    if observe_mode:
        level = "notice"
    else:
        level = "warning" if passed else "error"
    title = "Evidence Gate"
    for issue in issues[:MAX_ANNOTATIONS]:
        message = _escape_workflow_command(issue)
        print(f"::{level} title={title}::{message}")


def _detect_mode(api_key: str) -> str:
    """Detect operation mode based on environment.

    Returns:
        "free", "pro", or "enterprise"
    """
    if not api_key:
        return "free"
    api_base = os.environ.get("EG_API_BASE", "").strip()
    if api_base:
        return "enterprise"
    return "pro"


def _build_heading() -> str:
    """Build summary heading, including gate_type/phase_id when available."""
    gate_type = os.environ.get("EG_GATE_TYPE", "")
    phase_id = os.environ.get("EG_PHASE_ID", "")
    if gate_type and phase_id:
        return f"## Evidence Gate: {gate_type} ({phase_id})"
    elif gate_type:
        return f"## Evidence Gate: {gate_type}"
    return "## Evidence Gate"


def _write_summary(
    *,
    run_id: str | None,
    result: dict,
    github_run_url: str | None,
    dashboard_url: str | None,
    mode: str,
    observe_mode: bool = False,
) -> None:
    metadata = result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    passed = bool(result.get("passed", False))
    issues = result.get("issues", [])
    issue_list = [str(i) for i in issues if isinstance(i, str)]
    major_issues = issue_list[:MAX_MAJOR_ISSUES]
    trace_url = metadata_dict.get("trace_url")
    evidence_url = metadata_dict.get("evidence_url")

    heading = _build_heading()
    if observe_mode:
        status_text = "OBSERVE (PASS)" if passed else "OBSERVE (would FAIL)"
    else:
        status_text = "PASS" if passed else "FAIL"

    # Always-visible result line
    lines = [heading, "", f"**Result:** {status_text} | **Mode:** {mode}", ""]

    # Optional metadata rows -- filter out empty values
    optional_rows = [
        ("Run ID", run_id),
        ("GitHub Run", github_run_url),
        ("Langfuse Trace", trace_url),
        ("Evidence URL", evidence_url),
        ("Dashboard", dashboard_url),
    ]
    visible_rows = [(k, v) for k, v in optional_rows if v and v != "-"]

    if visible_rows:
        lines.append("<details>")
        lines.append("<summary>Metadata</summary>")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.extend(f"| {k} | {v} |" for k, v in visible_rows)
        lines.append("")
        lines.append("</details>")

    # Major issues (always visible, outside details)
    if major_issues:
        lines.extend(["", "### Major Issues"])
        lines.extend(f"- {issue}" for issue in major_issues)

    _append_summary("\n".join(lines))


def _write_upsell_summary(gate_type: str, upsell_message: str) -> None:
    """Append upsell message to GITHUB_STEP_SUMMARY."""
    lines = [
        "",
        "### Upgrade Available",
        "",
        f"> {upsell_message}",
        "",
        f"[View Plans]({PRICING_URL})",
    ]
    _append_summary("\n".join(lines))


def _write_error_summary(
    *,
    run_id: str | None,
    error_text: str,
    github_run_url: str | None,
    dashboard_url: str | None,
) -> None:
    heading = _build_heading()
    lines = [
        heading,
        "",
        "**Result:** FAIL",
        "",
        f"**Error:** {error_text}",
    ]

    # Optional metadata rows -- filter out empty values
    optional_rows = [
        ("Run ID", run_id),
        ("GitHub Run", github_run_url),
        ("Dashboard", dashboard_url),
    ]
    visible_rows = [(k, v) for k, v in optional_rows if v and v != "-"]

    if visible_rows:
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Metadata</summary>")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.extend(f"| {k} | {v} |" for k, v in visible_rows)
        lines.append("")
        lines.append("</details>")

    _append_summary("\n".join(lines))


def _evaluate_single_gate(
    *,
    gate_type: str,
    phase_id: str,
    api_key: str,
    evidence_file_paths: list[str],
    run_id: str,
    github_run_url: str | None,
    evidence_url: str | None,
    dashboard_url: str | None,
    mode: str,
) -> dict:
    """Evaluate a single gate. Returns result dict.

    Handles Pro/Enterprise (API) and Free (local) modes.
    Raises on Pro/Enterprise API errors.
    """
    if api_key:
        evidence: dict = {}
        if evidence_file_paths:
            refs = collect_evidence_refs(evidence_file_paths)
            if refs:
                evidence["evidence_refs"] = refs

        try:
            result = evaluate(
                gate_type=gate_type,
                phase_id=phase_id,
                run_id=run_id or None,
                github_run_url=github_run_url,
                evidence_url=evidence_url,
                evidence=evidence or None,
            )
            print("::notice title=Evidence Gate::OIDC authentication successful")
        except Exception as exc:
            _set_output("passed", "false")
            _set_output("mode", mode)
            _set_output("run_id", run_id)
            _set_output("github_run_url", github_run_url or "")
            _set_output("dashboard_url", dashboard_url or "")
            _write_error_summary(
                run_id=run_id or None,
                error_text=str(exc),
                github_run_url=github_run_url,
                dashboard_url=dashboard_url,
            )
            raise
    else:
        checks_json = os.environ.get("EG_CHECKS", "").strip()
        checks: dict | None = None
        if checks_json:
            try:
                checks = json.loads(checks_json)
            except (ValueError, TypeError):
                checks = None

        result = evaluate_local(
            gate_type=gate_type,
            phase_id=phase_id,
            evidence_files=evidence_file_paths or None,
            checks=checks,
        )

    # Attach gate_type for multi-gate aggregation
    result["gate_type"] = gate_type
    return result


def _handle_sticky_comment(
    results: list[dict],
    observe_mode: bool,
) -> None:
    """Post sticky comment if enabled and in PR context."""
    sticky_enabled = os.environ.get("EG_STICKY_COMMENT", "false").lower() == "true"
    if not sticky_enabled:
        return

    pr_context = _get_pr_context()
    if pr_context is None:
        print(
            "::warning title=Evidence Gate::"
            "sticky_comment=true but no PR context (not a pull_request event)"
        )
        return

    owner, repo, pr_number = pr_context
    token = os.environ.get("GITHUB_TOKEN", "")
    post_sticky_comment(owner, repo, pr_number, token, results, observe_mode)


def _handle_result(
    *,
    result: dict,
    gate_type: str,
    run_id: str,
    github_run_url: str | None,
    dashboard_url: str | None,
    evidence_url: str | None,
    mode: str,
    observe_mode: bool,
) -> None:
    """Write summary, annotations, and outputs for a single-gate result."""
    # Handle upsell (Free mode + Pro-only gate type)
    if result.get("upsell"):
        upsell_msg = result.get("upsell_message", "")
        print(
            f"::warning title=Evidence Gate::"
            f"{_escape_workflow_command(upsell_msg)}"
        )
        _write_upsell_summary(gate_type, upsell_msg)
        _set_output("passed", "true")
        _set_output("mode", mode)
        _set_output("upsell", "true")
        _set_output("run_id", run_id)
        _set_output("github_run_url", github_run_url or "")
        _set_output("dashboard_url", dashboard_url or "")
        _set_multiline_output("missing_evidence", json.dumps([]))
        _set_multiline_output("suggested_actions", "")
        _set_multiline_output("json_output", json.dumps(result))
        return

    # Standard result handling
    metadata = result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    trace_url = metadata_dict.get("trace_url", "")
    evidence_link = metadata_dict.get("evidence_url", "") or evidence_url or ""
    issues = result.get("issues", [])
    issue_list = [str(i) for i in issues if isinstance(i, str)]
    passed = bool(result.get("passed", False))

    _write_summary(
        run_id=run_id or None,
        result=result,
        github_run_url=github_run_url,
        dashboard_url=dashboard_url,
        mode=mode,
        observe_mode=observe_mode,
    )
    _emit_annotations(issue_list, passed=passed, observe_mode=observe_mode)

    _set_output("passed", str(passed).lower())
    _set_output("mode", mode)
    _set_output("run_id", run_id)
    _set_output("trace_url", str(trace_url))
    _set_output("evidence_url", str(evidence_link))
    _set_output("dashboard_url", dashboard_url or "")
    _set_output("github_run_url", github_run_url or "")
    _set_output("major_issue_count", str(len(issue_list)))
    if observe_mode:
        _set_output("observe_would_pass", str(passed).lower())

    # Actionable outputs (FEAT-02, FEAT-03)
    missing = _extract_missing_evidence(result)
    _set_multiline_output("missing_evidence", json.dumps(missing))
    actions = _generate_suggested_actions(gate_type, result)
    _set_multiline_output("suggested_actions", "\n".join(actions))

    _set_multiline_output("json_output", json.dumps(result))


def main() -> dict:
    """Run Evidence Gate evaluation for GitHub Actions."""
    # --- Config file loading (CONFIG-01..CONFIG-05) ---
    env_config_path = os.environ.get("EG_CONFIG_PATH", "").strip()
    config_path = get_config_path(env_config_path)

    try:
        file_config = load_config(config_path)
    except ConfigError:
        sys.exit(1)

    errors = validate_config(file_config, config_path)
    if errors:
        sys.exit(1)

    # Resolve all settings: env > config file > defaults
    resolved = resolve_config(
        env_gate_type=os.environ.get("EG_GATE_TYPE", "").strip(),
        env_phase_id=os.environ.get("EG_PHASE_ID", "").strip(),
        env_mode=os.environ.get("EG_MODE", "").strip(),
        env_evidence_files=os.environ.get("EG_EVIDENCE_FILES", "").strip(),
        env_gate_preset=os.environ.get("EG_GATE_PRESET", "").strip(),
        env_config_path=env_config_path,
        file_config=file_config,
    )

    gate_type = resolved.gate_type
    phase_id = resolved.phase_id
    gate_preset = resolved.gate_preset
    evidence_files_str = resolved.evidence_files

    run_id = os.environ.get("EG_RUN_ID", "") or os.environ.get("GITHUB_RUN_ID", "")
    github_run_url = _github_run_url()
    dashboard_url = _build_dashboard_url(run_id or None)
    evidence_url = os.environ.get("EG_EVIDENCE_URL", "").strip() or dashboard_url

    # Resolve gate_type vs gate_preset
    if gate_type and gate_preset:
        # gate_type takes precedence
        debug = os.environ.get("EG_DEBUG", "false").lower() == "true"
        if debug:
            print("[DEBUG] gate_type takes precedence over gate_preset")
        gate_preset = ""  # ignore preset

    if not gate_type and not gate_preset:
        if not phase_id:
            print("ERROR: EG_GATE_TYPE and EG_PHASE_ID are required", file=sys.stderr)
        else:
            print("ERROR: Either gate_type or gate_preset is required", file=sys.stderr)
        sys.exit(1)

    if not phase_id:
        print("ERROR: EG_PHASE_ID is required", file=sys.stderr)
        sys.exit(1)

    # Parse evidence file paths
    evidence_file_paths: list[str] = []
    if evidence_files_str:
        evidence_file_paths = [p.strip() for p in evidence_files_str.split(",") if p.strip()]

    # Mode detection
    api_key = os.environ.get("EG_API_KEY", "").strip()
    if api_key:
        print(f"::add-mask::{api_key}")
    mode = _detect_mode(api_key)

    # Observe mode detection
    observe_mode = resolved.mode.lower() == "observe"
    if observe_mode:
        print(
            "::notice title=Evidence Gate::"
            "Running in observe mode -- failures will not block this step"
        )

    # Debug logging (DX-03)
    debug = os.environ.get("EG_DEBUG", "false").lower() == "true"
    if debug:
        version = os.environ.get("EG_VERSION", "latest")
        print(f"[DEBUG] gate_type={gate_type}, phase_id={phase_id}, mode={mode}")
        print(f"[DEBUG] version={version}")
        print(f"[DEBUG] evidence_files={evidence_file_paths}")
        print(f"[DEBUG] api_base={os.environ.get('EG_API_BASE', 'default')}")
        print(f"[DEBUG] run_id={run_id}")
        if gate_preset:
            print(f"[DEBUG] gate_preset={gate_preset}")

    # -- Preset mode: expand and evaluate multiple gates --
    if gate_preset:
        gate_types = expand_preset(gate_preset)
        results: list[dict] = []

        for gt in gate_types:
            os.environ["EG_GATE_TYPE"] = gt  # for _build_heading
            result = _evaluate_single_gate(
                gate_type=gt,
                phase_id=phase_id,
                api_key=api_key,
                evidence_file_paths=evidence_file_paths,
                run_id=run_id,
                github_run_url=github_run_url,
                evidence_url=evidence_url,
                dashboard_url=dashboard_url,
                mode=mode,
            )
            results.append(result)

            # Write per-gate summary
            _write_summary(
                run_id=run_id or None,
                result=result,
                github_run_url=github_run_url,
                dashboard_url=dashboard_url,
                mode=mode,
                observe_mode=observe_mode,
            )

        # Aggregate results
        all_passed = all(r.get("passed", False) for r in results)
        all_missing: list[dict] = []
        all_actions: list[str] = []
        for r in results:
            all_missing.extend(_extract_missing_evidence(r))
            all_actions.extend(
                _generate_suggested_actions(r.get("gate_type", ""), r)
            )

        # Set outputs
        _set_output("passed", str(all_passed).lower())
        _set_output("mode", mode)
        _set_output("run_id", run_id)
        _set_output("github_run_url", github_run_url or "")
        _set_output("dashboard_url", dashboard_url or "")
        if observe_mode:
            _set_output("observe_would_pass", str(all_passed).lower())
        _set_multiline_output("missing_evidence", json.dumps(all_missing))
        _set_multiline_output("suggested_actions", "\n".join(all_actions))
        _set_multiline_output("json_output", json.dumps(results))

        # Sticky comment
        _handle_sticky_comment(results, observe_mode)

        # Return aggregated result for fail_closed_main
        return {"passed": all_passed, "results": results}

    # -- Single gate mode --
    result = _evaluate_single_gate(
        gate_type=gate_type,
        phase_id=phase_id,
        api_key=api_key,
        evidence_file_paths=evidence_file_paths,
        run_id=run_id,
        github_run_url=github_run_url,
        evidence_url=evidence_url,
        dashboard_url=dashboard_url,
        mode=mode,
    )

    _handle_result(
        result=result,
        gate_type=gate_type,
        run_id=run_id,
        github_run_url=github_run_url,
        dashboard_url=dashboard_url,
        evidence_url=evidence_url,
        mode=mode,
        observe_mode=observe_mode,
    )

    # Sticky comment (single gate)
    _handle_sticky_comment([result], observe_mode)

    return result


if __name__ == "__main__":
    fail_closed_main(main)
