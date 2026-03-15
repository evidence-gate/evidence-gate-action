"""Tests for sticky_comment.py -- PR comment aggregation.

Verifies:
- find_existing_comment finds/misses MARKER in comments
- _build_comment_body builds correct markdown for pass/fail/observe
- post_sticky_comment creates new or updates existing comments
- post_sticky_comment handles 403 and other HTTP errors gracefully
- _get_pr_context extracts PR info from event JSON
- _get_pr_context returns None for non-PR events
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from sticky_comment import (
    MARKER,
    _build_comment_body,
    _get_pr_context,
    find_existing_comment,
    post_sticky_comment,
)


class TestFindExistingComment:
    """Tests for find_existing_comment."""

    @patch("sticky_comment._github_api")
    def test_find_existing_comment_found(self, mock_api: MagicMock) -> None:
        """When a comment contains MARKER, return its id."""
        mock_api.return_value = [
            {"id": 100, "body": "Some other comment"},
            {"id": 200, "body": f"Results\n{MARKER}\n| Gate | Result |"},
            {"id": 300, "body": "Another comment"},
        ]
        result = find_existing_comment("owner", "repo", 42, "token123")
        assert result == 200

    @patch("sticky_comment._github_api")
    def test_find_existing_comment_not_found(self, mock_api: MagicMock) -> None:
        """When no comments contain MARKER, return None."""
        mock_api.return_value = [
            {"id": 100, "body": "Some comment"},
            {"id": 200, "body": "Another comment"},
        ]
        result = find_existing_comment("owner", "repo", 42, "token123")
        assert result is None

    @patch("sticky_comment._github_api")
    def test_find_existing_comment_empty_page(self, mock_api: MagicMock) -> None:
        """When no comments exist, return None."""
        mock_api.return_value = []
        result = find_existing_comment("owner", "repo", 42, "token123")
        assert result is None


class TestBuildCommentBody:
    """Tests for _build_comment_body."""

    def test_build_comment_body_pass(self) -> None:
        """Body contains MARKER, PASS status, and gate type."""
        results = [{"gate_type": "security", "passed": True}]
        body = _build_comment_body(results, observe=False)
        assert MARKER in body
        assert "PASS" in body
        assert "security" in body

    def test_build_comment_body_fail(self) -> None:
        """Body contains FAIL status for failed gate."""
        results = [{"gate_type": "build", "passed": False}]
        body = _build_comment_body(results, observe=False)
        assert "FAIL" in body

    def test_build_comment_body_observe(self) -> None:
        """Observe mode shows 'OBSERVE (would FAIL)' for failed gate."""
        results = [{"gate_type": "security", "passed": False}]
        body = _build_comment_body(results, observe=True)
        assert "OBSERVE (would FAIL)" in body


class TestPostStickyComment:
    """Tests for post_sticky_comment."""

    @patch("sticky_comment._github_api")
    @patch("sticky_comment.find_existing_comment", return_value=None)
    def test_post_sticky_comment_creates_new(
        self, mock_find: MagicMock, mock_api: MagicMock
    ) -> None:
        """When no existing comment, POST to create new."""
        results = [{"gate_type": "security", "passed": True}]
        post_sticky_comment("owner", "repo", 42, "token123", results, observe=False)
        # Should call _github_api with POST
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        assert call_args[0][0] == "POST"
        assert "/issues/42/comments" in call_args[0][1]

    @patch("sticky_comment._github_api")
    @patch("sticky_comment.find_existing_comment", return_value=999)
    def test_post_sticky_comment_updates_existing(
        self, mock_find: MagicMock, mock_api: MagicMock
    ) -> None:
        """When existing comment found, PATCH to update."""
        results = [{"gate_type": "build", "passed": True}]
        post_sticky_comment("owner", "repo", 42, "token123", results, observe=False)
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        assert call_args[0][0] == "PATCH"
        assert "/comments/999" in call_args[0][1]

    @patch("sticky_comment.find_existing_comment", return_value=None)
    @patch("sticky_comment._github_api")
    def test_post_sticky_comment_handles_403(
        self, mock_api: MagicMock, mock_find: MagicMock, capsys
    ) -> None:
        """HTTP 403 emits ::warning:: and does not raise."""
        mock_api.side_effect = HTTPError(
            url="https://api.github.com/test",
            code=403,
            msg="Forbidden",
            hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(b"forbidden"),
        )
        results = [{"gate_type": "security", "passed": True}]
        # Should NOT raise
        post_sticky_comment("owner", "repo", 42, "token123", results, observe=False)
        captured = capsys.readouterr()
        assert "::warning title=Evidence Gate::" in captured.out
        assert "pull-requests: write" in captured.out


class TestGetPrContext:
    """Tests for _get_pr_context."""

    def test_get_pr_context_from_event(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Extracts owner, repo, pr_number from event JSON."""
        event_data = {"pull_request": {"number": 7}}
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event_data))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "myorg/myrepo")

        result = _get_pr_context()
        assert result == ("myorg", "myrepo", 7)

    def test_get_pr_context_non_pr_event(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Returns None when event is not a pull_request."""
        event_data = {"action": "push", "ref": "refs/heads/main"}
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(event_data))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "myorg/myrepo")

        result = _get_pr_context()
        assert result is None
