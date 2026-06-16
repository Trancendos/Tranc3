## 2024-06-16 - Icon-only buttons accessibility
**Learning:** Added `aria-label`s to multiple icon-only buttons across the Dashboard component (`Close`, `Expand/Collapse`, `Refresh`, `Notifications`, `Settings`) to fix accessibility issues. Even minor structural changes might require re-evaluating the full suite of `devDependencies` if test files rely on specific versions, but unnecessary dependencies should not be committed.
**Action:** Ensure ARIA attributes are added to all icon-only buttons without modifying other functionality or needlessly committing lockfile updates.
