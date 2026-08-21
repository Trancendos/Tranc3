---
title: "UX/UI Design Matrix"
category: Reference
last-reviewed: 2026-07-30
status: needs-update
---

# UX/UI Design Matrix

> **What this is.** Consolidates three separately-requested documents — a UX Standards Matrix, a
> UI Standards Matrix, and a Design Matrix — into one, because splitting them would fragment an
> already-thin area rather than clarify it. A fourth request (a "Component Matrix") folds in here
> too, as §3's catalog of the 62 real components under `web/src/components/`.

**Owner:** Fabulousa (Baron Von Hilton) · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Not to be confused with `docs/DESIGN_SYSTEM.md`

`docs/DESIGN_SYSTEM.md` already exists and is titled "Design System," but it documents the
**backend entity tier hierarchy** (T1–T5 base classes, `TrancOne`/`T2ance`/`Tranc3`/`InfinityAgent`/
`InfinityBot`, ID prefixes) — naming conventions for AI orchestration code, not frontend visual
design. This document is the actual frontend UX/UI standard; the two are unrelated despite the
name collision, and neither should be merged into the other.

## 2. Design tokens — what's real (`web/src/trancendos/tokens.ts`)

A single source-of-truth token file (325 lines) already backs the frontend:

- **`colors`** — brand palette (primary/secondary/accent/surface/elevated/border), 10 **pillar**
  colors (architectural, creativity, development, commercial, knowledge, security, devops,
  wellbeing, foresight, governance), and per-hub colors for ~20 named Locations (The Nexus, The
  Observatory, Infinity, The Void, etc.) — each hub's colour derives from its pillar but is
  distinct.
- **`typography`**, **`layout`**, **`animation`** — shared scale constants.
- **`hubIcons`** — icon mapping per Location.
- **`pillars`** — structured pillar definitions (`PillarDef[]`).

Theme switching (`web/src/contexts/ThemeContext.tsx`) supports `dark`/`light`, persisted to
`localStorage`, defaulting to the OS `prefers-color-scheme`.

**Standard going forward:** any new UI surface must consume `tokens.ts` values (via Tailwind's
CSS custom properties) rather than hardcoding colours/spacing — this is the one binding rule this
document adds; everything below is descriptive of what already exists.

## 3. Component catalog (62 components, 4 directories)

| Directory | Count | Purpose |
|---|---|---|
| `components/shadcn/` | 15 | shadcn/ui-derived primitives (button, card, dialog, tabs, input, label, separator, badge) plus domain-specific cards (`document-card`, `threat-card`, `workflow-card`, `security-engine-status`, `workflow-engine-status`, `pdf-ops-panel`, `upload-zone`) |
| `components/ux/` | 27 | Interaction-pattern components — the largest group. Covers progressive disclosure (`ProgressiveDisclosure`, `AccordionCluster`, `SelectiveList`), feedback (`ToastCluster`, `CelebrationWrapper`, `MicroInteraction`), state indicators (`StatusIndicator`, `SkeletonCell`, `ProgressBar`, `StepIndicator`), layout adaptation (`AdaptiveGrid`, `ChunkedGrid`, `FlowZone`), and a11y-adjacent primitives (`FocusTrap`, `ShortcutLayer`, `ContrastBadge`) |
| `components/ui/` | 9 | Realtime/platform-state widgets — `PlatformPulse`, `RealtimeStatusBar`, `NotificationBell`, `SmartWidget`, `AdaptiveCard`, `LiquidCard`, `FluidContainer`, `StatusBadge`, `Toast` |
| `components/workflow/` | 5 | The Digital Grid's visual editor — `WorkflowCanvas`, `NodePalette`, `ExecutionPanel`, `WorkflowDashboard`, `DigitalGridPage` |
| `components/` (root) | 6 | App-shell — `Layout`, `NavBar`, `AuthGuard`, `ErrorBoundary`, plus the two accessibility components covered in `ACCESSIBILITY-STANDARDS.md` (`GlobalAccessibility`, `KeyboardHelpModal`) |

`components/ux/`'s naming (Cluster/Shield/Zone/Layer suffixes) is a real, consistent internal
vocabulary — new components in this directory should follow it rather than introducing a new
naming pattern.

## 4. What's aspirational, not yet built

- **Penpot integration** (per `CLAUDE.md`'s "Recommended Open Source Foundations" table) —
  Fabulousa's planned design-tool backend. Not started; `workers/fabulousa-service/worker.py` has
  no Penpot API calls today.
- **A published Storybook site** — `web/src/stories/` exists with real story files
  (`Button.stories.ts`, `Cryptex.stories.tsx`, `DocUtari.stories.tsx`, etc.) and
  `@storybook/addon-a11y`/`addon-docs`/`addon-vitest` are installed, but there's no evidence of a
  published/deployed Storybook instance — it currently runs locally only.
- **A formal component contribution guide** (props conventions, when to add to `ux/` vs `ui/` vs
  `shadcn/`) — the directory split above is inferred from existing code, not written down
  anywhere until this document.

## 5. Cross-references

- `docs/DESIGN_SYSTEM.md` — the differently-scoped backend entity-tier doc (§1)
- `docs/governance/ACCESSIBILITY-STANDARDS.md` — accessibility-specific standards and gap list
- Fabulousa (`workers/fabulousa-service/`, port 8048) — named platform owner of this area
