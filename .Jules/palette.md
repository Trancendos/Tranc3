## 2026-05-29 - Add ARIA Labels and Form Associations
**Learning:** The application lacked some basic accessibility features, specifically ARIA labels for icon-only buttons and associated labels for form inputs. These are critical for screen reader compatibility.
**Action:** Add ARIA labels to all icon-only buttons and ensure all form inputs have associated labels with 'id' and 'htmlFor' attributes.
## 2024-05-17 - Empty State Prompts Reduce Friction
**Learning:** Adding clickable suggested prompts to empty chat states significantly improves user onboarding. It eliminates "blank canvas" paralysis and guides users toward successful initial interactions with the AI.
**Action:** Always include contextual, clickable suggested prompts in empty states for conversational interfaces, ensuring they auto-focus the main input to encourage immediate action.

## 2026-05-30 - Context-Aware Loading and Focus States
**Learning:** Screen reader users needed better cues for async form submissions than plain "...". Also discovered that default focus outlines were inadequate for keyboard navigation and missing on mode toggles.
**Action:** Use context-aware loading text (e.g. "Signing In...") combined with `aria-busy` and `aria-live` on submit buttons. Standardize keyboard navigation by applying `focus-visible:ring-2` to inputs, buttons, and tabs.
