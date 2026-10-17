# Releasing Evidence Gate Action

## Pre-release Checklist

- [ ] All CI checks pass on the `master` branch
- [ ] `CHANGELOG.md` has an entry for the new version (e.g. `## [2.0.2]`)
- [ ] `pyproject.toml` and `uv.lock` project version match the new version
- [ ] README.md / README.ja.md / `action.yml` are up to date
- [ ] `action.yml` branding is set

## Release Steps

### 1. Tag and publish a GitHub Release

Create an annotated tag on the merge commit on `master`, push it, then publish the release:

```bash
git tag -a v2.x.y -m "v2.x.y" <master-sha>
git push origin v2.x.y
gh release create v2.x.y \
  --repo evidence-gate/evidence-gate-action \
  --title "v2.x.y" \
  --notes-file notes.md \
  --latest
```

### 2. Floating major tag (automatic)

When a release is **published**, `.github/workflows/release.yml` moves the floating major tag (`v2`) to the released `v2.x.y` tag automatically. Verify afterwards:

```bash
git fetch --tags --force
git rev-list -n1 v2 && git rev-list -n1 v2.x.y   # must match
```

The `v1` tag is frozen and must not be moved. Breaking changes require a new major version (`v3.0.0`, floating `v3`).

### 3. Verify Marketplace Listing

1. Visit https://github.com/marketplace/actions/evidence-gate
2. Check the description (from `action.yml`), README rendering and branding.

### 4. Verify Installation

```yaml
- uses: evidence-gate/evidence-gate-action@v2
  with:
    gate_type: "test_coverage"
    phase_id: "test"
    evidence_files: "test.json"
```

## Notes

- Releases are created manually by the repository owner (or with their approval).
- Do not force-push branches. Only the floating major tag is moved, by `release.yml`.
