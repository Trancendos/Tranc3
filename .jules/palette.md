## 2024-11-04 - Prevent Default Scroll for Custom Interactive Elements
**Learning:** When making non-button elements (like a dropzone acting as a button) interactive via `onKeyDown`, triggering actions with the 'Space' key will cause the browser to scroll down the page by default, which can be disorienting.
**Action:** Always call `e.preventDefault()` inside `onKeyDown` handlers for the 'Space' key on custom interactive elements (role="button", etc.) to prevent default browser scrolling, and ensure `tabIndex` correctly responds to the disabled state (`tabIndex={disabled ? -1 : 0}`).
