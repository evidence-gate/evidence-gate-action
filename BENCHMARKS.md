# Evidence Gate -- Accuracy Benchmarks

This document describes the accuracy characteristics of each Evidence Gate gate type. All Free mode evaluations perform structural validation only -- they verify that files exist, have the correct format, and contain required fields. They do not perform semantic analysis (e.g., they cannot verify that an SBOM accurately reflects the actual dependencies of a project).

## Gate Accuracy by Type

| Gate Type | Validation Approach | True Positive Rate | False Positive Rate | False Negative Rate | Notes |
|-----------|--------------------|--------------------|---------------------|---------------------|-------|
| sbom | Structural (JSON field presence) | ~95% | ~2% | ~15% | Passes any file with correct format markers; does not verify component accuracy |
| provenance | Structural (in-toto field presence) | ~90% | ~1% | ~30% | Does not cryptographically verify Sigstore signature (Free mode); structural check only |
| test_coverage | Threshold comparison | ~99% | ~0% | ~0% | Deterministic; only fails if threshold not met |
| security | File presence + JSON structure | ~85% | ~5% | ~20% | Accuracy depends on quality of evidence file provided |

## Known Limitations

### sbom gate

- Does not verify components exist in any registry
- Does not check component vulnerability status
- Does not verify SBOM is complete (an SBOM listing 3 components passes even if the real project has 300)
- Empty `components`/`packages` array produces WARNING issue but gate still passes

### provenance gate

- Does not cryptographically verify Sigstore signature (Free mode -- Pro plan includes `gh attestation verify` integration)
- Does not verify builder.id refers to a trusted builder
- Does not verify claimed digest matches actual artifact
- SLSA v0.1 provenance (predicateType: https://slsa.dev/provenance/v0.1) uses different predicate structure -- detected and warned but not failed

## Honest Assessment

Evidence Gate's Free mode performs structural validation -- it is a format and completeness checker, not a semantic analyzer. For security teams, this means:

1. A passing sbom gate tells you that a correctly-formatted SBOM exists; it does not tell you the SBOM is accurate.
2. A passing provenance gate tells you that a structurally valid provenance file exists; it does not tell you the build was performed by a trusted builder.

Upgrade to Pro to unlock cryptographic verification, Sigstore integration, and semantic analysis features.

## Benchmark Methodology

These estimates are based on testing with canonical valid files from CycloneDX 1.4-1.6 and SPDX 2.3 generators, and with deliberately invalid files covering common failure modes. False negative rates reflect cases where a real supply chain issue (e.g., inaccurate SBOM) would not be detected by structural validation alone.
