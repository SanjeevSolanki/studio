# Example scenarios for `cfs eval`

Two runs the eval harness can score, so the command has something to work on out of the
box — and so a reader can see what a scenario looks like without reverse-engineering the
loader.

| Scenario | `expect` | Purpose |
|---|---|---|
| `compliant-two-phase` | `compliant` | A well-formed two-phase run. Every structural check should pass. |
| `non-compliant-numbering-gap` | `non_compliant` | **Deliberately broken.** Its phases are numbered 1 and 3, so `numbering-contiguous` fails. Everything else about it is valid. |

The second one is deliberate, not a mistake to be tidied up: without a run that is known
to be bad, a green result proves nothing — a checker that never fails is indistinguishable
from one that cannot fail. If you change it, keep exactly one check failing and say which
one here.

## Layout

```
eval/<scenario>/
  scenario.toml        [scenario] id · workflow · run_dir · expect
  run/
    plan.toml          [plan] table + one [[phases]] entry per phase
    phase-NN-*.md      a ```toml [phase] frontmatter block, then the body
```

Phase frontmatter carries `number`, `total`, `depends_on`, and `outputs`. Phase bodies
carry `## Preamble`, `## What` and `## Rules` (a `verify`/`verification` workflow drops
`## Rules`).

Run them with `cfs eval`. Gating is off by default: the broken run is reported, not
enforced, unless you pass `--check`.
