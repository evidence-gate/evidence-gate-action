# Evidence Gate Action

**AI writes your code and your tests. How do you prove quality to an auditor?**

When AI agents (Copilot, Claude, Cursor) generate both production code and tests, traditional CI/CD gates lose their meaning. An LLM told to "achieve 80% coverage" will produce tests that hit exactly 80.1% — a number that satisfies the metric but proves nothing about quality. Worse, when an incident occurs, you cannot show auditors verifiable evidence that quality controls were genuinely enforced.

Evidence Gate Action records every gate evaluation as **tamper-proof evidence** — from simple declarations (L1) to SHA-256 hash chains (L4) that any auditor can independently verify. Combined with **Blind Gates** — evaluation criteria hidden from the AI — your pipeline produces audit-grade proof that quality was built in, not gamed.

The evidence model is designed with global regulatory frameworks in mind — SOC 2, ISO 27001, the EU AI Act's transparency requirements, Japan's AI guidelines, and similar standards that increasingly demand verifiable records of how AI-generated code was validated. Evidence Gate does not yet cover every requirement of every framework, and regulations themselves are still evolving. But the core architecture — immutable evidence chains, independent verifiability, fail-closed semantics — is built to grow with these standards, not retrofit compliance after the fact.

This is an open-source project under active development. We are shipping early because the problem is urgent: AI-driven development is already here, and audit-grade tooling should not wait for perfection. We welcome feedback, contributions, and real-world use cases to shape Evidence Gate into the standard that teams and regulators can rely on together.

- **Tamper-proof evidence chains** — every evaluation produces verifiable records (L1–L4) for compliance and audit readiness
- **Blind Gates** (Pro) — hidden criteria that AI agents cannot see, reverse-engineer, or optimize against
- **Fail-closed by default** — missing evidence or unreachable API means FAIL, never a silent pass
- **25 gate types** — test coverage, security, architecture, compliance, release readiness, and more
- **Built for AI-driven development** — quality gates designed for a world where LLMs write code and tests

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Evidence%20Gate-blue.svg?logo=github)](https://github.com/marketplace/actions/evidence-gate-action)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## Quick Start

Add this step to any GitHub Actions workflow:

```yaml
- uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "test_coverage"
    phase_id: "testing"
    evidence_files: "coverage.json"
```

That's it. If the evidence is valid, the step passes. If not, it fails — no silent passes, no warnings to ignore.

## Permissions

Evidence Gate requires different permissions depending on which features you use:

| Feature | `contents` | `checks` | `issues` | `id-token` |
|---------|:----------:|:--------:|:--------:|:----------:|
| Basic gate evaluation | `read` | — | — | — |
| Check Run annotations | `read` | `write` | — | — |
| Issue creation on failure | `read` | — | `write` | — |
| OIDC keyless auth (Pro) | `read` | — | — | `write` |

A typical workflow with Check Run support uses per-job permissions:

```yaml
jobs:
  gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
```

## Inputs

| Input | Required | Default | Description |
|-------|:--------:|---------|-------------|
| `gate_type` | **Yes** | — | Gate type to evaluate (e.g., `test_coverage`, `security`, `build`, `skill`) |
| `phase_id` | **Yes** | — | Phase identifier (e.g., `build`, `test`, `deploy`) |
| `evidence_files` | No | `""` | Comma-separated list of evidence file paths to validate |
| `api_key` | No | `""` | Evidence Gate API key. Omit for Free mode |
| `api_base` | No | `https://api.evidence-gate.dev` | API base URL. Change for self-hosted Enterprise |
| `dashboard_base_url` | No | `""` | Dashboard base URL for deep links |
| `evidence_url` | No | `""` | Explicit evidence deep link URL |

## Outputs

| Output | Description |
|--------|-------------|
| `passed` | Gate result: `true` or `false` |
| `mode` | Detected mode: `free`, `pro`, or `enterprise` |
| `run_id` | Pipeline run ID |
| `major_issue_count` | Number of detected issues |
| `trace_url` | Trace URL (Pro/Enterprise) |
| `evidence_url` | Evidence detail URL |
| `dashboard_url` | Dashboard URL |
| `github_run_url` | GitHub Actions run URL |

## Using Gate Results in Downstream Steps

Gate outputs can drive conditional logic in your workflow:

```yaml
- name: Evidence Gate
  id: gate
  uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "test_coverage"
    phase_id: "testing"
    evidence_files: "coverage.json"

- name: Deploy (only if gate passed)
  if: steps.gate.outputs.passed == 'true'
  run: ./deploy.sh
```

## Workflow Recipes

Complete, copy-paste workflow files for common use cases. Each recipe includes the required `permissions` block.

### Recipe 1: Test Coverage Gate (Free Mode)

No API key needed. Validates that your test suite produced coverage evidence:

```yaml
name: Test Coverage Gate
on: [pull_request]

jobs:
  coverage-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests with coverage
        run: pytest --cov --cov-report=json

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
```

### Recipe 2: Security Scan Gate

Evaluate security scan results after running a SAST/DAST tool:

```yaml
name: Security Gate
on: [pull_request]

jobs:
  security-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run security scan
        run: bandit -r src/ -f json -o security-report.json || true

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "security"
          phase_id: "security-scan"
          evidence_files: "security-report.json"
```

### Recipe 3: Build Artifact Gate

Verify that your build step produced the expected output files:

```yaml
name: Build Gate
on: [push]

jobs:
  build-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: npm run build

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "build"
          phase_id: "build"
          evidence_files: "dist/index.js,dist/index.css"
```

### Recipe 4: Multi-Gate Pipeline

Run multiple gates in sequence — deploy only if all pass:

```yaml
name: Multi-Gate Pipeline
on: [pull_request]

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Run security scan
        run: bandit -r src/ -f json -o security-report.json || true

      - name: Coverage Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"

      - name: Security Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "security"
          phase_id: "security"
          evidence_files: "security-report.json"
```

### Recipe 5: Pro Mode with Blind Gate

Blind Gates hide evaluation criteria from the pipeline — the AI that generated the code cannot see or game the thresholds:

```yaml
name: Blind Gate Evaluation
on: [pull_request]

jobs:
  blind-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Evidence Gate (Blind)
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "skill"
          phase_id: "quality-check"
          evidence_files: "coverage.json"
          api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}
```

### Recipe 6: Scheduled Quality Assessment

Run a weekly quality check against your main branch:

```yaml
name: Weekly Quality Assessment
on:
  schedule:
    - cron: "0 9 * * 1"  # Every Monday at 09:00 UTC

jobs:
  weekly-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run full test suite
        run: pytest --cov --cov-report=json

      - name: Evidence Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "release_readiness"
          phase_id: "weekly-audit"
          evidence_files: "coverage.json"
```

## How It Works

Evidence Gate operates in three modes depending on your configuration:

| Mode | Config | What It Does |
|------|--------|-------------|
| **Free** | No `api_key` | Client-side evaluation: file existence, JSON validation, schema checks, numeric thresholds |
| **Pro** | `api_key` set | Full SaaS evaluation: Blind Gate, Quality State, evidence chains (L4), remediation |
| **Enterprise** | `api_key` + custom `api_base` | Self-hosted with the same Pro features in your own infrastructure |

Free mode requires **zero external dependencies** — all checks run locally. Pro and Enterprise modes call the Evidence Gate API for advanced features.

## Free vs Pro

| Feature | Free | Pro / Enterprise |
|---------|:----:|:----------------:|
| Gate evaluations/month | 100 | 5,000+ |
| All 25 gate types | Yes | Yes |
| SARIF output | Yes | Yes |
| GitHub Check Runs | Yes | Yes |
| SHA-256 integrity hashing | Yes | Yes |
| Fail-closed error handling | Yes | Yes |
| `GITHUB_STEP_SUMMARY` | Yes | Yes |
| Blind Gate evaluation | — | Yes |
| Evidence chain verification (L4) | — | Yes |
| Quality State tracking | — | Yes |
| Remediation workflows | — | Yes |

## Troubleshooting

### "Gate type requires Pro plan" warning

You are using a Pro-only gate type without an `api_key`. Add your API key:

```yaml
api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}
```

### Evidence file not found

- **Relative paths**: Paths are resolved from `$GITHUB_WORKSPACE`. Use `coverage.json`, not `/home/runner/work/.../coverage.json`.
- **Missing build step**: Ensure your test/build step runs **before** the Evidence Gate step.
- **No glob support**: List each file explicitly, separated by commas.

### API connection errors (Pro/Enterprise)

1. **Check your API key**: Ensure `EVIDENCE_GATE_API_KEY` is set in repository secrets.
2. **Verify the API base URL**: For Enterprise, confirm `api_base` is reachable from GitHub Actions runners.

The action uses **fail-closed** semantics: any unhandled error exits non-zero. This prevents false passes when the evaluation service is unreachable.

## Links

- [Landing Page & Pricing](https://evidence-gate.dev)
- [Changelog](CHANGELOG.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
