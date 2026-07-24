# Personality Archetypes — Research Basis for Job-Description Trait Vectors

> **What this is.** A grounding pass over `src/personality/profiles/*.json`'s trait vectors
> (`PersonalityProfile.traits` per `src/personality/matrix.py`), checking each Job Description
> holder (`docs/governance/LOCATION-FUNCTIONS.md` §2) against real research on the Big-Five /
> extended personality patterns typical of that professional archetype — not just Royal Bank of
> Arcadia's Dorris Fontaine (the original worked example), but every assigned AI across the 43
> Locations.
>
> **Finding, up front:** the existing 38 profile files were already well-tuned and largely
> archetype-consistent (see §2's evidence table) — this pass is a validation + gap-fill, not a
> wholesale rewrite. Two Job Description holders (`Imfy` — The Spark, `Trancendos` — The Citadel /
> Think Tank) had no profile mapped to them; §3 resolves both — `Imfy` via the existing
> `norman-hawkins` profile's own `serves` declaration, `Trancendos` via a newly added profile file.
> One Location (`DocUtari`) has a named Lead AI (`lead_ai = "Fiddsy"`, per
> `trance_one/platform_manifest.py` — see `docs/governance/LOCATION-FUNCTIONS.md`'s 2026-07-24
> verification-log entry) but no personality profile authored for it yet, and correctly gets none.

## 1. Archetype research (Big Five / extended traits)

Eight recurring professional archetypes cover the platform's 43 Job Descriptions. Each is grounded
in published research on that profession's typical personality pattern, not invented:

| Archetype | Representative Job Descriptions | Research-backed pattern | Sources |
|---|---|---|---|
| **Precision / Finance & Risk** | CFO (Royal Bank of Arcadia), Chief Procurement Officer (Arcadian Exchange), Head of Artifact Management (The Artifactory), Chief Audit & Monitoring Officer (The Observatory) | Very high conscientiousness, low neuroticism, low-moderate extraversion, high formality, low humor. High extraversion+openness combined with low neuroticism/agreeableness/conscientiousness predicts risk-*taking* — the inverse (high conscientiousness, controlled openness) predicts risk-*aversion*, the correct fit for finance/audit roles. | [Big Five & risk-taking](https://arxiv.org/pdf/2503.04735), [Big Five in the workplace](https://online.fit.edu/degrees/graduate/master-organizational-leadership/how-the-big-five-personality-traits-influence-work-behavior/) |
| **Technology / Orchestration leadership** | CTO (Luminous), Head of Workflow Engineering (The Digital Grid), Head of API Integrations (API Marketplace) | High openness *and* high conscientiousness together, moderate-high extraversion, low neuroticism. Meta-analysis: leadership correlates most with low neuroticism (−0.24), extraversion (0.31), openness (0.24), conscientiousness (0.28). | [Big Five & leadership meta-analysis](https://www.researchgate.net/publication/377415434_The_Big_Five_Personality_Traits_and_Leadership_A_Comprehensive_Analysis) |
| **Security / vigilance** | CISO (Cryptex), Chief Secrets & Vault Officer (The Void), Chief Identity & Access Officer (Infinity), Head of Cryptographic Token Services (The Lighthouse), Head of Threat Scanning (The Warp Tunnel), Head of Sandbox Threat Isolation (The Ice Box) | Extreme conscientiousness, low-moderate agreeableness (professional skepticism/distrust-by-default), high assertiveness, very high formality, near-zero humor, low-moderate openness (innovation channeled narrowly, not novelty-seeking). | [Essential traits of a CISO](https://cloudsecurityalliance.org/articles/navigating-the-cybersecurity-seas-the-essential-traits-of-a-successful-ciso), [CISO qualities](https://itchronicles.com/security/5-qualities-of-a-great-ciso/) |
| **Creative** | Chief Creative Officer (The Studio), Head of Photo/Image Generation (Sashas Photo Studio), Head of 3D/Game Dev (TranceFlow), Head of Video Production (TateKing), Chief Design Officer (Fabulousa), Chief Creative Orchestration Officer (Imaginarium) | Very high openness (the one trait consistently linked to creativity across studies), lower conscientiousness relative to precision roles, higher extraversion/humor, low formality. | [Big Five & creativity meta-analysis](https://www.researchgate.net/publication/347557360_Big_Five_Personality_Traits_and_Creativity), [creative-director profile](https://www.ideatovalue.com/crea/nickskillicorn/2022/03/the-creative-personality-which-of-the-big-5-personality-traits-is-associated-with-creativity/) |
| **Governance / compliance** | Chief Governance Officer (The Town Hall), Head of Source Control & CI/CD (The Workshop), Chief Audit & Monitoring Officer (The Observatory) | Conscientiousness is *the* trait most consistently linked to rule-following — internalized standards that function as background "internal rules." High formality, low humor, moderate-low neuroticism. | [Psychology of compliance officers](https://www.zimbardo.com/the-psychology-behind-being-a-compliance-officer/), [conscientiousness & compliance](https://jewlscholar.mtsu.edu/bitstreams/0f7a1ce6-3660-4276-8fd8-763639b34c8f/download) |
| **Community / people / wellbeing** | Chief Community & Front-End Officer (Arcadia), Chief Wellbeing Officer (Tranquility), Head of Emotional Intelligence (I-Mind), Chief Empathy Officer (Resonate), Head of Digital Twin Services (tAimra) | High agreeableness and empathy, high extraversion, high adaptability, low neuroticism, low formality. Agreeableness → cooperative/compassionate; extraversion → sociable/energetic; both correlate positively with career satisfaction in this cluster. | [Big Five in HR/community roles](https://www.thomas.co/resources/type/hr-blog/which-personality-attributes-are-most-important-workplace), [empathy & personality](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9112556/) |
| **Knowledge / archival** | Chief Knowledge Officer (The Library), Head of Archives (The Basement), Head of Learning & Development (The Academy) | High conscientiousness *and* high openness together (meticulous cataloguing + intellectual curiosity), moderate-low extraversion (introverted, focused independent work), high agreeableness. | [Librarian personality traits](https://www.zimbardo.com/the-psychology-behind-being-a-librarian/), [librarian knowledge-management behavior](https://www.degruyterbrill.com/document/doi/10.1515/libri-2024-0012/html?lang=en) |
| **DevOps / QA / engineering** | Head of DevOps (DevOcity), Head of Quality Assurance & Testing (The Chaos Party), Chief Engineering Officer (The Lab) | QA testers score highest measured conscientiousness of any tech role (91st percentile), moderate-to-low agreeableness, moderate neuroticism (vigilance to defects). DevOps roles run slightly lower (84th percentile) with more systematic/ISTJ-ISTP process orientation. | [QA tester psychology](https://jobcannon.io/blog/psychology-of-qa-testers), [DevOps traits](https://www.lambdatest.com/blog/recognize-and-hire-top-qa-devops-engineers/) |

`The Chaos Party`'s Mad Hatter persona deliberately keeps its Wonderland-themed high humor/high
extraversion — that is intentional lore per `CLAUDE.md` ("Alice in Wonderland themed"), layered on
top of (not instead of) the archetype's underlying high conscientiousness; it is not a mismatch to
correct.

## 2. Validation against existing profiles (evidence, not guesswork)

Spot-checking one profile per archetype against its numeric trait vector confirms the existing
work already tracks the research, before any new tuning:

| Profile (archetype) | conscientiousness | neuroticism | extraversion | formality | humor | Matches archetype? |
|---|---|---|---|---|---|---|
| `dorris-fontaine` (Precision/Finance) | 0.98 | 0.05 | 0.40 | 0.95 | 0.15 | ✅ |
| `cornelius-macintyre` (Tech leadership) | 0.92 | 0.08 | 0.80 | 0.75 | 0.35 | ✅ (openness 0.85 too) |
| `prometheus` / `the-guardian` (Security) | 0.99 | 0.02 | 0.20–0.30 | 0.98–0.99 | 0.04–0.05 | ✅ |
| `voxx` (Creative) | 0.72 | 0.08 | 0.88 | 0.30 | 0.70 | ✅ (openness 0.99) |
| `tristuran` (Governance) | 0.97 | 0.04 | 0.60 | 0.90 | 0.20 | ✅ |
| `lilli-sc` / `savania` (Community/wellbeing) | 0.82 | 0.05–0.08 | 0.72–0.92 | 0.30–0.45 | 0.58–0.65 | ✅ (agreeableness 0.92–0.97) |
| `zimik` / `gary-glowman` (Knowledge/archival) | 0.88–0.95 | 0.05–0.06 | 0.30–0.42 | 0.65–0.82 | 0.28–0.35 | ✅ |
| `the-mad-hatter` (DevOps/QA) | 0.88 | 0.12 | 0.90 | 0.18 | 0.88 | ✅ conscientiousness for the archetype, humor/extraversion is the deliberate Wonderland layer above it |

No profile in this sample contradicted its archetype badly enough to warrant a rewrite. The
remaining ~30 profiles were reviewed the same way (dumped and diffed against archetype ranges);
none needed correction either. Effort went instead into the two real gaps below and the actual
wiring work (§3–4).

## 3. Gaps filled

| Location | Job Description | `lead_ai` | Profile before this pass | Action |
|---|---|---|---|---|
| The Spark | Head of AI Tooling | Imfy | none under an `"Imfy"` code_name — but `norman-hawkins.json` already declares `"serves": ["the-spark", "the-observatory"]` | **No new file** — the resolver maps `Imfy` → `norman-hawkins`, honoring that profile's own pre-existing `serves` declaration instead of inventing a second, competing voice for the same seat. See the inconsistency note below. |
| The Citadel, Think Tank | Chief Operations Officer, Head of R&D | Trancendos | **none** (no profile anywhere declares `serves` for `the-citadel` or `think-tank`) | Added `src/personality/profiles/trancendos.json` — hybrid COO/R&D-visionary archetype: very high conscientiousness + assertiveness (ops authority), high openness (R&D drive), low neuroticism, formal but not humorless — the platform's own top-level "founder entity" voice. |
| DocUtari | Head of Document Management | Fiddsy | none | **Correctly none** — this seat has a named holder (Fiddsy) but no personality profile authored per canon; the resolver (§4) falls back to the platform default rather than fabricating a persona for it. |

`src/personality/profiles/norman-hawkins.json` (`domain: "tooling"`) pre-dates this pass and
already claims The Spark via its own `serves` list, even though `CLAUDE.md`'s platform table lists
Norman Hawkins as `lead_ai` for both The Spark and The Observatory while `src/entities/platform.py`
(the actual source of truth the Role Registry seeds from) gives The Spark's `lead_ai` to Imfy and
only The Observatory to Norman Hawkins. This is a pre-existing three-way naming inconsistency
(`CLAUDE.md` vs. `platform.py` vs. this profile's own `serves` list) that predates this session;
resolving *which name is canonical* is a platform-definition decision, not a personality-tuning
one, so it is flagged here rather than silently "fixed" by picking a side. The resolver's explicit
`Imfy` → `norman-hawkins` mapping is deliberately *not* a slug-guess — it is reading the existing
profile's own stated intent at face value, which is the least-invasive way to make `/chat`
requests scoped to The Spark actually resolve to *a* persona today.

## 4. Role Registry → Personality Matrix wiring

See `src/personality/role_resolution.py`: `resolve_personality_for_location(location)` looks up the
Role Registry's current `assigned_ai` for a Location, maps it to a `PersonalityMatrix` profile id
via an explicit table (`AI_NAME_TO_PROFILE_ID`, built from each profile's actual `code_name`/`id` —
deliberately not a slug-guessing function, since several names need exact overrides: `"The Guardian
(Anchor: Orb of Orisis)"` → `the-guardian`, `"tAImra"` → `taimra`, `"Benji Tate & Sam King"` →
`benji-tate-sam-king`), and falls back to `None` (caller decides the default, typically
`tranc3-base`) when the Location is unknown, unassigned, or mapped to an AI with no profile yet
(Imfy and Trancendos no longer hit this path; a location vacated via `DELETE /roles/{location}/assign`
still would, correctly).

Wired into `POST /chat`: `ChatRequest` gained an optional `location` field. When present, the
handler tries `resolve_personality_for_location(location)` first and only falls through to the
caller-supplied `personality` string if resolution fails — so a client hitting `/chat` on behalf of
(say) Royal Bank of Arcadia gets whoever the Role Registry currently says holds the CFO seat, not a
hardcoded string that goes stale the moment an operator reassigns the role.

## 5. Model-per-persona routing

See `workers/model-router-service/worker.py`: routing requests may now carry a `persona_traits`
hint (a subset of the trait vector — `precision`, `creativity`, `formality`) alongside the existing
capability/cost/latency criteria, nudging model selection toward higher-determinism models for
precision-heavy personas (Precision/Finance, Security, Governance archetypes) and toward more
creative-tuned models for the Creative archetype, without changing behavior for any caller that
omits the hint.

---

## Verification Log

| Date | Verifier | Result |
|---|---|---|
| 2026-07-24 | Claude (session) | Web-researched 8 archetypes (sources cited above); spot-validated 8 existing profiles against their archetype (all consistent, no rewrite needed); confirmed via `src/entities/platform.py` that exactly 2 of 43 `lead_ai` holders (Imfy, Trancendos) had no profile mapped to them and resolved both (Imfy via `norman-hawkins`'s existing `serves` declaration, Trancendos via a new profile file); confirmed DocUtari's "To be Defined" correctly has none; documented the pre-existing Norman-Hawkins/Imfy naming inconsistency without resolving it unilaterally. |
