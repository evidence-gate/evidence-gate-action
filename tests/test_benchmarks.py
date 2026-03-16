"""Tests that BENCHMARKS.md exists and contains required sections."""
import pathlib

BENCHMARKS = pathlib.Path(__file__).parent.parent / "BENCHMARKS.md"


def test_benchmarks_file_exists():
    assert BENCHMARKS.exists(), "BENCHMARKS.md must exist at action repo root"


def test_benchmarks_sbom_section():
    text = BENCHMARKS.read_text()
    assert "sbom" in text.lower()


def test_benchmarks_provenance_section():
    text = BENCHMARKS.read_text()
    assert "provenance" in text.lower()


def test_benchmarks_limitations_section():
    text = BENCHMARKS.read_text()
    assert "limitation" in text.lower() or "known" in text.lower()
