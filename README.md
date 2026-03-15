# Evidence Gate

**Run quality gates in your CI/CD pipeline.** Verify evidence files, enforce thresholds, and optionally integrate with Evidence Gate SaaS for Blind Gate evaluation, Quality State tracking, and remediation workflows.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Evidence%20Gate-green.svg?logo=github)](https://github.com/marketplace/actions/evidence-gate)

## Quick Start

Add this step to any GitHub Actions workflow:

```yaml
- uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "test_coverage"
    phase_id: "testing"
    evidence_files: "coverage.json"
```

The action evaluates `coverage.json` as test coverage evidence. If the evaluation fails, the step exits non-zero and your workflow stops.

## How It Works

Evidence Gate operates in three modes depending on your configuration:

| Mode | Config | What It Does |
|------|--------|-------------|
| **Free** | No `api_key` | Client-side evaluation: file existence, JSON validation, schema checks, numeric thresholds |
| **Pro** | `api_key` set | Full SaaS evaluation via Evidence Gate API: Blind Gate, Quality State, Remediation |
| **Enterprise** | `api_key` + custom `api_base` | Self-hosted server with the same Pro features in your own infrastructure |

Free mode requires **zero external dependencies** -- all checks run locally using Python stdlib. Pro and Enterprise modes call the Evidence Gate API for advanced evaluation features.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `gate_type` | **Yes** | -- | Gate type to evaluate (e.g., `test_coverage`, `security`, `build`, `skill`) |
| `phase_id` | **Yes** | -- | Phase identifier (e.g., `build`, `test`, `deploy`, `1a`, `2b`) |
| `evidence_files` | No | `""` | Comma-separated list of evidence file paths to validate |
| `api_key` | No | `""` | Evidence Gate API key. Omit for Free mode. Required for Pro/Enterprise features |
| `api_base` | No | `https://api.evidence-gate.dev` | API base URL. Change for self-hosted Enterprise deployments |
| `dashboard_base_url` | No | `""` | Dashboard base URL for run/evidence deep links |
| `evidence_url` | No | `""` | Explicit evidence deep link URL |

## Outputs

| Output | Description |
|--------|-------------|
| `passed` | Gate result: `true` or `false` |
| `mode` | Detected operational mode: `free`, `pro`, or `enterprise` |
| `run_id` | Pipeline run ID |
| `major_issue_count` | Number of detected issues |
| `trace_url` | Langfuse trace URL (Pro/Enterprise only) |
| `evidence_url` | Evidence detail URL |
| `dashboard_url` | Supplemental dashboard URL |
| `github_run_url` | GitHub Actions run URL for this workflow execution |

## Examples

### Example 1: Test Coverage Gate (Free Mode)

No API key needed. Evaluates test coverage evidence from your CI pipeline:

```yaml
name: Quality Gate
on: [pull_request]

permissions:
  contents: read
  checks: write

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
```

### Example 2: Full Evaluation with Pro Mode

Enables Blind Gate, Quality State tracking, and remediation workflows:

```yaml
name: Quality Gate (Pro)
on: [pull_request]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "skill"
          phase_id: "2b"
          evidence_files: "coverage.json,test-results.json"
          api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}
```

### Example 3: Self-hosted Enterprise Mode

Point to your own Evidence Gate server:

```yaml
name: Quality Gate (Enterprise)
on: [pull_request]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "security"
          phase_id: "deploy"
          evidence_files: "security-scan.json"
          api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}
          api_base: "https://evidence-gate.internal.example.com"
```

## Free vs Pro

| Feature | Free | Pro / Enterprise |
|---------|:----:|:----------------:|
| Gate evaluations/month | 100 | 5,000+ |
| API calls/month | 1,000 | 50,000+ |
| All 25 gate types | Yes | Yes |
| SARIF output | Yes | Yes |
| GitHub Check Runs | Yes | Yes |
| Wave evaluation | Yes | Yes |
| SHA-256 integrity hashing | Yes | Yes |
| Blind Gate evaluation | -- | Yes |
| Evidence chain verification (L4) | -- | Yes |
| Quality State tracking | -- | Yes |
| Remediation workflows | -- | Yes |
| `GITHUB_STEP_SUMMARY` output | Yes | Yes |
| Fail-closed error handling | Yes | Yes |

When a Free mode user triggers a Pro-only gate type (e.g., `blind_gate`), the action does **not** fail. Instead, it emits a warning-level annotation with an upgrade link and passes the step.

## Troubleshooting

### "Gate type requires Pro plan" warning

You are using a Pro-only gate type (`blind_gate`, `quality_state`, `remediation`, `composite`, or `wave`) without an `api_key`. The action will pass with a warning. To use these gate types, add your API key:

```yaml
api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}
```

### Evidence file not found

The action checks that every path in `evidence_files` exists on disk. Common causes:

- **Relative paths**: Paths are resolved from the repository root (`$GITHUB_WORKSPACE`). Use relative paths like `coverage.json` or `reports/test-results.json`.
- **Missing build step**: Ensure your test/build step runs **before** the Evidence Gate step.
- **Glob patterns**: The `evidence_files` input does not support globs. List each file explicitly, separated by commas.

### API connection errors (Pro/Enterprise)

If the action fails with a network or API error:

1. **Check your API key**: Ensure `EVIDENCE_GATE_API_KEY` is set in repository secrets.
2. **Verify the API base URL**: For Enterprise, confirm `api_base` points to your server and is reachable from GitHub Actions runners.
3. **Check service status**: Visit [status.evidence-gate.dev](https://status.evidence-gate.dev) for SaaS availability.

The action uses **fail-closed** semantics: any unhandled error causes the step to exit non-zero. This prevents false passes when the evaluation service is unreachable.

## Links

- [Pro Plan & Pricing](https://evidence-gate.dev#pricing)
- [Self-hosted Deployment Guide](https://evidence-gate.dev#pricing)
- [Documentation](https://docs.evidence-gate.dev)
- [Changelog](CHANGELOG.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
