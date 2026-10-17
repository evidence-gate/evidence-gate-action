# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2.0.1] - 2026-10-17

### Changed

- The hosted API (Pro) is not launched yet: the Free-mode notice for Pro-only gate types now says Pro is coming soon (no upgrade/sign-up prompt), and the step-summary heading is "Pro (hosted API) coming soon". Behaviour is unchanged (warning annotation, `passed=true`, `upsell=true`). README and `action.yml` descriptions mark Pro/hosted API as coming soon. (#5)

### Fixed

- `integration.yml` is valid again (GitHub had rejected it before any job started); the `on` key in workflows is quoted, and the Python sources pass `ruff format --check`. No change to evaluation behaviour. (#4)
- `pyproject.toml` / `uv.lock` project version now matches the release (was `1.0.0`).

## [2.0.0] - 2026-10-17

### Changed

- **Breaking:** unknown `gate_type` values now fail in Free mode (they previously passed). Released as a new major version (`v2.0.0`, floating `v2`); the existing `v1` tag was not moved.

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

[Unreleased]: https://github.com/evidence-gate/evidence-gate-action/compare/v2.0.1...HEAD
[2.0.1]: https://github.com/evidence-gate/evidence-gate-action/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/evidence-gate/evidence-gate-action/compare/v1.1.0...v2.0.0
