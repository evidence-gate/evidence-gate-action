"""Workflow files must be valid YAML so GitHub Actions can start them."""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def test_workflow_files_parse_and_declare_triggers() -> None:
    paths = sorted(_WORKFLOWS.glob("*.yml"))
    assert paths, "expected workflow files"
    for path in paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict), path.name
        assert isinstance(document.get("name"), str) and document["name"], path.name
        # Quoted "on" stays a string. An unquoted on is YAML 1.1 boolean true,
        # which GitHub may not register as a trigger.
        assert "on" in document, path.name
        assert True not in document, path.name
        assert document["on"], path.name
