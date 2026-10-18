**English** | [日本語](README.ja.md)

# Evidence Gate Action

Fail-closed quality gates for GitHub Actions. Free mode checks evidence files in CI.

**AI writes your code and your tests. How do you check the artifacts in CI?** Evidence Gate evaluates pipeline artifacts against quality criteria and blocks merges that fail. **Free mode (available now)** checks that evidence files exist, are valid JSON, and meet numeric thresholds, and records a SHA-256 digest of each file. That digest names the bytes that were checked. It is not signed, and it is not written to an external log.

**Blind Gate, L4 hash chains, Pro, and the hosted API are coming soon** (準備中). `api.evidence-gate.dev` is not launched, and API keys are not issued. A planned L4 record is `sha256(previous + evidence_hash)` with no key and no signature. That construction is **tamper-evident**: modifying a single record is detectable when the rest of the chain is left intact. It does not prevent a full-chain rewrite by someone with write access to the store.

This is a CI/CD quality gate enforcement tool -- not an AI code reviewer and not an AI agent guardrail. Multiple unrelated projects share the name "Evidence Gate" on GitHub -- this one enforces quality in your CI/CD pipeline.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Evidence%20Gate-blue.svg?logo=github)](https://github.com/marketplace/actions/evidence-gate-action)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## Quick Start

Add this step to any GitHub Actions workflow:

```yaml
- uses: evidence-gate/evidence-gate-action@v2
  with:
    gate_type: "test_coverage"
    phase_id: "testing"
    evidence_files: "coverage.json"
```

If the evidence is valid, the step passes. If the evidence is missing or invalid, the step fails -- no silent passes.

## What You Need

> **The hosted API (Pro) is coming soon.** Free mode (local evaluation, no API key) is available now. Pro/Enterprise API keys are not issued yet; `api.evidence-gate.dev` is not a working endpoint at this time.

| | Free (available now) | Pro / Enterprise (coming soon) |
|---|---|---|
| **API key** | Not required | `api_key: ${{ secrets.EVIDENCE_GATE_API_KEY }}` (not issued yet) |
| **What runs** | Local validation (file existence, JSON validity, numeric thresholds) and a SHA-256 digest of each evidence file | Planned hosted evaluation: Blind Gates, a tamper-evident hash chain (L4), quality state |
| **Gate types** | 30 of 35 (all except the 5 Pro-only types); no evaluation limit in local mode | All 35, including the 5 Pro-only types |
| **Best for** | Open-source projects, basic evidence-file checks | Planned, after the API launches, for teams that want hosted checks |

A custom `api_base` input exists for a future self-hosted deployment. Enterprise is not on sale, and the hosted API at the default URL is coming soon.

## When to Use This

- **AI-assisted development** -- when LLMs generate both code and tests, a coverage file can meet a number and still say little about quality. Free mode checks that the evidence file exists, is valid JSON, and meets a numeric threshold. Blind Gates (criteria kept outside the pipeline) are planned for the hosted API and are not available yet
- **CI records** -- each run writes the pass/fail result and a SHA-256 digest of the evidence files to the Actions log and job summary
- **Deployment gating** -- block deployment unless the evidence file is present and passes the local checks
- **Multi-gate pipelines** -- run coverage, security, and build gates in sequence with a single action

## Permissions

| Feature | `contents` | `checks` | `id-token` | `pull-requests` |
|---------|:----------:|:--------:|:----------:|:---------------:|
| Basic gate evaluation | `read` | -- | -- | -- |
| Check Run annotations | `read` | `write` | -- | -- |
| OIDC keyless auth (Pro, coming soon) | `read` | -- | `write` | -- |
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
      - uses: evidence-gate/evidence-gate-action@v2
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
| `api_key` | No | `""` | Evidence Gate API key. Omit for Free mode. The hosted API (Pro) is coming soon; keys are not issued yet |
| `api_base` | No | `https://api.evidence-gate.dev` | API base URL, used only when `api_key` is set. The hosted API at this default URL is coming soon (not launched). A custom URL is accepted; Enterprise is not on sale |
| `mode` | No | `enforce` | `enforce` (fail on gate failure) or `observe` (log results without blocking) |
| `gate_preset` | No | `""` | Named gate bundle (`web-app-baseline`, `enterprise-compliance`, `api-service`, `supply-chain`). Runs all gates in the preset |
| `sticky_comment` | No | `false` | Aggregate results into a single updating PR comment. Requires `pull-requests: write` |
| `debug` | No | `false` | Enable verbose diagnostic output |
| `version` | No | `latest` | Deprecated (no-op). Kept for backward compatibility; the action always uses its bundled stdlib-only evaluator |
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
| `trace_url` | Trace URL from a hosted evaluation response. Empty in Free mode. The hosted API (Pro) is coming soon |
| `evidence_url` | Evidence detail URL |
| `dashboard_url` | Dashboard URL |
| `github_run_url` | GitHub Actions run URL |

## Using Gate Results in Downstream Steps

```yaml
- name: Evidence Gate
  id: gate
  uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"

      - name: Security Gate
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
          mode: "observe"

      - name: Check results
        run: echo "Would have passed: ${{ steps.gate.outputs.observe_would_pass }}"
```

### Prevent AI agents from gaming your quality metrics

> **Coming soon:** Blind Gates require the hosted API (Pro), which is not launched. The example below is planned usage. Setting `api_key` against the default host fails closed today. Free mode does not hide thresholds.

Blind Gates, once that API exists, are meant to keep evaluation criteria outside the pipeline so the AI that generated the code does not read the thresholds from the workflow. The `skill` gate type is shown here because hidden criteria are the planned use case:

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
        uses: evidence-gate/evidence-gate-action@v2
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
        uses: evidence-gate/evidence-gate-action@v2
        with:
          gate_type: "test_coverage"
          phase_id: "testing"
          evidence_files: "coverage.json"
          sticky_comment: "true"

      - name: Build Gate
        uses: evidence-gate/evidence-gate-action@v2
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
      - uses: evidence-gate/evidence-gate-action@v2
```

### Validate SBOM and build provenance

Free mode checks the shape of supply-chain files. It does not verify signatures, and it does not check that an SBOM matches the built artifact.

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
      - uses: evidence-gate/evidence-gate-action@v2
        with:
          gate_type: "sbom"
          phase_id: "release"
          evidence_files: "sbom.cdx.json"
```

Use `gate_type: "provenance"` to check that a provenance file is JSON with the expected in-toto fields. Both gate types are available in Free mode. See [BENCHMARKS.md](BENCHMARKS.md) for what a pass does and does not mean.

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

If you already set a custom `api_base`, no action is needed -- your URL overrides the default. Enterprise is not on sale.

If you previously relied on the **default URL** `https://api.evidence-gate.com`, it has changed to `https://api.evidence-gate.dev`. Free users are unaffected -- the default URL change happens automatically. (The hosted API (Pro) is coming soon.)

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
| SBOM gate | `gate_type: sbom` | CycloneDX/SPDX structure (Free); does not check the SBOM matches the build |
| Provenance gate | `gate_type: provenance` | in-toto field check (Free); signatures are not verified |
| Check Run annotations | automatic | Findings appear inline in Files Changed tab |
| Signal-sorted Job Summary | automatic | Critical > Warning > Info |

### Migration Checklist

- [ ] Verify existing workflows still pass (most users: no action required)
- [ ] If you set a custom `api_base`: confirm the URL is still correct. Enterprise is not on sale
- [ ] Optional: add `.evidencegate.yml` to your repo for zero-input usage
- [ ] Optional: add `mode: warn` to non-critical gates for gradual rollout
- [ ] Optional: add `sticky_comment: true` to aggregate PR feedback

## Architecture

<p align="center">
  <img src="docs/architecture.svg" alt="Evidence Gate Action architecture diagram" width="800">
</p>

## Why This Exists

When AI agents (Copilot, Claude, Cursor) generate both production code and tests, traditional CI/CD gates lose their meaning. An LLM told to "achieve 80% coverage" will produce tests that hit exactly 80.1% -- a number that satisfies the metric but proves nothing about quality.

Evidence Gate's Free mode checks the evidence file that pipeline produced: the file is present, the JSON is valid, and numeric fields meet a threshold.

What exists today, and what is only planned:

1. **Free-mode checks (available now)** -- file existence, JSON validity, and numeric thresholds, plus a SHA-256 digest of each evidence file. Blind Gates, which would keep evaluation criteria outside the pipeline, need the hosted API (Pro). That API is coming soon and is not available.

2. **Evidence trust levels (planned model, not recorded by Free mode)**:
   - **L1** Declaration -- the pipeline claims something happened
   - **L2** Attestation -- a third party confirms the claim
   - **L3** Verification -- someone other than the author reproduces the claim
   - **L4** Hash chain -- `sha256(previous + evidence_hash)`, with no key, signature, or external log. Modifying a single record is detectable when the rest of the chain is unchanged (tamper-evident). A full-chain rewrite by someone with write access is not prevented. An auditor cannot treat the chain alone as independent proof.

3. **Fail-closed semantics (available now)** -- missing evidence, an unreachable API, or an evaluation error means FAIL, never a silent pass.

This is an open-source project under active development. We welcome feedback, contributions, and real-world use cases.

## Modes

| Mode | Config | What It Does |
|------|--------|-------------|
| **Free** | No `api_key` | Client-side evaluation: file existence, JSON validation, schema checks, numeric thresholds |
| **Pro** (coming soon) | `api_key` set | Planned hosted evaluation: Blind Gate, Quality State, tamper-evident hash chain (L4), remediation. The hosted API is not launched |
| **Enterprise** (coming soon) | `api_key` + custom `api_base` | The action can send the same request to a custom `api_base`. Enterprise is not on sale |

## Free vs Pro

The hosted API (Pro) is coming soon. The Pro / Enterprise column describes planned features.

| Feature | Free | Pro / Enterprise (coming soon) |
|---------|:----:|:----------------:|
| Evaluation limit | None (local mode) | To be announced |
| Gate types | 30 of 35 | All 35 |
| Check Run annotations | Yes | Yes |
| SHA-256 digest of each evidence file | Yes | Yes |
| Fail-closed error handling | Yes | Yes |
| `GITHUB_STEP_SUMMARY` | Yes | Yes |
| Observe mode | Yes | Yes |
| Gate presets | Yes | Yes |
| Sticky PR comments | Yes | Yes |
| Structured outputs (missing_evidence, suggested_actions) | Yes | Yes |
| Blind Gate evaluation | -- | Planned |
| Tamper-evident hash chain (L4) | -- | Planned |
| Quality State tracking | -- | Planned |
| Remediation workflows | -- | Planned |

L4, once the hosted API exists, links records as `sha256(previous + evidence_hash)`. There is no signing key and no external log. A single-record edit is detectable; rewriting the whole chain is not prevented. L4 is not available in this action today. The hosted API at `api.evidence-gate.dev` is coming soon (準備中).

## Troubleshooting

### "Gate type requires Pro plan" warning

You are using a Pro-only gate type (`blind_gate`, `quality_state`, `remediation`, `composite`, `wave`) without an `api_key`. The hosted API (Pro) is coming soon and API keys are not issued yet, so these gate types cannot be evaluated today. The step does not fail; use a Free gate type in the meantime. Questions: info@allnew.work

### Evidence file not found

- **Relative paths**: Paths are resolved from `$GITHUB_WORKSPACE`. Use `coverage.json`, not `/home/runner/work/.../coverage.json`.
- **Missing build step**: Ensure your test/build step runs **before** the Evidence Gate step.
- **No glob support**: List each file explicitly, separated by commas.

### API connection errors (Pro/Enterprise)

The hosted API (Pro) at `https://api.evidence-gate.dev` is coming soon and is not launched. Setting `api_key` without a custom `api_base` fails closed, because that default host is not a working endpoint.

Enterprise is not on sale. If you point `api_base` at a server you run yourself:

1. **API key**: `EVIDENCE_GATE_API_KEY` must be set in repository secrets for the client to send a request.
2. **API base URL**: `api_base` must be reachable from GitHub Actions runners.

The action uses **fail-closed** semantics: any unhandled error exits non-zero. An unreachable evaluation service does not pass the gate.

## Links

- [Landing Page](https://evidence-gate.dev)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
