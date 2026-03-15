"""Sticky PR comment for Evidence Gate.

Aggregates multi-gate results into a single updating PR comment
using an HTML marker for identification. Creates or updates
the comment via the GitHub REST API.

Uses only stdlib (urllib.request) -- no third-party dependencies.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MARKER = "<!-- evidence-gate-sticky -->"

_API_BASE = "https://api.github.com"
_TIMEOUT = 15


def _github_api(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> dict | list:
    """Make a GitHub REST API call.

    Returns parsed JSON (dict or list).
    Raises HTTPError on failure.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    if body:
        headers["Content-Type"] = "application/json"

    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def find_existing_comment(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
) -> int | None:
    """Find an existing sticky comment on a PR.

    Pages through PR comments looking for the MARKER.
    Returns the comment ID if found, None otherwise.
    """
    page = 1
    while True:
        url = (
            f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}"
            f"/comments?per_page=100&page={page}"
        )
        comments = _github_api("GET", url, token)
        if not isinstance(comments, list) or not comments:
            return None
        for comment in comments:
            if isinstance(comment, dict) and MARKER in comment.get("body", ""):
                return comment["id"]
        if len(comments) < 100:
            return None
        page += 1


def _build_comment_body(results: list[dict], observe: bool) -> str:
    """Build the markdown body for the sticky comment.

    Args:
        results: List of dicts with gate_type and passed keys.
        observe: Whether running in observe mode.

    Returns:
        Markdown string with MARKER, heading, and results table.
    """
    lines = [
        MARKER,
        "",
        "## Evidence Gate Results",
        "",
        "| Gate | Result | Mode |",
        "|------|--------|------|",
    ]

    for r in results:
        gate = r.get("gate_type", "unknown")
        passed = r.get("passed", False)
        if observe:
            if passed:
                status = "OBSERVE (PASS)"
            else:
                status = "OBSERVE (would FAIL)"
            mode = "observe"
        else:
            status = "PASS" if passed else "FAIL"
            mode = "enforce"
        lines.append(f"| {gate} | {status} | {mode} |")

    lines.append("")
    return "\n".join(lines)


def post_sticky_comment(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    results: list[dict],
    observe: bool,
) -> None:
    """Create or update the sticky comment on a PR.

    Finds an existing comment by MARKER and updates it,
    or creates a new one if none exists.

    HTTP errors are caught and emitted as ::warning:: annotations
    to avoid crashing the workflow step.
    """
    body_text = _build_comment_body(results, observe)

    try:
        existing_id = find_existing_comment(owner, repo, pr_number, token)
        if existing_id is not None:
            url = f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{existing_id}"
            _github_api("PATCH", url, token, body={"body": body_text})
        else:
            url = f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
            _github_api("POST", url, token, body={"body": body_text})
    except HTTPError as exc:
        if exc.code == 403:
            print(
                "::warning title=Evidence Gate::"
                "Sticky comment requires pull-requests: write permission"
            )
        else:
            print(
                f"::warning title=Evidence Gate::"
                f"Failed to post sticky comment: HTTP {exc.code}"
            )
    except (URLError, OSError) as exc:
        print(
            f"::warning title=Evidence Gate::"
            f"Failed to post sticky comment: {exc}"
        )


def _get_pr_context() -> tuple[str, str, int] | None:
    """Extract PR context from GitHub Actions environment.

    Reads GITHUB_EVENT_PATH JSON and GITHUB_REPOSITORY.

    Returns:
        (owner, repo, pr_number) tuple, or None if not in PR context.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()

    if not event_path or not repository:
        return None

    try:
        with open(event_path, encoding="utf-8") as f:
            event = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return None

    pr_number = pr.get("number")
    if not isinstance(pr_number, int):
        return None

    parts = repository.split("/", 1)
    if len(parts) != 2:
        return None

    owner, repo = parts
    return (owner, repo, pr_number)
