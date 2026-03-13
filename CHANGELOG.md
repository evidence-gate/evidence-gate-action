# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
