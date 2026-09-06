## 2026-09-04 - Fast C-Level Iterator Math Replaces Python Loops
...first, otherwise it gets exhausted silently and yields wrong results (e.g. 0 once exhausted, or shifted products when the same exhausted/consumed iterator is passed twice).
**Action:** When migrating math logic away from native loops or `zip()` toward `operator` mapped functions for C-level speedups, carefully check if the sequence will be iterated over multiple times. If so, cast it to `list` first.
