## 2026-11-06 - Interactive Div Accessibility
**Learning:** When using non-semantic elements like `div` or `span` as interactive buttons (e.g. AdaptiveCard), it's easy to forget keyboard users. If an element has an `onClick` handler, it also requires `role="button"`, `tabIndex={0}`, an `onKeyDown` handler (listening for Enter or Space and calling preventDefault), and distinct focus styles (`focus-visible`).
**Action:** Always verify keyboard accessibility (`tabIndex`, `onKeyDown`, and `focus-visible`) when making a standard HTML element interactive in custom UI components.
