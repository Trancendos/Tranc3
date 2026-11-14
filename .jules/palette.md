## 2024-05-24 - Fix Keyboard Accessibility for Hidden Icons
**Learning:** When hiding icons or elements using `opacity-0 group-hover:opacity-100`, keyboard users cannot see the icon when they tab to the parent element, unless `group-focus-visible:opacity-100` is added. It is also important to add `focus-visible` outline styles to the parent interactive element.
**Action:** Always add `group-focus-visible:opacity-100` to hidden secondary icons and `focus-visible:outline-none focus-visible:ring-2` to the interactive parent container to ensure graceful keyboard accessibility.
