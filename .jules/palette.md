## 2024-05-29 - Making onClick divs accessible
**Learning:** When making non-semantic HTML elements like `<div>` interactive via an `onClick` prop, it's a common oversight to forget keyboard navigation and screen reader support, leaving out `role="button"`, `tabIndex={0}`, and an `onKeyDown` handler.
**Action:** Always verify that interactive `<div>` components include `role`, `tabIndex`, `onKeyDown` (for Enter/Space), and visible focus states (e.g., `focus-visible:ring-2`) to ensure full keyboard and screen reader accessibility.
