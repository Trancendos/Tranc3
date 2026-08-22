# Documentation Category Info — Template

> Copy this file into any new `docs/<category>/` directory you create, rename it
> `_category_info.md`, and fill in the placeholders. It documents the purpose of
> the category and the frontmatter contract every document in this repo follows.

## How to use this template

1. Place `_category_info.md` at the root of a documentation category directory.
2. Give the category one of the seven canonical names:

   - **Getting Started** — README, quick start, prerequisites
   - **Architecture** — threat model, topology, blueprints, service maps
   - **Development** — contributing, testing, CI/CD
   - **Deployment** — deployment guide, runbooks, production readiness
   - **Security** — threat model, alert register, assessments
   - **Operations** — runbooks, troubleshooting, monitoring
   - **Reference** — API reference, entity catalog, compliance

3. Every markdown file in this repo MUST carry YAML frontmatter:

   ```markdown
   ---
   title: "Human-Readable Document Title"
   category: <one of the seven canonical categories>
   last-reviewed: YYYY-MM-DD
   status: complete | wip | needs-update
   ---
   ```

   - `title` — the document's display name (surround with quotes if it contains `:`).
   - `category` — must match a canonical category above.
   - `last-reviewed` — date the content was last verified against the codebase.
   - `status`:
     - `complete` — reviewed and accurate
     - `wip` — actively being written
     - `needs-update` — accuracy not yet verified

4. After adding or moving docs, regenerate the navigation hub:

   ```bash
   python scripts/generate_doc_index.py
   ```

   This rewrites `docs/DOC_INDEX.md` and back-fills frontmatter on any file that
   lacks it.

## This category

- **Name:** <canonical-category>
- **Purpose:** <one sentence on what lives here>
- **Audience:** <who reads these docs>
