# Service Doc-Pack — Arcadia (Post-Login Front-End Hub)

| Field | Value |
|---|---|
| **Entity** | Arcadia (`PID-ARC`) |
| **Lead AI** | Lilli SC (`AID-ARC-01`); Prime: Dorris Fontaine |
| **Status** | 🔧 Partial (per `CLAUDE.md` service table) |
| **Code** | `web/` (package `tranc3-web`) |
| **Serve** | static SPA via Nginx on port **8080** (`web/nginx.conf`, `web/Dockerfile`) |
| **Gate tier** | Partial → GOV + RACI + TFM + POL + STD + DDD scoped to the front-end that exists |

> **Truthfulness:** claims cite `web/` (stack from `package.json`, structure from `web/src/`, serving from
> `web/nginx.conf`). Screens beyond those present in `web/src/` (e.g. full forum/email UI implied by the
> role) are described as **intended**, not verified. Status owned by the `CLAUDE.md` service table;
> identity by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** the post-login front-end — the user-facing app (forum & email hub per role) served as a
  static single-page app.
- **Owner (RACI-A):** Lilli SC (Lead AI); Prime Dorris Fontaine.
- **Scope (in-repo):** a React SPA (`tranc3-web`) plus its Nginx serving config. Supporting back-end
  workers under `PID-ARC` — `notifications` (8008) and `email-service` (8022, per the compose-aligned
  `CLAUDE.md` worker map) — are separate services.

## 2. Detailed Design Document (DDD) — `web/`

### Stack (`web/package.json`)
- **React 18** + **TypeScript**, built with **Vite** (`dev: vite`, `build: tsc && vite build`).
- State: **Zustand**. UI: **Radix UI** primitives (dialog, dropdown, tabs, toast, tooltip, select, …) +
  **Tailwind CSS** + **lucide-react** icons. Storybook stories present (`web/src/stories`).

### App structure (`web/src/`)
- Entry: `main.tsx` → `App.tsx`; routing in `AppRouter.tsx`.
- Verified top-level views/components: `LoginPage.tsx`, `ChatView.tsx`, `UpgradeModal.tsx`, plus
  `pages/`, `components/`, `contexts/`, `hooks/`, `store/` (Zustand), `config/`, `lib/`, `types/`,
  `trancendos/`, and `test/`. Design tokens in `ux-system.css` / `index.css`.

### Serving (`web/nginx.conf`, `web/Dockerfile`)
- Nginx `listen 8080`, `root /usr/share/nginx/html`; SPA fallback `try_files $uri $uri/ /index.html`;
  cached `/assets/`; `/healthz` endpoint; security headers (e.g. `Permissions-Policy` disabling
  camera/microphone/geolocation).

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** static SPA — build once (Vite), serve the bundle from Nginx; no server-side rendering.
- **Decision:** client-side routing with an Nginx SPA fallback; state in Zustand (lightweight) rather than
  a heavier store; UI composed from accessible Radix primitives + Tailwind.

## 4. RACI Matrix

| Activity | Lilli SC (Lead) | Dorris Fontaine (Prime) | Platform Owner | The Observatory |
|---|---|---|---|---|
| Front-end app (`web/`) | **R/A** | C | C | I |
| Static serving / Nginx | **R** | C | C | I |
| Supporting workers (notifications/email) | C | **A** | C | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** authenticated users (via Infinity) land here post-login; the SPA calls platform APIs.
- **Downstream:** `notifications` (8008) and `email-service` (8022) back the comms features.
- **Auth boundary:** the SPA is a public bundle; auth is enforced by the APIs it calls, not the static host.

## 6. Architecture Scalability Document (ASD)

- **Load model:** static assets scale trivially (CDN/Nginx cache); load is on the back-end APIs, not the SPA.
- **Zero-cost limits & hard stops:** static hosting via Nginx; no paid front-end platform.
- **Growth path:** code-split routes as `pages/` grows; the bundle is already Vite-optimised.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Framework | React 18 + TypeScript | OSS |
| Build | Vite (`tsc && vite build`) | OSS |
| State | Zustand | OSS |
| UI | Radix UI + Tailwind + lucide-react | OSS |
| Serve | Nginx static (port 8080) | OSS |

## 8. Policy (POL)

- No secrets in the client bundle; auth handled server-side. Security headers set in `nginx.conf`.
  Reuses platform policy (`POL-AI-001`, `docs/defstan/`).

## 9. Procedure (PROC)

- **Local dev:** `pnpm dev` (Vite). **Build:** `pnpm build` (`tsc && vite build`) → static bundle served by
  the `web/Dockerfile` Nginx image. Add routes in `AppRouter.tsx` + `pages/`.

## 10. Runbook (RUN)

- **Blank page / 404 on deep links:** SPA fallback misconfigured — confirm `try_files ... /index.html` in
  `nginx.conf`.
- **`/healthz` fails:** the Nginx container isn't serving — check the `web/Dockerfile` build/static assets.
- **Stale assets after deploy:** `/assets/` is cached — ensure Vite content-hashed filenames (default).

## 11. Standards (STD)

- TypeScript strict build (`tsc` before `vite build`); accessible Radix primitives; security headers on the
  static host; no client-side secrets.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `web/package.json` (React 18/Vite/Zustand/Radix/Tailwind), `web/src/` structure, `web/nginx.conf` (8080, SPA fallback, `/healthz`, headers) | Stack, app structure, and serving verified against `web/`; role-level forum/email screens marked intended, not verified |
