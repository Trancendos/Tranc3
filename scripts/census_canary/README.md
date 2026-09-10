# npm registry canary

This directory is not a service and nothing imports it. It is a one-package
lockfile whose only job is to be **known-vulnerable**, so that
`scripts/vulnerability_census.py` can tell two answers apart that `npm audit`
otherwise reports identically:

- the registry answered, and this surface has no advisories; and
- the registry did not really answer, and npm printed an empty report anyway.

`minimist@0.0.8` is pinned because GHSA-vh95-rmgr-6w4m (prototype pollution,
published 2020) affects `minimist < 0.2.1`, a range no longer maintained and
therefore one whose advisory will not be superseded by a patch to that version.
An audit of this directory that reports **zero** vulnerabilities is proof the
registry's audit endpoint is not answering usefully — see
`_npm_registry_reading()` in the census.

Do not "fix" the pin. Bumping `minimist` here silently disables the check that
every other npm result in the census depends on.
