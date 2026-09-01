```toml
[phase]
number = 1
total = 2
depends_on = []
outputs = ["design-note.md"]
```

## Preamble

Design the health-check endpoint before any code is written, so the shape of the
response is agreed rather than discovered during implementation.

## What

Produce a short design note covering the route, the response body, and the status
codes for healthy and degraded states.

## Rules

- ALWAYS state the response shape before implementing it.
- NEVER add a dependency for this endpoint; the standard library is sufficient.
