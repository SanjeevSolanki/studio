```toml
[phase]
number = 2
total = 2
depends_on = [1]
outputs = ["src/health.py", "tests/test_health.py"]
```

## Preamble

Implement the endpoint agreed in phase 1, with the tests written alongside it.

## What

Add the route, return the agreed body, and cover both the healthy and the degraded
path with a test each.

## Rules

- ALWAYS keep the response shape identical to the design note.
- NEVER let a test assert only the status code; assert the body too.
