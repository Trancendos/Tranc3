## 2024-05-14 - Keyboard Interaction in Custom Buttons
**Learning:** When making non-button elements (like a dropzone) act as a button via keyboard events, listening to the "Space" key without calling `e.preventDefault()` causes the default browser behavior of scrolling down the page, which breaks the UX. Also, elements should not be focusable (i.e. tabIndex should be -1) if they are disabled.
**Action:** Always call `e.preventDefault()` on "Space" key events when simulating a button click, and dynamically set `tabIndex={disabled ? -1 : 0}` based on the disabled state.
