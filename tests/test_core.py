"""Tests for core module.

Verifies:
- Request format matches API spec (method, path, headers, body schema)
- Fail-closed behavior (missing API key, network errors, 5xx)
- SHA-256 evidence hash accuracy
- Evidence ref format
- New: _get_config() returns empty tuple when no api_key
"""

from __future__ import annotations

import hashlib
import json
import os
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from core import (
    CORE_SHA256,
    CORE_VERSION,
    EvidenceGateError,
    _get_config,
    build_evidence_ref,
    collect_evidence_refs,
    evaluate,
    evaluate_batch,
    fail_closed_main,
    generate_run_id,
)

from conftest import make_http_error, make_mock_response

# ---------------------------------------------------------------------------
# Version metadata
# ---------------------------------------------------------------------------


class TestVersionMetadata:
    """Verify version constants are set correctly."""

    def test_core_version_is_set(self) -> None:
        """CORE_VERSION is a semver string."""
        assert CORE_VERSION == "1.1.0"

    def test_core_sha256_is_64_hex(self) -> None:
        """CORE_SHA256 is a 64-character hex string."""
        assert len(CORE_SHA256) == 64
        assert all(c in "0123456789abcdef" for c in CORE_SHA256)


# ---------------------------------------------------------------------------
# Request format tests
# ---------------------------------------------------------------------------


class TestRequestFormat:
    """Verify requests match the Evidence Gate API contract."""

    @patch("core.urlopen")
    def test_evaluate_sends_correct_method_and_path(
        self, mock_urlopen: MagicMock
    ) -> None:
        """POST /v1/evaluate with correct method and URL."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(gate_type="skill", phase_id="1a")

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.method == "POST"
        assert req.full_url == "https://api.test.evidence-gate.dev/v1/evaluate"

    @patch("core.urlopen")
    def test_evaluate_sends_bearer_auth(self, mock_urlopen: MagicMock) -> None:
        """Request includes Bearer authorization header."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(gate_type="skill", phase_id="1a")

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer eg_test_contract_key"

    @patch("core.urlopen")
    def test_evaluate_sends_json_content_type(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Request includes application/json content type."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(gate_type="skill", phase_id="1a")

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"

    @patch("core.urlopen")
    def test_evaluate_body_has_required_fields(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Request body contains gate_type and phase_id."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(gate_type="skill", phase_id="1a", run_id="test-run")

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["gate_type"] == "skill"
        assert body["phase_id"] == "1a"
        assert body["run_id"] == "test-run"

    @patch("core.urlopen")
    def test_evaluate_body_omits_optional_none_fields(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Optional fields are omitted when None."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(gate_type="skill", phase_id="1a")

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "run_id" not in body
        assert "github_run_url" not in body
        assert "evidence_url" not in body
        assert "checks" not in body
        assert "evidence" not in body

    @patch("core.urlopen")
    def test_evaluate_body_includes_link_fields(
        self, mock_urlopen: MagicMock
    ) -> None:
        """GitHub/Langfuse link fields should be forwarded when provided."""
        mock_urlopen.return_value = make_mock_response({"passed": True})

        evaluate(
            gate_type="skill",
            phase_id="1a",
            run_id="test-run",
            github_run_url="https://github.com/org/repo/actions/runs/1",
            evidence_url="https://dashboard.example.com?run_id=test-run",
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["github_run_url"] == "https://github.com/org/repo/actions/runs/1"
        assert body["evidence_url"] == "https://dashboard.example.com?run_id=test-run"

    @patch("core.urlopen")
    def test_batch_evaluate_sends_correct_path(
        self, mock_urlopen: MagicMock
    ) -> None:
        """POST /v1/evaluate/batch with correct URL."""
        mock_urlopen.return_value = make_mock_response({"results": []})

        evaluate_batch(
            [{"gate_type": "skill", "phase_id": "1a"}],
            run_id="batch-run",
        )

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://api.test.evidence-gate.dev/v1/evaluate/batch"
        body = json.loads(req.data)
        assert "evaluations" in body
        assert body["run_id"] == "batch-run"
        assert body["fail_fast"] is False

    @patch("core.urlopen")
    def test_batch_evaluate_includes_optional_links(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Batch request should include optional GitHub/evidence links."""
        mock_urlopen.return_value = make_mock_response({"results": []})

        evaluate_batch(
            [{"gate_type": "skill", "phase_id": "1a"}],
            run_id="batch-run",
            github_run_url="https://github.com/org/repo/actions/runs/1",
            evidence_url="https://dashboard.example.com?run_id=batch-run",
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["github_run_url"] == "https://github.com/org/repo/actions/runs/1"
        assert body["evidence_url"] == "https://dashboard.example.com?run_id=batch-run"


# ---------------------------------------------------------------------------
# Fail-closed behavior
# ---------------------------------------------------------------------------


class TestFailClosed:
    """Verify fail-closed semantics for all error conditions."""

    def test_get_config_returns_empty_when_no_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_config() returns ('', '') when EG_API_KEY is not set."""
        monkeypatch.delenv("EG_API_KEY")
        result = _get_config()
        assert result == ("", "")

    def test_post_raises_when_no_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_post (via evaluate) raises EvidenceGateError when no api_key."""
        monkeypatch.delenv("EG_API_KEY")
        with pytest.raises(EvidenceGateError, match="EG_API_KEY"):
            evaluate(gate_type="skill", phase_id="1a")

    @patch("core.urlopen")
    def test_http_error_raises(self, mock_urlopen: MagicMock) -> None:
        """HTTP error raises EvidenceGateError with status code."""
        mock_urlopen.side_effect = make_http_error(500)
        with pytest.raises(EvidenceGateError, match="500"):
            evaluate(gate_type="skill", phase_id="1a")

    @patch("core.urlopen")
    def test_network_error_raises(self, mock_urlopen: MagicMock) -> None:
        """Network error raises EvidenceGateError."""
        mock_urlopen.side_effect = URLError("Connection refused")
        with pytest.raises(EvidenceGateError, match="Network error"):
            evaluate(gate_type="skill", phase_id="1a")

    @patch("core.urlopen")
    def test_unexpected_error_raises(self, mock_urlopen: MagicMock) -> None:
        """Unexpected error raises EvidenceGateError."""
        mock_urlopen.side_effect = RuntimeError("unexpected")
        with pytest.raises(EvidenceGateError, match="Unexpected error"):
            evaluate(gate_type="skill", phase_id="1a")

    def test_fail_closed_main_exits_on_failure(self) -> None:
        """fail_closed_main exits with code 1 on failed result."""
        with pytest.raises(SystemExit) as exc_info:
            fail_closed_main(lambda: {"passed": False})
        assert exc_info.value.code == 1

    def test_fail_closed_main_exits_on_exception(self) -> None:
        """fail_closed_main exits with code 1 on exception."""

        def raise_error() -> None:
            raise EvidenceGateError("test error")

        with pytest.raises(SystemExit) as exc_info:
            fail_closed_main(raise_error)
        assert exc_info.value.code == 1

    def test_fail_closed_main_passes_on_success(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """fail_closed_main does not exit on passed result."""
        fail_closed_main(lambda: {"passed": True})
        captured = capsys.readouterr()
        assert "PASSED" in captured.out


# ---------------------------------------------------------------------------
# SHA-256 evidence hashing
# ---------------------------------------------------------------------------


class TestEvidenceHashing:
    """Verify SHA-256 hash computation accuracy and EvidenceRef schema compliance."""

    def test_build_evidence_ref_computes_correct_sha256(
        self, evidence_file: str
    ) -> None:
        """SHA-256 hash matches manual computation."""
        ref = build_evidence_ref(evidence_file)

        with open(evidence_file, "rb") as f:
            expected_hash = hashlib.sha256(f.read()).hexdigest()

        assert ref["sha256"] == expected_hash
        assert len(ref["sha256"]) == 64

    def test_build_evidence_ref_includes_size(self, evidence_file: str) -> None:
        """Evidence ref includes correct file size."""
        ref = build_evidence_ref(evidence_file)
        actual_size = os.path.getsize(evidence_file)
        assert ref["size_bytes"] == actual_size

    def test_build_evidence_ref_includes_abs_path(
        self, evidence_file: str
    ) -> None:
        """Evidence ref 'path' field includes absolute file path."""
        ref = build_evidence_ref(evidence_file)
        assert os.path.isabs(ref["path"])

    def test_build_evidence_ref_schema_matches_evidence_ref_model(
        self, evidence_file: str
    ) -> None:
        """Evidence ref dict is compatible with EvidenceRef Pydantic model."""
        ref = build_evidence_ref(evidence_file)

        assert "ref" in ref
        assert "path" in ref
        assert "sha256" in ref
        assert "exists" in ref
        assert "loaded_at" in ref

        assert ref["ref"] == os.path.basename(evidence_file)
        assert ref["exists"] is True
        assert "T" in ref["loaded_at"]  # ISO 8601 format

    def test_build_evidence_ref_missing_file_raises(self) -> None:
        """Non-existent file raises EvidenceGateError."""
        with pytest.raises(EvidenceGateError, match="not found"):
            build_evidence_ref("/nonexistent/file.json")

    def test_collect_evidence_refs_skips_missing(
        self, evidence_file: str
    ) -> None:
        """collect_evidence_refs skips non-existent files."""
        refs = collect_evidence_refs([evidence_file, "/nonexistent/file.json"])
        assert len(refs) == 1
        assert refs[0]["sha256"] is not None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class TestUtilities:
    """Test utility functions."""

    def test_generate_run_id_format(self) -> None:
        """generate_run_id returns UUID4 string."""
        run_id = generate_run_id()
        assert len(run_id) == 36
        assert run_id.count("-") == 4
