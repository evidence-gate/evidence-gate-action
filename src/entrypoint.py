"""GitHub Actions adapter for Evidence Gate.

Reads configuration from environment variables set by action.yml,
runs evaluation, and exits non-zero on failure (fail-closed).

Supports three modes:
- Free: no API key -> local evaluation via local_evaluator
- Pro: API key set -> SaaS API evaluation
- Enterprise: API key + custom API base -> self-hosted evaluation
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlencode

from core import (
    collect_evidence_refs,
    evaluate,
    fail_closed_main,
)
from local_evaluator import evaluate_local

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


def _emit_annotations(issues: list[str], passed: bool) -> None:
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


def main() -> dict:
    """Run Evidence Gate evaluation for GitHub Actions."""
    gate_type = os.environ.get("EG_GATE_TYPE", "")
    phase_id = os.environ.get("EG_PHASE_ID", "")
    run_id = os.environ.get("EG_RUN_ID", "") or os.environ.get("GITHUB_RUN_ID", "")
    evidence_files_str = os.environ.get("EG_EVIDENCE_FILES", "")
    github_run_url = _github_run_url()
    dashboard_url = _build_dashboard_url(run_id or None)
    evidence_url = os.environ.get("EG_EVIDENCE_URL", "").strip() or dashboard_url

    if not gate_type or not phase_id:
        print("ERROR: EG_GATE_TYPE and EG_PHASE_ID are required", file=sys.stderr)
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

    # Debug logging (DX-03)
    debug = os.environ.get("EG_DEBUG", "false").lower() == "true"
    if debug:
        print(f"[DEBUG] gate_type={gate_type}, phase_id={phase_id}, mode={mode}")
        print(f"[DEBUG] evidence_files={evidence_file_paths}")
        print(f"[DEBUG] api_base={os.environ.get('EG_API_BASE', 'default')}")
        print(f"[DEBUG] run_id={run_id}")

    if api_key:
        # Pro/Enterprise mode -- delegate to SaaS API
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
        # Free mode -- local evaluation
        checks_json = os.environ.get("EG_CHECKS", "").strip()
        checks: dict | None = None
        if checks_json:
            try:
                checks = __import__("json").loads(checks_json)
            except (ValueError, TypeError):
                checks = None

        result = evaluate_local(
            gate_type=gate_type,
            phase_id=phase_id,
            evidence_files=evidence_file_paths or None,
            checks=checks,
        )

    # Handle upsell (Free mode + Pro-only gate type)
    if result.get("upsell"):
        upsell_msg = result.get("upsell_message", "")
        # Emit warning-level annotation (not error)
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
        return result

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
    )
    _emit_annotations(issue_list, passed=passed)

    _set_output("passed", str(passed).lower())
    _set_output("mode", mode)
    _set_output("run_id", run_id)
    _set_output("trace_url", str(trace_url))
    _set_output("evidence_url", str(evidence_link))
    _set_output("dashboard_url", dashboard_url or "")
    _set_output("github_run_url", github_run_url or "")
    _set_output("major_issue_count", str(len(issue_list)))

    return result


if __name__ == "__main__":
    fail_closed_main(main)
