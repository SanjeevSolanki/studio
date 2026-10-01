"""Enumerate a plan's deliverable items from its phase files' acceptance criteria.

Verification-before-completion (the T4b close-of-run) checks a run against the items the
approved plan says it must satisfy. Those items are not a structured array in ``plan.toml``
today -- they live as Markdown task-list checkboxes under an ``## Acceptance Criteria``
heading in each phase file, the shape ``requirements/plan-template.md`` Section 8 mandates
(3-10 objectively-verifiable criteria per phase). This reads them into an enumerable list so
a later increment can walk it; it does not add plan syntax.

**The checkbox is a claim, never a verdict.** A ``[x]`` records that the *author* marked the
criterion done. This reader carries that as ``authored_done`` and nothing more -- whether the
item is actually satisfied is verification's job, not the box's, exactly as a sub-agent's
success report is not evidence its diff landed. Trusting the box here would delete the check
T4b exists to run.

**Every item is ``explicit`` in v1.** The plan does not yet declare *how* an item is checked
(a validator, a path, a schema), so none is inferred -- the conservative direction. The
``verify_kind`` field exists so a later increment can add ``deterministic`` without reshaping
any caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# Reuse the plan module's loader and text bound rather than a second copy of either: two
# plan readers drift, and two capping rules drift, and only one of each gets the next fix
# (the same argument `_bounded`'s own docstring makes). `_load_plan` is fail-loud -- it
# returns the reason a plan could not be read, which this surfaces rather than swallows.
from .plan_decisions import (  # noqa: F401  (re-exported constants kept near their use)
    PLAN_FILE,
    PHASES_TABLE,
    _MAX_PLAN_BYTES,
    _bounded,
    _load_plan,
)

# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
#: The level-2 heading whose task-list items are the deliverable criteria
#: (``requirements/plan-template.md`` Section 8). Matched case-insensitively.
_ACCEPTANCE_HEADING = "acceptance criteria"

#: A Markdown task-list item: a ``-`` or ``*`` bullet, a ``[ ]``/``[x]``/``[X]`` box, then
#: the criterion text. Anchored so a bare ``[x]`` mid-sentence is not mistaken for an item.
#: The text is captured greedily to end-of-line (no trailing ``\s*$``, which backtracks) and
#: trimmed by ``_bounded`` at the call site.
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[(?P<box>[ xX])\]\s+(?P<text>\S.*)$")

#: A level-2 ATX heading line. A deeper (``###``) or shallower (``#``) heading does not open
#: or close the criteria section, so a sub-heading inside it does not end it. The title is
#: captured greedily and ``.strip()``-ed at the call site, so no trailing ``\s*$`` is needed.
_H2_RE = re.compile(r"^\s*##\s+(?P<title>\S.*)$")

#: v1 verification kind -- an explicit statement to be made at completion. See module doc.
VERIFY_EXPLICIT = "explicit"

#: An author-controlled count, so it is bounded: a phase file declaring ten thousand
#: checkboxes yields the first `MAX_ITEMS_PER_PHASE` and a recorded note that the rest were
#: not read, never ten thousand items. The template's own ceiling is 10; this is generous.
MAX_ITEMS_PER_PHASE = 100
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
@dataclass(frozen=True)
class PlanItem:
    """One deliverable criterion a run must satisfy."""

    phase: int           #: the phase number whose acceptance criteria this came from
    ordinal: int         #: 0-based position within that phase's criteria (authoring order)
    text: str            #: the criterion text, bounded and whitespace-collapsed
    authored_done: bool  #: the ``[x]`` box as AUTHORED -- a claim, not a verified fact
    verify_kind: str = VERIFY_EXPLICIT
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
@dataclass(frozen=True)
class PlanItems:
    """Every deliverable item a run must satisfy, plus what could not be read.

    One shape for every outcome: a caller reads ``items`` for the list and ``error`` for a
    manifest that would not load at all (no items are returned in that case).
    ``phases_without_criteria`` is not an error -- a phase may legitimately declare none --
    but a later increment decides what an empty plan means, so it is surfaced, not hidden.
    ``read_problems`` names each phase whose criteria could not be fully read (a missing or
    unreadable file, a path escaping the plan directory, a non-UTF-8 file, or a criteria
    list past the per-phase cap), each with its reason: fail-loud, never a silent gap.
    """

    items: List[PlanItem]
    error: Optional[str] = None
    phases_without_criteria: List[int] = field(default_factory=list)
    read_problems: List[str] = field(default_factory=list)
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-read
def read_plan_items(plan_dir: Path) -> PlanItems:
    """The deliverable items the plan at ``plan_dir`` declares, in phase then authoring order.

    Re-reads the plan on every call (never cached): a plan edited mid-run has to take effect
    on the next read, the same reason the decision lookup re-reads. A manifest that will not
    load returns ``error`` and no items; a phase file that will not read is named in
    ``read_problems`` while the other phases still contribute theirs -- one bad phase file is
    a reported gap about that phase, not a crash that hides the rest.
    """
    plan, reason, _verdict = _load_plan(plan_dir / PLAN_FILE)
    if plan is None:
        return PlanItems(items=[], error=reason)

    phases = plan.get(PHASES_TABLE)
    if not isinstance(phases, list):
        if PHASES_TABLE in plan:
            # The author wrote a `phases` that is not an array -- a defect they must hear,
            # distinct from a plan that simply declares no phases (nothing to read).
            return PlanItems(
                items=[],
                error=(f"{PLAN_FILE}'s `{PHASES_TABLE}` is not an array, so no phase "
                       "files can be read for their acceptance criteria"),
            )
        return PlanItems(items=[])

    items: List[PlanItem] = []
    without: List[int] = []
    problems: List[str] = []
    for index, phase in enumerate(phases):
        found, empty_of, problem = _items_for_phase(plan_dir, phase, index)
        items.extend(found)
        if empty_of is not None:
            without.append(empty_of)
        if problem is not None:
            problems.append(problem)
    return PlanItems(items=items, phases_without_criteria=without, read_problems=problems)
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-read


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-phase
def _items_for_phase(
    plan_dir: Path, phase: object, index: int
) -> Tuple[List[PlanItem], Optional[int], Optional[str]]:
    """One phase's contribution: its items, the number to file under
    ``phases_without_criteria`` when it has none, and a ``read_problems`` note when reading
    it went wrong. A phase speaks to exactly the lists it has something to say for --
    truncation yields both items and a problem; a read failure yields only a problem.
    """
    if not isinstance(phase, dict):
        return [], None, f"phase at position {index}: not a table, so it was skipped"
    number = _phase_number(phase, index)
    file_name = phase.get("file")
    if not isinstance(file_name, str) or not file_name:
        return [], None, f"phase {number}: declares no `file` to read criteria from"
    text, read_error = _read_phase_text(plan_dir, file_name)
    if read_error is not None:
        return [], None, f"phase {number} ({_bounded(file_name)}): {read_error}"
    criteria, truncated = _acceptance_items(text, number)
    if truncated:
        return criteria, None, (f"phase {number}: more than {MAX_ITEMS_PER_PHASE} criteria; "
                                "the rest were not read")
    if not criteria:
        return [], number, None
    return criteria, None, None
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-phase


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file
def _phase_number(phase: dict, index: int) -> int:
    """The phase's declared ``number``, or its position when that is absent or unusable.

    An unparseable ``number`` falls back to ``index + 1`` rather than raising: the reader's
    job is to surface items, and a phase mis-numbering is the structural validator's finding,
    not a reason to read no items at all.
    """
    raw = phase.get("number")
    if isinstance(raw, bool):  # bool is an int subclass; a `number = true` is not a number
        return index + 1
    if isinstance(raw, int):
        return raw
    return index + 1
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file
def _read_phase_text(plan_dir: Path, file_name: str) -> Tuple[Optional[str], Optional[str]]:
    """A phase file's text, or ``None`` and the reason it could not be had.

    The file name comes from the plan, which is author-controlled, so the resolved path is
    required to stay inside the plan directory -- a ``file = "../../etc/passwd"`` is refused,
    not read. The file is read strictly as UTF-8: a byte sequence that is not UTF-8 is
    reported, never decoded with replacement, because a mangled criterion silently changes
    what the run is checked against.
    """
    base = plan_dir.resolve()
    candidate = (plan_dir / file_name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None, "its file path escapes the plan directory, so it is not read"
    if not candidate.is_file():
        return None, "is not a readable regular file"
    try:
        with candidate.open("rb") as handle:
            data = handle.read(_MAX_PLAN_BYTES + 1)
    except OSError as exc:
        return None, (exc.strerror or "could not be read").lower()
    if len(data) > _MAX_PLAN_BYTES:
        return None, "is larger than any phase file this workflow writes, so it is not read"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, (f"is not valid UTF-8 at byte {exc.start}, so its criteria would be "
                      "read as bytes the author did not write")
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-criteria
def _acceptance_items(phase_text: str, phase_number: int) -> Tuple[List[PlanItem], bool]:
    """The task-list items under this phase's ``## Acceptance Criteria`` heading.

    Scans line by line: a level-2 heading opens the section when its title is
    ``Acceptance Criteria`` (case-folded) and closes it when it is anything else, so a
    checkbox under a different ``##`` heading is never collected. Returns the items and a
    flag for whether the per-phase cap truncated them.
    """
    in_section = False
    items: List[PlanItem] = []
    ordinal = 0
    for line in phase_text.splitlines():
        heading = _H2_RE.match(line)
        if heading is not None:
            in_section = heading.group("title").strip().casefold() == _ACCEPTANCE_HEADING
            continue
        if not in_section:
            continue
        box = _CHECKBOX_RE.match(line)
        if box is None:
            continue
        if ordinal >= MAX_ITEMS_PER_PHASE:
            return items, True
        items.append(
            PlanItem(
                phase=phase_number,
                ordinal=ordinal,
                text=_bounded(box.group("text")),
                authored_done=box.group("box").casefold() == "x",
            )
        )
        ordinal += 1
    return items, False
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-criteria
