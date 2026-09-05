# Wiki and Knowledge Base reference numbering

**Set by the owner, 2026-09-05.** Implemented in `src/library/references.py`
and enforced by `tests/test_library_references.py` — the scheme is code, not a
convention, because a numbering scheme written down in a document is one people
diverge from, and this estate has measured that outcome repeatedly.

## The distinction

| | Wiki | Knowledge Base |
|---|---|---|
| **Audience** | Administrative | User |
| **Holds** | Orientation, navigation, narrative, architecture, design specification, topology | How to do the thing |
| **Marker** | `WIX` | `KB` |

Before this, a citation to "the Library page on The Void" told a reader
nothing about which of the two they were being sent to, or whether they were
cleared to read it.

## The three scopes

Visibility differs by scope, so the scopes are visibly different.

| Scope | Form | Example | Who it is for |
|---|---|---|---|
| **Platform-wide** | `T` + marker + 6 digits | `TKB000001`, `TWIX000042` | True of the estate, not of one Location |
| **Location-scoped** | code + marker + 4 digits | `Infi-KB-0001`, `Tranq-WIX-0007` | Owned by one of the 43 Locations |
| **Personal** | `#One:` + marker + 4 digits | `#One:KB-0001` | Infinity-One's per-user knowledge base — private to that user unless they share it |

The `#One:` sigil is deliberately unlike the other two. A personal reference
pasted into a shared channel, a log line or a citation has to be recognisable
as personal at a glance, and `Reference.is_private` exposes that as a property
rather than leaving callers to compare scope values — the check that gets
skipped is the one nobody had to name.

## Location codes are derived, not tabulated

`location_code()` cuts a Location's name to four letters, dropping a leading
"The" — twenty of the forty-three begin with it. A hand-kept code table would
be one more register to drift out of step with `src/entities/platform.py`.

**Four letters is not enough for three pairs, and the collisions are real:**

| Colliding code | Locations | Resolved to |
|---|---|---|
| `Arca` | Arcadia, Arcadian Exchange | `Arcadia`, `Arcadian` |
| `Tran` | TranceFlow, Tranquility | `Tranc`, `Tranq` |
| `Warp` | The Warp Tunnel, Warp Radio | `Warpt`, `Warpr` |

A colliding code is extended — **for both sides, not just the newcomer** — to
the shortest length that separates them. Leaving one at four would make the
shorter code look canonical and the longer look like an exception, and the
next Location beginning "Tran" would collide again silently.

**This changes one of the owner's own examples.** `Tran-Wix` was given for
Tranquility; it cannot be honoured as written, because TranceFlow answers to
the same four letters. Tranquility is `Tranq`, TranceFlow is `Tranc`.
`Infi-KB` for Infinity survives unchanged.

`collisions()` returns `{}` today and exists so that "codes are unique" is a
checked claim rather than an assumed one.

## What it refuses

A malformed reference raises rather than returning `None`, so it cannot be
quietly read as "no reference" — the failure that lets a citation to nothing
survive review.

- A code no Location holds: *"no Location has the code 'Zzzz'"*
- A shape matching none of the three forms, with all three named in the error
- A Location-scoped reference with no Location
- A Location outside the 43
- A number below 1

The owner's lowercase `Wix` spelling parses; `WIX` is what is emitted. A
scheme that rejects the spelling it was defined in is a scheme nobody can use
from memory.
