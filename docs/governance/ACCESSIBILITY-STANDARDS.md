# Accessibility Standards

> **What this is.** Before this document, real accessibility engineering already existed in the
> frontend — a live-region announcer, a keyboard focus trap, a route-change announcer, a keyboard
> shortcuts help modal, and 15 Radix UI primitives with strong built-in ARIA semantics — but
> nothing tied it to a stated conformance target, a review process, or a list of what still needs
> auditing. This document is that missing baseline, not a claim that accessibility work is
> starting from zero.

**Owner:** Fabulousa (Baron Von Hilton) · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. What already exists — verified against the real frontend

`web/src/` (React 18 + TypeScript + Tailwind, 62 components across `components/ux/`, `shadcn/`,
`ui/`, and `workflow/`):

| Mechanism | Code | What it does |
|---|---|---|
| Live-region announcer | `components/GlobalAccessibility.tsx` | A `role="status" aria-live="polite"` region mounted once at app root; screen readers hear updates without focus changes |
| Route-change announcement | `hooks/useRouteAnnouncer.ts` | On every client-side navigation, announces "Navigated to {page label}" via the live region above — SPAs are otherwise silent to screen-reader users on route change |
| Page title sync | `hooks/usePageTitle.ts` | Keeps `document.title` in sync with the current route, matching the announced label |
| Keyboard focus trap | `hooks/useFocusTrap.ts` | Traps Tab/Shift+Tab inside a modal/dialog container, restores focus to the triggering element on close, wired to Escape |
| Keyboard shortcuts help | `components/KeyboardHelpModal.tsx` | `?`-triggered modal documenting every keyboard shortcut in the app, itself using `useFocusTrap` |
| Component primitives | 15 `@radix-ui/*` packages (`web/package.json`) | Radix's accessible-by-default dialog/dropdown/tabs/etc. primitives underlie `components/shadcn/` and `components/ui/` |
| Visual regression + a11y checks (dev-time) | `@storybook/addon-a11y` (Storybook 10.4.6, `web/src/stories/`) | Runs axe-core checks against stories in the Storybook UI — **not currently wired into a CI gate** (§3) |

Grep confirms 61 files under `web/src/` use `aria-*`/`role=` attributes directly, on top of what
Radix supplies internally.

## 2. What this document adds: a stated target

No prior document set an actual conformance target. This platform's target, effective from this
document's version:

**WCAG 2.1 Level AA** for all pages under `web/src/pages/` reachable without authentication, and a
good-faith target (not yet audited) for authenticated dashboard views.

This is a target, not a certification — see §3 for the honest gap between target and verified
state.

## 3. Honest gap: target vs. verified state

- **No CI-enforced automated check exists yet.** `@storybook/addon-a11y` runs axe-core against
  individual component stories when a developer opens Storybook locally, but neither
  `.forgejo/workflows/` nor `.github/workflows/` runs it (or any axe-core/pa11y pass) as a gate.
  Closing this is the single highest-value next step — wiring `addon-a11y`'s check into
  `.forgejo/workflows/ci.yml`'s existing frontend job.
- **No manual audit has been performed** against real assistive technology (NVDA/JAWS/VoiceOver)
  on any page. The mechanisms in §1 are correctly implemented by inspection, not verified by a
  screen-reader pass.
- **No colour-contrast audit** has been run against `web/src/trancendos/tokens.ts`'s palette.

## 4. Process going forward

1. New interactive components should reuse `useFocusTrap` for any modal/dialog rather than
   reimplementing focus management.
2. New routes should have an entry in `config/routeMeta.ts` so `useRouteAnnouncer` announces them
   correctly — an unlabelled route falls back to a slug-derived label, which is functional but not
   ideal.
3. Any `components/shadcn/` or `components/ui/` addition should prefer the underlying Radix
   primitive over a bespoke implementation, to inherit its ARIA semantics.
4. Before this doc's next revision, wire `addon-a11y` into CI (§3) and run one real
   assistive-technology pass on the top 5 pages by traffic, once that data exists.

## 5. Cross-references

- `docs/DESIGN_SYSTEM.md` — backend entity/tier naming conventions (a different "design system",
  not frontend UX/UI — see `UX-UI-DESIGN-MATRIX.md` §1 for the disambiguation)
- `docs/governance/UX-UI-DESIGN-MATRIX.md` — the broader UX/UI standards this accessibility
  baseline sits under
- Fabulousa (`workers/fabulousa-service/`) — the named owner of UX/UI/design across the platform
