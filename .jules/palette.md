## 2024-05-18 - Input Fields Associated Labels
**Learning:** The application possessed unassociated form inputs for features like editing the workflow name inline or modifying Node labels within the Digital Grid view, causing accessibility issues because screen readers require labels or titles to announce input context.
**Action:** Ensure inline inputs have 'aria-label' or 'title' attributes if visually hidden labels are necessary, and verify explicitly visible labels properly use 'htmlFor' and match target 'id's on inputs.
