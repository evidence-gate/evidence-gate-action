"""Test fixtures -- mock HTTP layer for adapter core testing."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required EG_API_KEY for all tests by default.

    Individual tests can override or delete this as needed.
    """
    monkeypatch.setenv("EG_API_KEY", "eg_test_contract_key")
    monkeypatch.setenv("EG_API_BASE", "https://api.test.evidence-gate.com")


def make_mock_response(
    body: dict[str, Any],
    status: int = 200,
) -> MagicMock:
    """Create a mock urllib response."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.status = status
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def make_http_error(
    status: int,
    body: dict[str, Any] | None = None,
) -> HTTPError:
    """Create a mock HTTPError."""
    error_body = json.dumps(body or {"error": "test_error"}).encode("utf-8")
    from io import BytesIO

    err = HTTPError(
        url="https://api.test.evidence-gate.com/v1/evaluate",
        code=status,
        msg=f"HTTP {status}",
        hdrs={},  # type: ignore[arg-type]
        fp=BytesIO(error_body),
    )
    return err


@pytest.fixture()
def evidence_file(tmp_path: Any) -> str:
    """Create a temporary evidence file for testing."""
    file_path = tmp_path / "test_evidence.json"
    file_path.write_text('{"test": "data", "passed": true}')
    return str(file_path)


@pytest.fixture()
def evidence_dir(tmp_path: Any) -> Any:
    """Create a temporary directory with various evidence files for Free mode tests."""
    # Valid JSON
    valid = tmp_path / "valid.json"
    valid.write_text('{"name": "test", "score": 85, "passed": true}')

    # Invalid JSON
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken json")

    # Empty file
    empty = tmp_path / "empty.json"
    empty.write_text("")

    # Nested object
    nested = tmp_path / "nested.json"
    nested.write_text(json.dumps({
        "metadata": {
            "version": "1.0",
            "timestamp": "2026-01-01T00:00:00Z",
        },
        "results": [
            {"name": "test1", "passed": True},
            {"name": "test2", "passed": False},
        ],
        "score": 75,
    }))

    return tmp_path
