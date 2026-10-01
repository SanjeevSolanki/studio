"""Tests for enumerating a plan's deliverable items from phase-file acceptance criteria.

The reader's contract: items come out in phase-then-authoring order; a `[x]` is the author's
claim and never a verdict; every item is `explicit` in v1; and a plan or phase file that will
not read is a reported gap, never a silent empty list or a crash.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import plan_items as pi  # noqa: E402


def _plan(tmp_path: Path, manifest: str, phase_files: dict[str, str]) -> Path:
    """Write a plan.toml plus its phase files and return the plan directory."""
    (tmp_path / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    for name, body in phase_files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


_TWO_PHASE_MANIFEST = """\
[plan]
task = "demo"
total_phases = 2
[[phases]]
number = 1
file = "phase-1.md"
[[phases]]
number = 2
file = "phase-2.md"
"""

_PHASE_1 = """\
# Phase 1

## What
Produce the first artifact.

## Acceptance Criteria
- [ ] PRD file exists
- [x] User reviewed actor list
- [ ] No unresolved `{...}` variables outside code fences

## Output Format
Use the required completion report.
"""

_PHASE_2 = """\
# Phase 2

## Acceptance Criteria
* [X] Second artifact exists
* [ ] Line count within budget
"""


def test_reads_items_in_phase_then_authoring_order(tmp_path: Path) -> None:
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-1.md": _PHASE_1, "phase-2.md": _PHASE_2})
    )
    assert result.error is None
    assert result.read_problems == []
    assert [(i.phase, i.ordinal, i.text, i.authored_done) for i in result.items] == [
        (1, 0, "PRD file exists", False),
        (1, 1, "User reviewed actor list", True),
        (1, 2, "No unresolved `{...}` variables outside code fences", False),
        (2, 0, "Second artifact exists", True),
        (2, 1, "Line count within budget", False),
    ]
    assert all(i.verify_kind == pi.VERIFY_EXPLICIT for i in result.items)


def test_authored_checkbox_is_a_claim_not_a_verdict(tmp_path: Path) -> None:
    # A `[x]` sets authored_done but never promotes the item past `explicit` -- the reader
    # records the claim; verification (a later increment) decides if it is true.
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-1.md": _PHASE_1, "phase-2.md": _PHASE_2})
    )
    done = [i for i in result.items if i.authored_done]
    assert done
    assert all(i.verify_kind == pi.VERIFY_EXPLICIT for i in done)


@pytest.mark.parametrize(
    "line, expected_done",
    [
        ("- [ ] open", False),
        ("- [x] lower", True),
        ("- [X] upper", True),
        ("* [ ] star bullet", False),
        ("  - [x] indented", True),
    ],
)
def test_checkbox_variants_are_recognised(tmp_path: Path, line: str, expected_done: bool) -> None:
    body = f"## Acceptance Criteria\n{line}\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == 1
    assert result.items[0].authored_done is expected_done


def test_checkboxes_outside_the_criteria_section_are_ignored(tmp_path: Path) -> None:
    # A checkbox under a different `##` heading is not a deliverable item; the section both
    # opens on the right heading and CLOSES on the next one. Reverting either breaks this.
    body = (
        "## Acceptance Criteria\n"
        "- [ ] real criterion\n"
        "## Rules\n"
        "- [x] not a criterion\n"
    )
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert [i.text for i in result.items] == ["real criterion"]


def test_a_phase_with_no_criteria_is_surfaced_not_invented(tmp_path: Path) -> None:
    body = "# Phase 1\n## What\nNothing to check here.\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert result.items == []
    assert result.phases_without_criteria == [1]
    assert result.error is None


def test_missing_plan_is_an_error_not_a_crash(tmp_path: Path) -> None:
    result = pi.read_plan_items(tmp_path)  # no plan.toml written
    assert result.items == []
    assert result.error  # a non-empty reason, never a silent empty list


def test_a_malformed_phases_table_is_an_error(tmp_path: Path) -> None:
    # `phases` must be top-level, not nested under `[plan]`, to be the array the reader walks;
    # a top-level `phases = "oops"` is the author declaring the table and getting it wrong.
    (tmp_path / pi.PLAN_FILE).write_text('phases = "oops"\n[plan]\ntask = "t"\n', encoding="utf-8")
    result = pi.read_plan_items(tmp_path)
    assert result.items == []
    assert result.error is not None
    assert "phases" in result.error


def test_an_unreadable_phase_file_is_a_problem_but_other_phases_still_read(tmp_path: Path) -> None:
    # phase-1 points at a file that does not exist; phase-2 is fine and still contributes.
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-2.md": _PHASE_2})  # no phase-1.md
    )
    assert [i.text for i in result.items] == ["Second artifact exists", "Line count within budget"]
    assert any("phase 1" in p for p in result.read_problems)
    assert result.error is None


def test_a_phase_path_escaping_the_plan_dir_is_refused(tmp_path: Path) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("## Acceptance Criteria\n- [ ] LEAKED\n", encoding="utf-8")
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="../secret.md"\n'
    (plan_dir / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    result = pi.read_plan_items(plan_dir)
    assert result.items == []  # the escaping file is NOT read
    assert "LEAKED" not in " ".join(i.text for i in result.items)
    assert any("escapes" in p for p in result.read_problems)


def test_long_criterion_text_is_bounded(tmp_path: Path) -> None:
    body = "## Acceptance Criteria\n- [ ] " + ("A" * 5000) + "\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == 1
    assert 0 < len(result.items[0].text) <= 500  # the shared _bounded cap


def test_a_non_utf8_phase_file_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    (tmp_path / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    (tmp_path / "p.md").write_bytes(b"## Acceptance Criteria\n- [ ] \xff\xfe not utf8\n")
    result = pi.read_plan_items(tmp_path)
    assert result.items == []
    assert any("UTF-8" in p for p in result.read_problems)


def test_more_than_the_cap_criteria_truncates_with_a_note(tmp_path: Path) -> None:
    lines = "\n".join(f"- [ ] item {n}" for n in range(pi.MAX_ITEMS_PER_PHASE + 25))
    body = f"## Acceptance Criteria\n{lines}\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == pi.MAX_ITEMS_PER_PHASE
    assert any("more than" in p for p in result.read_problems)
