---
title: "Workflow Action SHA Audit"
category: Reference
last-reviewed: 2026-08-21
status: needs-update
---

# Workflow Action SHA Audit

> **Purpose.** Documents the policy and procedure for auditing third-party GitHub
> Action references across `.github/workflows/*.yml` and `.forgejo/workflows/`.
> This closes the gap noted in `docs/PROJECT_COVERAGE_MAP.md` §2.8: there was no
> dedicated doc describing *what each workflow does* or how action references are
> governed between the GitHub Actions and Forgejo CI/CD systems.

## Why SHA pinning matters

GitHub Actions (and Forgejo actions) let a workflow invoke another repository's
code via a `uses:` reference. A tag or branch reference (e.g. `actions/checkout@v4`)
is mutable — the upstream can move the tag, silently changing the code your CI runs.
A SHA reference (e.g. `actions/checkout@<40-hex-sha>`) is immutable: the runner
verifies the exact commit before executing. SHA pinning is the supply-chain control
that prevents a compromised or hijacked action from executing in our pipelines.

## The audit rule

Every `uses:` entry in CI must resolve to a full 40-character commit SHA, with the
human-readable tag kept as a trailing comment for reviewability:

```yaml
uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
```

The `# v6` comment is documentation only — the runner still pins to the SHA.

## How to audit

1. Grep every workflow for `uses:` lines that do **not** match a 40-char SHA:
   ```bash
   grep -rn "uses:" .github/workflows/*.yml .forgejo/workflows/*.yml \
     | grep -vE "@[0-9a-f]{40}"
   ```
2. For each offending line, resolve the current tag to its commit SHA and replace
   the reference. Pin to the SHA of the exact version you intend to use.
3. Re-run the grep to confirm zero unpinned references remain.

## Division of labour

- **GitHub Actions** (`.github/workflows/`) — kept deliberately for PR status
  checks, CodeQL, and Pages/Wiki publishing, where no Forgejo equivalent exists.
  See `ci.yml`, `codeql.yml`, `python.yml`, `rust.yml`, `go.yml`, `trivy.yml`,
  `publish-wiki.yml`, `publish-matrix-site.yml`.
- **Forgejo** (`.forgejo/workflows/`) — the primary deployment and security-scan
  system (see `CLAUDE.md` CI/CD section). Includes `deploy-fly.yml`,
  `deploy-cloudflare.yml`, `security-scan.yml`, `dependency-audit.yml`.

Both systems are held to the same SHA-pinning standard.

## Related

- `docs/PROJECT_COVERAGE_MAP.md` — maps the repo's code layout to its docs (this
  doc fills the CI/CD workflow-coverage gap).
- `.github/workflows/submodule-pins.yml` — companion guard for git submodule pins.
