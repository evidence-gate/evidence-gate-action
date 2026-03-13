# Releasing Evidence Gate Action

## Pre-release Checklist

- [ ] All CI checks pass on `main` branch
- [ ] README.md is up to date with correct URLs
- [ ] CHANGELOG.md has v1.0.0 entry
- [ ] Landing page is live at https://evidence-gate.dev
- [ ] `action.yml` branding is set (icon=shield, color=green)

## Release Steps

### 1. Create GitHub Release

```bash
gh release create v1.0.0 \
  --repo evidence-gate/evidence-gate-action \
  --title "v1.0.0 — Initial Release" \
  --generate-notes \
  --latest
```

### 2. Verify Marketplace Listing

After the release is created:

1. Visit https://github.com/marketplace/actions/evidence-gate
2. Verify the listing shows:
   - Name: "Evidence Gate"
   - Description from action.yml
   - README rendered correctly
   - Branding: green shield icon
3. Verify `@v1` floating tag was updated by the release workflow

### 3. Verify Installation

Test that a new user can install the action:

```yaml
- uses: evidence-gate/evidence-gate-action@v1
  with:
    gate_type: "file_check"
    phase_id: "test"
    evidence_files: "test.json"
```

## Subsequent Releases

For patch/minor releases (v1.0.1, v1.1.0, etc.):

```bash
gh release create v1.x.x \
  --repo evidence-gate/evidence-gate-action \
  --title "v1.x.x — Description" \
  --generate-notes \
  --latest
```

The `release.yml` workflow automatically updates the `v1` floating tag.

## Notes

- The actual `gh release create` command is executed **manually** by the repository owner.
- Marketplace listing activation happens automatically when a GitHub Release is published with a valid `action.yml` containing branding metadata.
- The release workflow (`.github/workflows/release.yml`) handles floating tag updates (`v1` -> latest `v1.x.x`).
