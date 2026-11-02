## 2026-10-26 - AdaptiveCard Keyboard Accessibility
**Learning:** When making standard `<div>` elements interactive via `onClick`, they lack inherent keyboard accessibility. Always add `role="button"`, `tabIndex={0}`, `onKeyDown` (for Enter/Space), and visible focus states (`focus-visible:ring-2`) to ensure they can be used by keyboard-only and screen reader users.
**Action:** Add these attributes to any custom interactive component that doesn't use semantic HTML elements like `<button>` or `<a>`.
