"""Evidence Gate adapter core -- shared by all CI/CD platform adapters.

Uses only stdlib (urllib.request) to avoid requiring pip install in CI.

Key functions:
  evaluate()          -- single gate evaluation via POST /v1/evaluate
  evaluate_batch()    -- batch evaluation via POST /v1/evaluate/batch
  build_evidence_ref() -- file -> SHA-256 hash + EvidenceRef dict
  fail_closed_main()  -- entry point wrapper with fail-closed semantics
"""

from __future__ import annotations

CORE_VERSION = "1.1.0"
CORE_SHA256 = ""  # placeholder -- computed below

import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EvidenceGateError(Exception):
    """Error from Evidence Gate API or adapter logic."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_BASE = "https://api.evidence-gate.com"
DEFAULT_TIMEOUT = 30  # seconds


def _get_config() -> tuple[str, str]:
    """Return (api_base, api_key) from environment.

    Returns ("", "") when EG_API_KEY is not set, enabling Free mode routing
    by the caller (entrypoint.py).
    """
    api_key = os.environ.get("EG_API_KEY", "").strip()
    if not api_key:
        return "", ""
    api_base = os.environ.get("EG_API_BASE", DEFAULT_API_BASE).rstrip("/")
    return api_base, api_key


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST to Evidence Gate API. Returns parsed JSON response.

    Raises EvidenceGateError on any failure (fail-closed).
    """
    api_base, api_key = _get_config()
    if not api_key:
        raise EvidenceGateError(
            "EG_API_KEY environment variable is required for API calls. "
            "Set it to your Evidence Gate API key."
        )
    url = f"{api_base}{path}"

    data = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "evidence-gate-adapter/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
            detail = error_body.get("detail", error_body.get("error", str(exc)))
        except Exception:
            detail = str(exc)
        raise EvidenceGateError(
            f"API error {exc.code} on {path}: {detail}"
        ) from exc
    except URLError as exc:
        raise EvidenceGateError(
            f"Network error on {path}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise EvidenceGateError(
            f"Unexpected error on {path}: {type(exc).__name__}"
        ) from exc


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------


def build_evidence_ref(file_path: str) -> dict[str, Any]:
    """Build an evidence reference from a local file.

    Returns dict compatible with EvidenceRef model schema:
      ref, path, sha256, exists, loaded_at, size_bytes (extra metadata).
    """
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        raise EvidenceGateError(f"Evidence file not found: {abs_path}")

    sha256 = hashlib.sha256()
    size = 0
    with open(abs_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
            size += len(chunk)

    return {
        "ref": os.path.basename(abs_path),
        "path": abs_path,
        "sha256": sha256.hexdigest(),
        "exists": True,
        "loaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": size,
    }


def collect_evidence_refs(paths: list[str]) -> list[dict[str, Any]]:
    """Build evidence references for multiple files."""
    return [build_evidence_ref(p) for p in paths if os.path.isfile(p)]


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def evaluate(
    *,
    gate_type: str,
    phase_id: str,
    run_id: str | None = None,
    github_run_url: str | None = None,
    evidence_url: str | None = None,
    checks: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single gate evaluation via POST /v1/evaluate."""
    body: dict[str, Any] = {
        "gate_type": gate_type,
        "phase_id": phase_id,
    }
    if run_id:
        body["run_id"] = run_id
    if github_run_url:
        body["github_run_url"] = github_run_url
    if evidence_url:
        body["evidence_url"] = evidence_url
    if checks:
        body["checks"] = checks
    if evidence:
        body["evidence"] = evidence

    return _post("/v1/evaluate", body)


def evaluate_batch(
    evaluations: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    github_run_url: str | None = None,
    evidence_url: str | None = None,
    fail_fast: bool = False,
) -> dict[str, Any]:
    """Batch evaluation via POST /v1/evaluate/batch."""
    body: dict[str, Any] = {
        "evaluations": evaluations,
        "fail_fast": fail_fast,
    }
    if run_id:
        body["run_id"] = run_id
    if github_run_url:
        body["github_run_url"] = github_run_url
    if evidence_url:
        body["evidence_url"] = evidence_url

    return _post("/v1/evaluate/batch", body)


def generate_run_id() -> str:
    """Generate a new run ID."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Entry point wrapper
# ---------------------------------------------------------------------------


def fail_closed_main(main_fn: Any) -> None:
    """Wrap adapter main() with fail-closed error handling.

    Any exception -> exit(1) to fail the CI pipeline.
    """
    try:
        result = main_fn()
        if isinstance(result, dict):
            passed = result.get("passed", False)
            if not passed:
                print("EVIDENCE GATE: Quality gate FAILED", file=sys.stderr)
                sys.exit(1)
            print("EVIDENCE GATE: Quality gate PASSED")
        elif result is False:
            print("EVIDENCE GATE: Quality gate FAILED", file=sys.stderr)
            sys.exit(1)
    except EvidenceGateError as exc:
        print(f"EVIDENCE GATE ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(
            f"EVIDENCE GATE UNEXPECTED ERROR: {type(exc).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Self-integrity hash (computed over canonical content)
# ---------------------------------------------------------------------------

def _compute_core_sha256() -> str:
    """Compute SHA-256 of this module excluding CORE_VERSION/CORE_SHA256 lines."""
    import inspect
    source_file = inspect.getfile(sys.modules[__name__])
    with open(source_file, "rb") as f:
        lines = f.readlines()
    # Exclude lines that define CORE_VERSION and CORE_SHA256
    canonical = b"".join(
        line for line in lines
        if not line.strip().startswith(b"CORE_VERSION")
        and not line.strip().startswith(b"CORE_SHA256")
    )
    return hashlib.sha256(canonical).hexdigest()


# Compute on import
CORE_SHA256 = _compute_core_sha256()
