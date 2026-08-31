## 2026-05-29 - Add ARIA Labels and Form Associations
**Learning:** The application lacked some basic accessibility features, specifically ARIA labels for icon-only buttons and associated labels for form inputs. These are critical for screen reader compatibility.
**Action:** Add ARIA labels to all icon-only buttons and ensure all form inputs have associated labels with 'id' and 'htmlFor' attributes.
## 2024-05-17 - Empty State Prompts Reduce Friction
**Learning:** Adding clickable suggested prompts to empty chat states significantly improves user onboarding. It eliminates "blank canvas" paralysis and guides users toward successful initial interactions with the AI.
**Action:** Always include contextual, clickable suggested prompts in empty states for conversational interfaces, ensuring they auto-focus the main input to encourage immediate action.

## 2026-06-05 - Icon-only Controls Navigation
**Learning:** The Trancendos dashboard (master OS) contains a lot of dense operational metrics and several icon-only control buttons (e.g. settings, notifications, refresh, close panels) that lack critical accessibility context. It also has complex sidebar navigation elements that rely purely on visual hover cues rather than explicit focus states.
**Action:** Audit and add explicit `aria-label` attributes to all icon-only interactions and ensure uniform keyboard navigation by applying `focus-visible:ring-2 focus-visible:ring-blue-500` to them so they are accessible and visually noticeable during tabbed navigation.
## 2024-05-19 - Added confirmation to destructive actions
**Learning:** Destructive actions without a confirmation prompt can easily result in accidental data loss for users when they click icon-only buttons like the trash can by mistake.
**Action:** Always wrap destructive actions (like deleting API keys) in a confirmation dialogue (e.g. `window.confirm`) to prevent accidental deletion, and ensure icon-only buttons have descriptive `title` tooltips for clarity on hover.
## 2024-05-18 - Missing ARIA labels pattern in modal dismiss buttons
**Learning:** Found an accessibility pattern specific to this app's components: various custom implementation of modal/panel components (`DigitalGridPage.tsx`, `ExecutionPanel.tsx`, `Dashboard.tsx`) have icon-only "✕" dismiss/close buttons without `aria-label`s or keyboard focus rings, leading to accessibility violations with screen readers.
**Action:** Always verify newly created floating panels or sidebars include proper keyboard-navigable and screen-reader compliant close buttons with `focus-visible` utilities.

## 2024-05-15 - [Icon-only Buttons Accessibility]
**Learning:** Icon-only buttons without explicit text fail `axe-core` accessibility tests.
**Action:** Always add an `aria-label` attribute to icon-only buttons to provide an accessible name for screen readers, and add `aria-hidden="true"` to the inner SVG elements to avoid redundant announcements.
## 2026-07-16 - Prevent Accidental Data Loss on Destructive Actions
**Learning:** The application contained several destructive actions (e.g. deleting keys, flushing cache, dissolving swarms, resetting buckets) that executed immediately upon clicking icon-only buttons, making it easy for users to accidentally cause data loss or system state changes.
**Action:** Always wrap destructive API calls with `window.confirm` dialogues to ensure intentionality, and add descriptive `title` tooltips to icon-only buttons to clarify their function before interaction.
## 2024-08-24 - Interactive Elements in Hover-Only Containers
**Learning:** Hiding card actions (like Delete or Run buttons) behind `opacity-0 group-hover:opacity-100` completely breaks keyboard navigation because focusable elements remain invisible when users tab to them.
**Action:** Always pair `group-hover:opacity-100` with `focus-within:opacity-100` on the container so actions reveal themselves gracefully when any child receives keyboard focus.

## 2024-05-20 - Ensure Decorative Elements Reveal on Focus
**Learning:** Decorative elements tied to hover states (like the animated gradient on the Landing Page button or the External Link icon on the Dutchy Page) that are revealed using `group-hover:opacity-100` remain invisible when keyboard users navigate to the parent element, depriving them of visual context.
**Action:** Always pair `group-hover:opacity-100` with `group-focus:opacity-100` for decorative child elements when the parent wrapper is naturally focusable (like a `<button>` or `<a>` with the `group` class) so the visual enhancements appear equally for both mouse and keyboard users. Do not use `tabIndex={0}` on non-interactive semantic elements just to force focus.
