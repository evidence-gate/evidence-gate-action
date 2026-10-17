# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **Breaking:** unknown `gate_type` values now fail in Free mode (they previously passed). Release this as a new minor or major tag. Do not move the existing `v1` tag.

### Fixed

- **Fail-closed in Free mode**: a gate with no evidence files, an empty evidence file (`{}`, `[]`, `null`), or an unknown `gate_type` now FAILS instead of silently passing.
- `version` input no longer installs the unpublished `evidence-gate-evaluator` PyPI package (which made any non-`latest` value fail and was a dependency-confusion risk). The input is kept as a deprecated no-op.
- `pyyaml` is pinned (`6.0.3`); `run:` steps no longer interpolate `${{ inputs.* }}` inline.
- ruff clean.

## [1.0.0] - 2026-03-13

### Added

- Initial release of Evidence Gate GitHub Action
- Three operational modes: Free (client-side), Pro (SaaS), Enterprise (self-hosted)
- Free mode: file existence, JSON validation, schema checks, numeric thresholds, SHA-256 integrity
- Pro/Enterprise mode: Blind Gate, Quality State, Remediation, Composite gates, Wave evaluation
- `GITHUB_STEP_SUMMARY` output with detailed gate results
- Workflow annotations (warnings for Pro-only gate types in Free mode)
- Fail-closed error handling
- Comprehensive input/output interface via `action.yml`
