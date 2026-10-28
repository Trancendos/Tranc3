## 2024-05-18 - Keyboard Accessibility for Hover-Revealed Elements
**Learning:** Tailwind's `group-hover` pattern for revealing secondary icons (like external links or background gradients) is often inaccessible to keyboard users because hover states don't trigger on focus.
**Action:** When hiding secondary actions or decorative indicators using `opacity-0 group-hover:opacity-100`, always add `group-focus-visible:opacity-100` to the hidden element, and ensure the interactive parent container has `focus-visible` styles (e.g., `focus-visible:ring-2`) to appear gracefully on keyboard focus.
