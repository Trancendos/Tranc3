## 2026-05-29 - Add ARIA Labels and Form Associations
**Learning:** The application lacked some basic accessibility features, specifically ARIA labels for icon-only buttons and associated labels for form inputs. These are critical for screen reader compatibility.
**Action:** Add ARIA labels to all icon-only buttons and ensure all form inputs have associated labels with 'id' and 'htmlFor' attributes.

## 2026-05-30 - Context-Aware Loading and Focus States
**Learning:** Screen reader users needed better cues for async form submissions than plain "...". Also discovered that default focus outlines were inadequate for keyboard navigation and missing on mode toggles.
**Action:** Use context-aware loading text (e.g. "Signing In...") combined with `aria-busy` and `aria-live` on submit buttons. Standardize keyboard navigation by applying `focus-visible:ring-2` to inputs, buttons, and tabs.

## 2024-05-17 - Empty State Prompts Reduce Friction
**Learning:** Adding clickable suggested prompts to empty chat states significantly improves user onboarding. It eliminates "blank canvas" paralysis and guides users toward successful initial interactions with the AI.
**Action:** Always include contextual, clickable suggested prompts in empty states for conversational interfaces, ensuring they auto-focus the main input to encourage immediate action.

## 2026-06-05 - Icon-only Controls Navigation
**Learning:** The Trancendos dashboard (master OS) contains a lot of dense operational metrics and several icon-only control buttons (e.g. settings, notifications, refresh, close panels) that lack critical accessibility context. It also has complex sidebar navigation elements that rely purely on visual hover cues rather than explicit focus states.
**Action:** Audit and add explicit `aria-label` attributes to all icon-only interactions and ensure uniform keyboard navigation by applying `focus-visible:ring-2 focus-visible:ring-blue-500` to them so they are accessible and visually noticeable during tabbed navigation.
## 2026-06-07 - Added focus-visible classes to Spark Dashboard
**Learning:** Adding focus-visible classes to custom elements such as interactive tabs and buttons provides improved visual cues for keyboard navigation without relying on inline styling adjustments.
**Action:** Always include focus-visible utility classes when writing custom, styled interactive elements to ensure full keyboard navigation support and WCAG compliance.
