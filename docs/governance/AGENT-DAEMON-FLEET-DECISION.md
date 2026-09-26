# The Charlie daemon fleet: fourteen install requests, one decision

**Decided 2026-09-26. Outcome: none of the fourteen are installed.**
**Owner decision still open: whether the Charlie GitHub App keeps write access at all.**

Between 07:27 and 08:59 on 2026-09-11, `charliecreates[bot]` opened fourteen pull
requests against this repository — #1183–#1196. Each adds one
`.agents/daemons/<id>/DAEMON.md`, and two also add executable TypeScript. They are
not fourteen changes; they are one question asked fourteen times: **should this
estate run a fleet of autonomous agents with write access to its repository?**

This record answers it with measurements rather than posture, so that a later
"why didn't we take these?" has something to read.

## The fact that decides the framing

A `DAEMON.md` looks like documentation. It is not, here.

`charliecreates[bot]` (GitHub App `charliecreates`, app id 198680274) is the
**author** of all fourteen branches and pull requests.

Authorship alone would not prove write access — a fork author can open a pull
request against a public base repository without it. So the head repository was
checked rather than assumed. Every one of the fourteen reports
`head.repo.full_name = "Trancendos/Tranc3"`, not a fork, and the branches live
in this repository under the `charlie/daemon-installs/` prefix. Pushing a branch
here requires write access, so the App holds it. (Raised by
chatgpt-codex-connector on #1240 — the conclusion stood, the evidence for it was
not written down.)

Nothing in this repo reads `.agents/`. Measured: `git ls-tree -r origin/main`
returns no `.agents/` path, and a repository-wide grep for `.agents/`,
`DAEMON.md` and `daemons/` returns nothing across `.py`, `.yml`, `.yaml`, `.md`,
`.json`, **`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.go`, `.rs`, `.sh` and
`.toml`**. The executable extensions matter and were missing from the first pass
of this record: the cluster itself ships TypeScript, so a `.ts` consumer is
exactly the one that would have been overlooked. (sourcery-ai on #1240.) The
consumer is external.

So merging a `DAEMON.md` does not add a document. It **arms an agent that already
has the access to act**, against a queue of **78 open pull requests — measured
2026-09-26** by listing `state=open` pull requests for this repository and
counting the result. (Not to be confused with the 84 in
`docs/governance/CI-ESTATE-CONSOLIDATION.md`: that is a different figure from
2026-09-10, counting pull requests blocked by one CI cause. Flagged by
codeant-ai on #1240.) That is the decision, and it is the same decision fourteen
times.

## What each one was measured against

### Four are configured for a tool this estate does not use (#1191–#1194)

`linear-pr-link-reconciler`, `linear-issue-labeler`,
`linear-issue-duplicate-finder`, `linear-bug-context-researcher`.

Measured: a repository-wide search for `linear.app`, `linear.com`, `LINEAR_API_KEY`,
`linear_api` and `linear-issue` returns **zero** matches outside linear-algebra
false positives. There is no Linear integration here, no Linear issue tracker, and
nothing for these four to reconcile, label, deduplicate or research.

They are not wrong so much as addressed to someone else. Rejected on that alone.

### Three are triage machinery for a backlog that does not exist (#1185, #1195, #1196)

`github-issue-labeler`, `github-issue-duplicate-finder`,
`github-bug-context-researcher`.

Measured: **12 open issues** — #174, #284, #334, #336, #337, #474, #969, #990,
#991, #995, #1146, #1180. That is the whole tracker, and it is the same figure
`docs/governance/EXTERNAL-ASSESSMENT-REVIEW.md` recorded independently.

That document already states the rule this triggers, and it was written for
exactly this shape of proposal: externally generated reports reliably read the
issue tracker and reliably invent the aggregates, and the "triage blitz"
machinery all of them propose is for a backlog that does not exist. A duplicate
finder needs duplicates. A labeller needs a volume of issues where labelling
changes what anyone does. Twelve issues, nine of them already carrying the labels
that matter, is not that.

### One would overwrite the evidence this repository writes into pull requests (#1189)

`pr-metadata`. Its body policy normalises every pull request body to four fixed
headings — `## Primary changes`, `## Reviewer walkthrough`,
`## Correctness and invariants`, `## Testing and QA` — and appends
`Resolves <issue-id>` / `Refs <issue-id>` lines. It triggers on `opened`,
`reopened`, `synchronized`, and on a human editing the body.

This estate's pull request bodies are its working record: what was measured, the
command that measured it, and what the measurement disproved. #1239 is the
example to hand — its body carries four numbered findings, each with the tool's
own error text. Normalising that into a template is not a formatting change; it
is the deletion of the evidence, performed automatically, and re-performed every
time a human edits the body back.

Rejected as actively harmful to how this repository works.

### Two duplicate a role that is already contested (#1187, #1190)

`pr-merge-conflict-repair` and `pr-check-repair`. Both push commits to pull
request branches: the first on every push to the default branch, scanning all
open pull requests for `mergeable: CONFLICTING`; the second on every
non-successful check run.

Two problems, both measured.

**Volume.** There are 78 open pull requests. A default-branch push triggering a
conflict scan and repair pass across all of them is precisely the
prolonged-and-heavy automation that `CLAUDE.md`'s standing policy exists to avoid
— "avoid GitHub Actions and Cloudflare Workers wherever possible (both carry rate
limits that bite under prolonged/heavy use)". The policy's reasoning does not stop
at Actions; it is about what a fleet of writers costs.

**Collision.** Conflict resolution and drive-to-green on this estate's pull
requests are already performed by the sessions doing the merge work. Mergify is
*not* a second party to that, and an earlier draft of this record said it was:
`.mergify.yml` defines `merge`, `label` and `comment` actions only — it merges
eligible pull requests and manages metadata, and resolves no conflicts and
repairs no checks. (codeant-ai on #1240.) One concurrent writer, not two, and
adding a third-party agent to the same branches still makes it a race.
`pr-check-repair`'s own specification concedes the hazard and
spends three sections on it — "Expect parallel `pr-check-repair` activations",
a flaky-rerun guard that must "fail closed", and an admission that its checks
"do not provide atomic exactly-once execution". A design that documents its own
race is honest, and it is still a race.

### One duplicates the eighth review bot with a ninth (#1188)

`pr-review`. Measured on #1239's check run list and comment thread, this
repository already runs **CodeRabbit, CodeAnt, Sourcery, cubic, Copilot autofix
(github-advanced-security), CodeFactor, ecc-tools and Mergify** against every
pull request.

To its credit, `pr-review` is the only one of the nine whose policy explicitly
defers to the others — "Problems already clearly reported by current checks, the
compiler, a formatter, a linter, or another review" are on its never-report list,
and it refuses to `APPROVE` or `REQUEST_CHANGES`. That is better behaviour than
most of the eight already here. It is still a ninth reviewer on a queue whose
problem is not too little review.

### One is the closest call, and it is a concurrency decision (#1186)

`pr-review-triage`. This is the one the first draft of this record omitted
entirely — the groups covered thirteen of fourteen, and #1186 had a disposition
on its own pull request but none here. (Caught independently by sourcery-ai and
chatgpt-codex-connector on #1240. An exhaustive classification that is not
exhaustive is the same defect as a register that claims to carry content it
dropped, which is the other thing review caught this week.)

It is the one that targets a problem this estate demonstrably has. Eight review
bots produce a great deal of output across 78 open pull requests, and this
daemon's job is to disposition *non-human* review threads — `valid`, `invalid`,
`duplicate`, `fixed`, `uncertain` — reply with rationale, and resolve or
minimise the duplicates. Its deny list is strict in the right direction: it will
not reply to, hide, minimise or react to human-authored feedback, will not
approve or merge, will not push commits, and will not resolve a thread "just
because a new commit mentions it" without code-level evidence.

Declined on concurrency, not on quality. Review-thread triage on these pull
requests is already being done by the sessions working the merge queue — reading
each bot finding, deciding whether it is real, replying and resolving. Two
agents resolving the same threads is the same race as #1187 and #1190, and this
one cannot be scoped to a subset of pull requests.

Its disposition model is a good starting design if the bot-noise problem is
attacked later, and this record says so deliberately rather than leaving the
reasoning to a closed pull request.

### Two would add scheduled pull requests to a 78-deep queue (#1183, #1184)

`docs-drift-maintainer` (cron `0 10 * * 1-5`) and `docs-stale-maintainer`. Both
open documentation pull requests on a schedule, inferring targets from
"repository conventions".

Two reasons this does not fit. The queue is 78 deep and the constraint is
throughput, not the absence of docs pull requests. And both deny lists exclude
"legal, security, compliance, or policy documents without explicit human
approval" — which is most of `docs/governance/`, where this estate's
documentation drift actually lives and where every correction so far has come
from measuring something, not from inferring it from filenames and headings.

### The one with standalone value cannot run here

`find-conflicted-pulls.ts`, shipped with #1187, is read-only: it lists open
non-draft pull requests whose `mergeable` is `CONFLICTING`. With 78 open pull
requests that is a genuinely useful thing to know, independent of any daemon.

**An earlier draft of this record rejected it on tool availability, and that was
wrong.** It claimed `gh` is not installed in this estate's environments and that
nobody here could run the script. Measured properly: **11 workflows in
`.github/workflows/` invoke `gh`**, three of them calling `gh pr` / `gh api` /
`gh issue` directly on `ubuntu-latest` without an install step, because GitHub's
runners ship it. `bun` is likewise present in the agent container (1.3.11). The
script is runnable. (chatgpt-codex-connector on #1240 — and the correct lesson
is the one it stated: an absent executable and missing authentication are
different findings, and neither had been established.)

What survives the correction is narrower and still real: `bun` appears **nowhere
in this repository's own toolchain** — no reference in `.github/`, `Makefile` or
`package.json` — so adopting these scripts introduces a new runtime dependency
for the estate to carry and pin. For a read-only GraphQL query over open pull
requests, that is a poor trade against the same query in the Python tooling
`scripts/` already uses everywhere else.

So: if the conflict scan is wanted, write it against this repository's own
tooling. Not because the original cannot run, but because adopting it would add
a runtime to the estate as a side effect of a decision about daemons.

## What is left for the owner

Closing fourteen install requests does not uninstall anything. The Charlie App
retains the write access it used to open them, and will presumably ask again.

**The decision this record cannot make:** whether `charliecreates` keeps write
access to this repository at all. Declining its fourteen proposals while leaving
it able to push branches is the least coherent of the three available states. The
other two are coherent: revoke the App, or decide deliberately which daemons to
install through Charlie's own configuration rather than by merging files here.

That is an owner decision about vendor posture, and it is recorded here as open.

## The generalisable rule

**A configuration file for an installed agent is a grant of authority, not a
document.** Review it against what the agent can already do, not against what the
file says. The fourteen read as documentation and behave as fourteen keys.
