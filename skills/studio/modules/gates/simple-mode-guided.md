# Guided Mode Branch

```pdsl
UNIT SimpleModeGuided
PURPOSE: Preserve today's standard workflow behavior under the guided interaction mode — every menu, gate, and stop intact.
WHEN:
  - REQUIRE SIMPLE_MODE == guided
DO:
  - REQUIRE SIMPLE_MODE == guided
RULES:
  - ALWAYS continue with the workflow's existing menus, gates, stops, and output contracts
  - NEVER add simple-mode explanations or automatic selections while SIMPLE_MODE == guided
```
