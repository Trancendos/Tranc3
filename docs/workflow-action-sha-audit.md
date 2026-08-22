# Workflow GitHub Action SHA Audit

**Date:** 2026-08-21
**Scope:** Every `uses: owner/repo@<40-char-SHA> # <tag>` reference in
`.github/workflows/*.yml` and `.forgejo/workflows/*.yml`.
**Method:** Resolve each pinned SHA against the GitHub Releases/Tags API to
determine (a) the latest patch release within the *pinned major version* (the
`# vN` comment encodes the maintainer's intended major) and (b) the commit SHA
of that release. A reference is "outdated" when its pinned SHA no longer equals
the latest patch SHA of its pinned major line.

> Pinning strategy note: this repository tracks GitHub Actions by major version
> (e.g. `# v4`) and keeps the commit SHA current to the latest patch of that
> major. The audit therefore updates SHAs *within the pinned major* to avoid
> untested cross-major behaviour changes. Action references that are multiple
> majors behind the newest overall release are listed separately as upgrade
> candidates (see "Upgrade candidates" below) and were deliberately **not**
> bumped here without behavioural testing.

## Results: 16 unique actions, 241 total references

| Action | Pinned SHA | Comment | Latest patch in pinned major | Latest patch SHA | Status |
|---|---|---|---|---|---|
| actions/checkout | 11d5960a326750d5838078e36cf38b85af677262 | v4 | v4.4.0 | 11d5960a… | ✅ updated (was 34e1148…) |
| actions/setup-python (v5) | a26af69be951a213d495a4c3e4e4022e16d87065 | v5 | v5.6.0 | a26af69b… | ✅ updated (was 4237552…) |
| aquasecurity/trivy-action | ed142fd0673e97e23eac54620cfb913e5ce36c25 | v0.36.0 | v0.36.0 | ed142fd0… | ✅ updated (was `…f03c8 # master`) |
| dtolnay/rust-toolchain | 4360b52568e2003a75bf9bc1d59f33a8e3fc893c | stable | stable (moving tag) | 4360b525… | ✅ updated (was 4be7066a…) |
| actions/cache | 0057852bfaa89a56745cba8c7296529d2fc39830 | v4 | v4.3.0 | 0057852b… | ✅ current |
| actions/deploy-pages | d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e | v4 | v4.0.5 | d6db9016… | ✅ current |
| actions/download-artifact | 3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c | v8 | v8.0.1 | 3e5f45b2… | ✅ current |
| actions/github-script | f28e40c7f34bde8b3046d885e986cb6290c5673b | v7 | v7.1.0 | f28e40c7… | ✅ current |
| actions/setup-go | 40f1582b2485089dde7abd97c1529aa768e1baff | v5 | v5.6.0 | 40f1582b… | ✅ current |
| actions/setup-node | 49933ea5288caeca8642d1e84afbd3f7d6820020 | v4 | v4.4.0 | 49933ea5… | ✅ current |
| actions/setup-python (v6) | ece7cb06caefa5fff74198d8649806c4678c61a1 | v6 | v6.3.0 | ece7cb06… | ✅ current |
| actions/upload-artifact | 043fb46d1a93c77aae656e7c1c64a875d1fc6a0a | v7 | v7.0.1 | 043fb46d… | ✅ current |
| actions/upload-pages-artifact | 56afc609e74202658d3ffba0e8f6dda462b719fa | v3 | v3.0.1 | 56afc609… | ✅ current |
| advanced-security/dismiss-alerts | a18f986bdb40edba0dd7a74382c15d4a3d50a1c8 | v2 | v2.0.3 | a18f986b… | ✅ current |
| codecov/codecov-action | b9fd7d16f6d7d1b5d2bec1a2887e65ceed900238 | v4 | v4.6.0 | b9fd7d16… | ✅ current |
| golangci/golangci-lint-action | ba0d7d2ec06a0ea1cb5fa41b2e4a3ab91d21278a | v9 | v9.3.0 | ba0d7d2e… | ✅ current |

## References that could NOT be updated

- **`.forgejo/workflows/registry-push.yml:105` —
  `uses: https://code.forgejo.org/actions/github-script@v7`**
  This is a Forgejo-hosted action (a different registry from
  `github.com/actions`), pinned to a moving tag `v7` rather than a GitHub-style
  commit SHA. It is outside the GitHub Releases API audit scope and cannot be
  SHA-pinned with the same tooling. Left as-is; recommend tracking Forgejo's
  upstream for security advisories or mirroring to a pinned SHA if a SHA-based
  Forgejo mirror becomes available.

## Updated references (summary)

1. `actions/checkout` → `11d5960a326750d5838078e36cf38b85af677262` (v4.4.0), 108 occurrences.
2. `actions/setup-python` (v5) → `a26af69be951a213d495a4c3e4e4022e16d87065` (v5.6.0), 2 occurrences.
3. `aquasecurity/trivy-action` → `ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0), changed from a moving `master` branch pin to a fixed release tag, 2 occurrences.
4. `dtolnay/rust-toolchain` → `4360b52568e2003a75bf9bc1d59f33a8e3fc893c` (current `stable` moving tag), 3 occurrences.

Total edits: 115 `uses:` lines across 50 workflow files.

## Upgrade candidates (multiple majors behind — NOT bumped, needs behavioural review)

These pin an older major but are already at the latest *patch* of that major.
Bumping them to the newest overall release is a behaviour change and should be
tested separately:

| Action | Current major | Newest overall release | Risk |
|---|---|---|---|
| actions/checkout | v4 | v7.0.1 | Medium — widespread use |
| actions/setup-python | v5 / v6 | v7.0.0 | Low–Medium |
| actions/setup-node | v4 | v7.0.0 | Medium |
| actions/setup-go | v5 | v7.0.0 | Low |
| actions/cache | v4 | v6.1.0 | Low |
| actions/deploy-pages | v4 | v5.0.0 | Low |
| actions/upload-pages-artifact | v3 | v5.0.0 | Low–Medium |
| actions/github-script | v7 | v9.0.0 | Medium (API changes) |
| codecov/codecov-action | v4 | v7.0.0 | Low–Medium |
| golangci/golangci-lint-action | v9 | v9.3.0 | None (already at v9.3.0) |

## Reproducing the audit

```bash
# List every unique action@SHA reference with its comment tag
grep -rEn 'uses:\s+[a-zA-Z0-9_./-]+/[a-zA-Z0-9_./-]+@[0-9a-f]{40}' \
  .github/workflows .forgejo/workflows

# For each repo, find the latest patch within the pinned major:
gh api repos/<owner>/<repo>/tags?per_page=100 --jq '.[].name'
gh api repos/<owner>/<repo>/commits/<tag> --jq '.sha'
```
