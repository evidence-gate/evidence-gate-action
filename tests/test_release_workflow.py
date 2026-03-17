"""Tests for .github/workflows/release.yml (QUAL-01).

Verifies:
- release.yml exists and has correct trigger configuration
- Semver validation is present
- Force-push of floating major tag is implemented
- Correct permissions are set

All tests should be GREEN immediately since release.yml is already correct.
"""

from __future__ import annotations

from pathlib import Path


# Locate release.yml relative to this test file
_RELEASE_YML = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


class TestReleaseWorkflow:
    """QUAL-01: release.yml content verification tests."""

    def test_release_workflow_file_exists(self) -> None:
        """release.yml exists in .github/workflows/."""
        assert _RELEASE_YML.exists(), f"release.yml not found at {_RELEASE_YML}"

    def test_release_workflow_trigger_is_release_published(self) -> None:
        """release.yml triggers on release published event."""
        content = _RELEASE_YML.read_text()
        assert "types: [published]" in content
        assert "release:" in content

    def test_release_workflow_has_contents_write_permission(self) -> None:
        """release.yml has contents: write permission for tag pushing."""
        content = _RELEASE_YML.read_text()
        assert "contents: write" in content

    def test_release_workflow_validates_semver(self) -> None:
        """release.yml contains semver validation regex pattern."""
        content = _RELEASE_YML.read_text()
        assert "^v[0-9]" in content

    def test_release_workflow_force_pushes_major_tag(self) -> None:
        """release.yml force-pushes the floating major tag."""
        content = _RELEASE_YML.read_text()
        assert "git push origin" in content
        assert "--force" in content
