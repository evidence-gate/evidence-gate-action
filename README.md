**English** | [日本語](README.ja.md)

# Evidence Gate Action

Fail-closed quality gates for GitHub Actions with verifiable evidence chains.

**AI writes your code and your tests. How do you prove quality to an auditor?** Evidence Gate evaluates pipeline artifacts against quality criteria, blocks merges that fail, and records every evaluation as tamper-proof evidence (L1 declarations through L4 SHA-256 hash chains). **Blind Gates** hide the pass/fail criteria, making it harder for AI agents to reverse-engineer or game them.

This is a CI/CD quality gate enforcement tool -- not an AI code reviewer and not an AI agent guardrail. Multiple unrelated projects share the name "Evidence Gate" on GitHub -- this one enforces quality in your CI/CD pipeline.

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

If the evidence is valid, the step passes. If the evidence is missing or invalid, the step fails -- no silent passes.

## What You Need

| | Free | Pro / Enterprise |
|---|---|---|
| **API key** | Not required | `api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}` |
| **What runs** | Local validation (file existence, JSON schema, numeric thresholds) | Hosted evaluation with Blind Gates, evidence chains (L4), quality state |
| **Evaluations/month** | 100 | 5,000+ |
| **Best for** | Open-source projects, basic evidence checks | Teams needing audit trails, compliance workflows, AI-driven pipelines |

Enterprise uses the same action with a custom `api_base` for self-hosted deployment.

## When to Use This

- **AI-assisted development** -- when LLMs generate both code and tests, traditional coverage metrics prove nothing; Blind Gates are a structural approach to this problem
- **Audit & compliance** -- keep verifiable records of every quality gate decision (SOC 2, ISO 27001, EU AI Act, Japan AI guidelines)
- **Deployment gating** -- block deployment unless quality evidence is present and valid
- **Multi-gate pipelines** -- run coverage, security, and build gates in sequence with a single action

## Permissions

| Feature | `contents` | `checks` | `id-token` | `pull-requests` |
|---------|:----------:|:--------:|:----------:|:---------------:|
| Basic gate evaluation | `read` | -- | -- | -- |
| Check Run annotations | `read` | `write` | -- | -- |
| OIDC keyless auth (Pro) | `read` | -- | `write` | -- |
| Sticky PR comments | `read` | -- | -- | `write` |

A typical workflow with Check Run support:

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
| `gate_type` | No | `""` | Gate type to evaluate (e.g., `test_coverage`, `security`, `build`, `skill`). Optional if `.evidencegate.yml` is present |
| `phase_id` | No | `""` | Phase identifier (e.g., `build`, `test`, `deploy`). Optional if `.evidencegate.yml` is present |
| `evidence_files` | No | `""` | Comma-separated list of evidence file paths |
| `api_key` | No | `""` | Evidence Gate API key. Omit for Free mode |
| `api_base` | No | `https://api.evidence-gate.dev` | API base URL. Change for self-hosted Enterprise |
| `mode` | No | `enforce` | `enforce` (fail on gate failure) or `observe` (log results without blocking) |
| `gate_preset` | No | `""` | Named gate bundle (`web-app-baseline`, `enterprise-compliance`, `api-service`, `supply-chain`). Runs all gates in the preset |
| `sticky_comment` | No | `false` | Aggregate results into a single updating PR comment. Requires `pull-requests: write` |
| `debug` | No | `false` | Enable verbose diagnostic output |
| `version` | No | `latest` | Evaluator version to install (e.g., `1.0.0`). `latest` uses stdlib-only evaluation |
| `dashboard_base_url` | No | `""` | Dashboard base URL for deep links |
| `evidence_url` | No | `""` | Explicit evidence deep link URL |

## Outputs

| Output | Description |
|--------|-------------|
| `passed` | Gate result: `true` or `false` |
| `mode` | Detected mode: `free`, `pro`, or `enterprise` |
| `run_id` | Pipeline run ID |
| `major_issue_count` | Number of detected issues |
| `observe_would_pass` | In observe mode, whether the gate would have passed. Only set when `mode: observe` |
| `missing_evidence` | JSON array of missing evidence items `[{code, message, field_path}]` |
| `suggested_actions` | Human-readable repair steps for failed gates |
| `retry_prompt` | Machine-readable repair instructions for AI agents. Empty string when gate passes |
| `json_output` | Full evaluation result as JSON (use `fromJson()` to parse) |
| `trace_url` | Trace URL (Pro/Enterprise) |
| `evidence_url` | Evidence detail URL |
| `dashboard_url` | Dashboard URL |
| `github_run_url` | GitHub Actions run URL |

## Using Gate Results in Downstream Steps

```yaml
- name: Evidence Gate
  id: gate
  uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "test_coverage"
    phase_id: "testing"
    evidence_files: "coverage.json"

- name: Handle failure
  if: failure()
  run: |
    echo "Missing: ${{ steps.gate.outputs.missing_evidence }}"
    echo "Fix: ${{ steps.gate.outputs.suggested_actions }}"

- name: Deploy (only if gate passed)
  if: steps.gate.outputs.passed == 'true'
  run: ./deploy.sh
```

## Solutions

Complete, copy-paste workflow files. Each recipe includes the required `permissions` block.

### Enforce test coverage on every PR

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

### Block PRs without a security scan

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

### Require build artifacts before deploy

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

### Run multiple quality checks in sequence

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

### Use a curated gate bundle (zero decision paralysis)

Run a curated bundle of gates with a single input. Four presets are available: `web-app-baseline`, `enterprise-compliance`, `api-service`, `supply-chain`.

```yaml
name: Preset Gate
on: [pull_request]

jobs:
  preset-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Evidence Gate (Web App Baseline)
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_preset: "web-app-baseline"
          phase_id: "quality-check"
          evidence_files: "coverage.json,security-report.json"
```

### Measure gate pass rates before enforcing

Evaluate all gates without failing the workflow. Use this to measure gate pass rates before enforcing:

```yaml
name: Observe Mode
on: [pull_request]

jobs:
  observe:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Evidence Gate (Observe)
        id: gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
          mode: "observe"

      - name: Check results
        run: echo "Would have passed: ${{ steps.gate.outputs.observe_would_pass }}"
```

### Prevent AI agents from gaming your quality metrics

Blind Gates keep evaluation criteria outside the pipeline -- the AI that generated the code cannot see or game the thresholds. The `skill` gate type is used here because skill evaluations are the primary use case for hidden criteria:

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

### Aggregate all gate results in one PR comment

Aggregate multiple gate results into a single, auto-updating PR comment:

```yaml
name: Quality Gates with Sticky Comment
on: [pull_request]

jobs:
  gates:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: pytest --cov --cov-report=json

      - name: Coverage Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
          sticky_comment: "true"

      - name: Build Gate
        uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "build"
          phase_id: "build"
          evidence_files: "dist/index.js"
          sticky_comment: "true"
```

### Configure from a repo file (no workflow inputs needed)

Add `.evidencegate.yml` to your repository root and run the action with zero inputs:

```yaml
# .evidencegate.yml
gate_type: test_coverage
phase_id: testing
mode: enforce
evidence_files:
  - coverage.json
```

```yaml
# .github/workflows/gate.yml — no inputs needed
name: Evidence Gate
on: [pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4
      - run: pytest --cov --cov-report=json
      - uses: evidence-gate/evidence-gate-action@v1
```

### Validate SBOM and build provenance

Verify supply chain security artifacts as part of your release pipeline:

```yaml
name: Supply Chain Gate
on: [push]
jobs:
  supply-chain:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
    steps:
      - uses: actions/checkout@v4
      - uses: evidence-gate/evidence-gate-action@v1
        with:
          gate_type: "sbom"
          phase_id: "release"
          evidence_files: "sbom.cdx.json"
```

Use `gate_type: "provenance"` for build provenance attestation. Both gate types are available in Free mode.

## Visual Proof

<!-- TODO: replace with screenshot once action runs in a live GitHub Actions environment -->

### Check Run Annotations

When a gate fails, findings appear inline in the **Files Changed** tab of your PR:

```
::error file=src/app.py,line=1::test_coverage gate FAILED — coverage 72% < threshold 80%
::warning file=coverage.json::Evidence file found but threshold not met
::notice ::Suggested action: increase test coverage by 8 percentage points
```

Annotations are visible without leaving GitHub. `::error` creates a blocking review, `::warning` flags the file, `::notice` adds context.

<!-- TODO: replace with screenshot -->

### Job Summary

Every run appends a structured summary to `GITHUB_STEP_SUMMARY` (visible in the Actions UI under the Summary tab):

| Signal | Gate | Result | Details |
|--------|------|--------|---------|
| CRITICAL | test_coverage | FAILED | coverage 72% < 80% threshold |
| WARNING | security | WARN | 2 medium-severity findings |
| INFO | build | PASSED | dist/index.js present (124 KB) |

Results are sorted by signal hierarchy: Critical > Warning > Info. Use this view to triage failures without digging through logs.

## Migrating from v1.0.x to v1.1.0

v1.1.0 is **backwards-compatible** for most users. Existing workflows continue to work without changes.

### The one breaking change: API base URL

If you use self-hosted Enterprise with a custom `api_base`, no action is needed -- your custom URL overrides the default.

If you previously relied on the **default URL** `https://api.evidence-gate.com`, it has changed to `https://api.evidence-gate.dev`. Free and Pro users are unaffected -- the default URL change happens automatically.

### Before / After

**Before (v1.0.x) -- still works in v1.1.0:**

```yaml
- uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "test_coverage"   # was required; now optional if config file present
    phase_id: "testing"          # was required; now optional if config file present
    evidence_files: "coverage.json"
```

**After (v1.1.0) with config file (optional upgrade):**

```yaml
# .evidencegate.yml in your repo root
gate_type: test_coverage
phase_id: testing
evidence_files:
  - coverage.json

# workflow — zero inputs needed
- uses: evidence-gate/evidence-gate-action@v1
```

### New Capabilities in v1.1.0

| Feature | How to Use | Notes |
|---------|-----------|-------|
| Config file | Add `.evidencegate.yml` | Zero required inputs |
| Warn mode | `mode: warn` | Gate fails but step succeeds |
| Observe mode | `mode: observe` | Shadow run -- outputs `observe_would_pass` |
| Gate presets | `gate_preset: web-app-baseline` | Runs 4 gates at once |
| Sticky PR comment | `sticky_comment: true` | Single updating comment |
| AI repair contract | output `retry_prompt` | Machine-readable fix instructions for AI agents |
| SBOM gate | `gate_type: sbom` | CycloneDX/SPDX validation (Free) |
| Provenance gate | `gate_type: provenance` | Build attestation check (Free) |
| Check Run annotations | automatic | Findings appear inline in Files Changed tab |
| Signal-sorted Job Summary | automatic | Critical > Warning > Info |

### Migration Checklist

- [ ] Verify existing workflows still pass (most users: no action required)
- [ ] If using self-hosted Enterprise: confirm `api_base` URL is still correct
- [ ] Optional: add `.evidencegate.yml` to your repo for zero-input usage
- [ ] Optional: add `mode: warn` to non-critical gates for gradual rollout
- [ ] Optional: add `sticky_comment: true` to aggregate PR feedback

## Why This Exists

When AI agents (Copilot, Claude, Cursor) generate both production code and tests, traditional CI/CD gates lose their meaning. An LLM told to "achieve 80% coverage" will produce tests that hit exactly 80.1% -- a number that satisfies the metric but proves nothing about quality.

Evidence Gate addresses this with three design choices:

1. **Blind Gates** -- evaluation criteria are hidden from the pipeline, making it harder for AI agents to reverse-engineer or optimize against them. This is a structural approach to the gate-gaming problem in AI-driven development.

2. **Evidence Trust Levels** -- every evaluation is recorded at one of four trust levels:
   - **L1** Declaration -- the pipeline claims something happened
   - **L2** Attestation -- a third party confirms the claim
   - **L3** Verification -- the claim is independently reproducible
   - **L4** Hash Chain -- SHA-256 chain that any auditor can independently verify

3. **Fail-closed semantics** -- missing evidence, unreachable API, or evaluation errors mean FAIL, never a silent pass.

The evidence model is designed with global regulatory frameworks in mind -- SOC 2, ISO 27001, the EU AI Act's transparency requirements, Japan's AI guidelines, and similar standards that increasingly demand verifiable records of how AI-generated code was validated. Evidence Gate does not yet cover every requirement of every framework, and regulations are still evolving. But the core architecture -- immutable evidence chains, independent verifiability, fail-closed semantics -- is built to grow with these standards.

This is an open-source project under active development. We welcome feedback, contributions, and real-world use cases.

## Modes

| Mode | Config | What It Does |
|------|--------|-------------|
| **Free** | No `api_key` | Client-side evaluation: file existence, JSON validation, schema checks, numeric thresholds |
| **Pro** | `api_key` set | Full SaaS evaluation: Blind Gate, Quality State, evidence chains (L4), remediation |
| **Enterprise** | `api_key` + custom `api_base` | Self-hosted with the same Pro features in your own infrastructure |

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
| Observe mode | Yes | Yes |
| Gate presets | Yes | Yes |
| Sticky PR comments | Yes | Yes |
| Structured outputs (missing_evidence, suggested_actions) | Yes | Yes |
| Blind Gate evaluation | -- | Yes |
| Evidence chain verification (L4) | -- | Yes |
| Quality State tracking | -- | Yes |
| Remediation workflows | -- | Yes |

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
- [Documentation](https://evidence-gate.dev/docs/)
- [Changelog](CHANGELOG.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
