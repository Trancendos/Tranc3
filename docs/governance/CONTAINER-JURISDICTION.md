# Container Jurisdiction, Contents and Custody

> **What this is.** The owner's model for containerisation: every container has a shared
> jurisdiction — the Location or AI whose code runs inside it, and The Ice Box as custodian of
> its containment — plus a requirement that what is inside each container be logged. This
> document settles the SBOM question the owner raised, defines the jurisdiction split, and
> records what is measured today.
>
> **Code:** `src/cmdb/containers.py`, `scripts/build_container_sboms.py`, `scripts/build_ci_register.py`
> **Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Set:** 2026-09-11

---

## 1. The SBOM question, answered

> *"Anything within a container needs to be also logged... A few AI's have said mark these as
> SBOMs but I'm not sure."*

The uncertainty is well placed, because the advice is half right and the missing half is the
part that matters.

**An SBOM is the right artifact for the contents.** It is a standard, machine-readable inventory
of every component in an image — name, version, licence, hash. CycloneDX and SPDX are the two
formats; **CycloneDX** is the one to use here, because it is security-oriented and can also
describe *services*, which this platform's Locations are.

**An SBOM is not a substitute for a Configuration Item, and cannot be.** They answer different
questions:

| | SBOM | Configuration Item |
|---|---|---|
| Answers | What components are in this thing | What is this thing, who answers for it, what does it connect to |
| Has an owner | No | Yes — that is most of the point |
| Has a lifecycle state | No | Yes |
| Has relationships | Only component→component | Yes — depends-on, runs-on, custodied-by |
| Changes are governed | No | Yes |
| Good at | "Is CVE-2026-x in my estate" | "Who do I call, and what breaks if I stop it" |

So the model used here is **both, joined**: the container is registered as a CI, and its SBOM is
referenced from that CI as the evidence of its contents. Marking containers *only* as SBOMs would
produce an estate that can answer a CVE question and cannot answer an ownership one.

### Two kinds of SBOM, and why the distinction is enforced in code

- **Image SBOM** — generated from a built image (syft, trivy). Sees OS packages from the base
  layer, system libraries, everything added by every `RUN`. This is the one that answers CVE
  questions properly.
- **Source SBOM** — generated from the dependency manifests in the repository. Sees declared
  application dependencies only. No base-image packages. No transitive resolution.

`scripts/build_container_sboms.py` currently emits **source SBOMs**, and stamps every document
with `trancendos:sbom-scope = source` plus a note saying exactly what it did not look at. It does
this because syft and trivy are not present in every environment, and an honestly-labelled
partial inventory is worth more than an empty directory — but a source SBOM presented as a
complete one would let a container with an unexamined base layer read as fully inventoried.
`--strict` refuses to emit source SBOMs at all, for once image SBOMs exist.

## 2. Shared jurisdiction

> *"All containerisations should have a shared jurisdiction, The Location or AI that's within
> the container and a shared responsibility to the IceBox."*

Two fields on every container CI, never merged:

| Field | Means | Can be unknown? |
|---|---|---|
| `jurisdiction` | The Location whose code runs in this container — accountable for **what it does** | Yes → `_unrouted_` |
| `custodian` | **The Ice Box**, always — accountable for **that it runs safely**: isolation, resource limits, sandbox and VM stability | **No** |

The asymmetry is deliberate. 86 of the estate's containers are third-party images running
nobody's code here, so their jurisdiction is genuinely unknown. Their containment is not. Keeping
the fields separate lets the register say "we do not know whose this is" without also saying
"nobody is responsible for it" — which is what a single merged owner field would have said.

## 3. What is measured today

From `scripts/build_ci_register.py`, regenerated on each run:

| | Count |
|---|---:|
| Containers registered as CIs | 174 |
| — built from our Dockerfiles | 88 |
| — pulled third-party images | 86 |
| With a resolved jurisdiction | 46 |
| With `_unrouted_` jurisdiction | 128 |
| With a custodian | **174** |
| With a source SBOM | 174 |
| With an **image** SBOM | **0** |
| Built images running as root (no `USER`) | 1 |

The last two rows are the honest findings. Every container has a contents inventory, and none of
those inventories has looked inside a base image. `.github/workflows/anchore-syft.yml` runs Syft
on push to main against a single build — it is not per-container coverage, and it should not be
read as such.

## 4. The Ice Box as management centre

`workers/ice-box-service/` is 247 lines offering `/scan`, `/quarantine` and `/stats`. The owner's
model makes it the management centre for sandboxes, VMs and containers across Docker, Podman and
Kubernetes. The gap between those two sentences is the work, and it is real: the Ice Box today
quarantines artifacts, and does not know that 174 containers exist.

The build order that follows from what is now measured:

1. **Inventory** — the Ice Box reads the container CIs. Done: the register exists.
2. **Image SBOMs** — syft against each built image in CI, replacing source SBOMs where available.
   Image SBOMs are what make step 3 meaningful.
3. **Runtime scanning** — trivy/grype against images and running containers; findings land on the
   container CI, so a vulnerability has an owner and a custodian the moment it is found.
4. **Runtime posture** — the containment facts the Ice Box is custodian of: runs-as-root,
   privileged, host mounts, capability sets, missing resource limits. One is already measured;
   the rest need the runtime, not the compose file.
5. **Podman and Kubernetes** — the same CI shape for pods and for Podman containers. The CI class
   stays `Container`; the runtime becomes an attribute rather than a separate register.

Steps 3–5 are Action 2 of the owner's five Actions, and this document is where that Action lands:
in the Location the platform already designated for sandbox isolation, rather than in a new one.

## 5. Related

- `docs/governance/DATA-PLATFORM-STRATEGY.md` — the datastore half of the same CMDB work
- `docs/governance/IMMUNE-SYSTEM.md` — the sensor model these scanners must register under,
  including the rule that a sensor which cannot see must report that it could not see
- `docs/architecture/ci-register.json` — the generated register
- `docs/architecture/sbom/` — one CycloneDX document per container

## Sources

- [CycloneDX — Software Bill of Materials](https://cyclonedx.org/capabilities/sbom/)
- [SPDX vs CycloneDX: Choosing the Right SBOM Format](https://www.herodevs.com/blog-posts/spdx-vs-cyclonedx-choosing-the-right-sbom-format-for-your-software-supply-chain)
- [CycloneDX and SPDX for Kubernetes: A Practical Guide to SBOMs](https://www.plural.sh/blog/cyclonedx-spdx-kubernetes/)
- [Open-Source Container Security: Trivy, Clair, and Grype](https://www.stakater.com/post/open-source-container-security-a-deep-dive-into-trivy-clair-and-grype/)
- [Using Grype to scan software artifacts — Chainguard Academy](https://edu.chainguard.dev/chainguard/chainguard-images/staying-secure/working-with-scanners/grype-tutorial/)
