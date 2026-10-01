"""Verify a run against its plan before it may report success.

The close of a run: read the deliverable items the approved plan declares, read the verdicts
the run recorded for them, reconcile the two, and refuse to call the run complete if any item
is unsatisfied or unstated. It is **not** a second judgement engine -- it does not decide
whether an item is met. The run states each verdict (in v1 every item is an explicit
statement); this tallies those statements and enforces that every item has a satisfying one.

Each item's verdict is recorded to the decision log through ``record_verification``, so the
close is auditable and the session summary (a later increment) can be projected from the
ledger rather than re-constructed.

Exit codes follow the project contract (``architecture/specs/cli.md``): **0** the run is
complete, **2** a check FAILED (an item is not satisfied, not stated, or its criteria could
not be read), **1** a fault (the plan or the verdicts file could not be read). A fault is kept
apart from a failed check so CI keying on 2 for an incomplete run is not confused by a close
that could not run.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils import decision_log, plan_items, ui
from ..utils.plan_decisions import PLAN_FILE, _bounded, _load_plan

#: The run writes its verdicts here, beside the plan's own ``plan.toml`` by default.
# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-model
VERDICTS_FILE = "verdicts.toml"

#: The array a verdicts file declares its per-item verdicts in.
_VERDICTS_TABLE = "verdicts"

_COMMAND = "verify-completion"


@dataclass(frozen=True)
class _Verdict:
    """One recorded verdict and the evidence it rests on."""

    verdict: str
    evidence: str


@dataclass(frozen=True)
class Verdicts:
    """The verdicts a run recorded, keyed by ``(phase, bounded-text)`` -- phase ``None`` for an
    entry that names no phase.

    Keying by phase as well as text is what lets the **same criterion in two phases** receive
    two separate answers; a phase-less entry answers a criterion only when that text is unique
    across the plan (resolved in ``_verdict_for``). ``duplicates`` names keys a file answered
    more than once: a conflicting double-answer is no trustworthy answer, not the last one.
    ``error`` is set when the file itself could not be read, which is a fault, not a verdict.
    """

    by_key: Dict[Tuple[Optional[int], str], _Verdict] = field(default_factory=dict)
    duplicates: Set[Tuple[Optional[int], str]] = field(default_factory=set)
    error: Optional[str] = None


@dataclass(frozen=True)
class Completion:
    """One result shape for every outcome of a completion check.

    ``status`` is ``COMPLETE``, ``INCOMPLETE`` or ``ERROR``; ``exit_code`` is the contract
    code it maps to. ``unsatisfied`` and ``unstated`` name the items that block completion;
    ``read_problems`` carries the plan phases whose criteria could not be read (so an item
    may be missing entirely); ``applicable`` is ``False`` only when the plan declares no
    items at all, a vacuous pass that is stated rather than hidden.
    """

    status: str
    exit_code: int
    checked: int = 0
    unsatisfied: List[str] = field(default_factory=list)
    unstated: List[str] = field(default_factory=list)
    read_problems: List[str] = field(default_factory=list)
    phases_without_criteria: List[int] = field(default_factory=list)
    unmatched_verdicts: List[str] = field(default_factory=list)
    applicable: bool = True
    message: str = ""


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-model

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-read-verdicts
def _read_verdicts(path: Path) -> Verdicts:
    """The verdicts a run recorded, or a ``Verdicts`` carrying the reason the file failed.

    Reuses the plan loader's fail-loud TOML read rather than a second one. A file that
    declares no ``verdicts`` array is not an error -- it means the run stated nothing, so
    every item will read as unstated; a ``verdicts`` that is present but not an array is the
    author's defect and is reported.
    """
    data, reason, _verdict = _load_plan(path)
    if data is None:
        return Verdicts(error=reason)
    entries = data.get(_VERDICTS_TABLE)
    if not isinstance(entries, list):
        if _VERDICTS_TABLE in data:
            return Verdicts(error=(f"`{_VERDICTS_TABLE}` in {path.name} is not an array, "
                                   "so no verdicts can be read"))
        return Verdicts()
    by_key: Dict[Tuple[Optional[int], str], _Verdict] = {}
    duplicates: Set[Tuple[Optional[int], str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = _bounded(entry.get("item", ""))
        if not item:
            continue
        raw_phase = entry.get("phase")
        # A `bool` is an `int` subclass; `phase = true` is not a phase number.
        phase = raw_phase if isinstance(raw_phase, int) and not isinstance(raw_phase, bool) else None
        key = (phase, item)
        if key in by_key:
            duplicates.add(key)
        by_key[key] = _Verdict(
            verdict=_bounded(entry.get("verdict", "")),
            evidence=_bounded(entry.get("evidence", "")),
        )
    return Verdicts(by_key=by_key, duplicates=duplicates)


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-read-verdicts

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-item
def _verdict_for(item: plan_items.PlanItem, verdicts: Verdicts,
                 text_counts: Dict[str, int]) -> Tuple[str, str, str]:
    """The verdict, evidence, and a **reason tag** for one item, fail-safe toward not-satisfied.

    Looks the answer up by ``(phase, text)`` first; falls back to a phase-less entry only when
    this criterion's text is **unique** across the plan, since a phase-less answer to a text
    that appears in several phases cannot say which phase it means. The reason -- ``missing``,
    ``conflict``, ``unrecognised``, ``ambiguous`` or ``ok`` -- is returned explicitly so the
    caller classifies on it, never on the evidence text (which is author-controlled).
    """
    phased = (item.phase, item.text)
    if phased in verdicts.duplicates:
        return "not-satisfied", "conflicting verdicts were recorded for this item", "conflict"
    found = verdicts.by_key.get(phased)
    if found is None:
        phaseless = (None, item.text)
        if phaseless in verdicts.duplicates:
            return "not-satisfied", "conflicting verdicts were recorded for this item", "conflict"
        if phaseless in verdicts.by_key:
            if text_counts.get(item.text, 0) > 1:
                return ("not-satisfied", "a verdict with no phase is ambiguous because this "
                        "criterion appears in more than one phase", "ambiguous")
            found = verdicts.by_key[phaseless]
    if found is None:
        return "not-satisfied", "no verdict was recorded for this item", "missing"
    if found.verdict not in decision_log.VERIFICATION_VERDICTS:
        # A verdict outside the enumerated set is a typo or an invented value, not a pass:
        # accepting it would let `verdict = "done"` slip an unchecked item through.
        return "not-satisfied", f"unrecognised verdict {found.verdict!r}", "unrecognised"
    return found.verdict, found.evidence, "ok"


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-item

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
def _reconcile(items: plan_items.PlanItems, verdicts: Verdicts,
               log_path: Optional[Path]) -> Tuple[List[str], List[str]]:
    """Record one verification event per item and split the blockers into (unsatisfied, unstated).

    An item with no usable answer (``missing``/``ambiguous``) is *unstated*; one answered
    wrongly (``conflict``/``unrecognised``/an explicit not-satisfied) is *unsatisfied*. The
    split is on the reason tag, never on the evidence text.
    """
    unsatisfied: List[str] = []
    unstated: List[str] = []
    text_counts = Counter(item.text for item in items.items)
    for item in items.items:
        verdict, evidence, reason = _verdict_for(item, verdicts, text_counts)
        decision_log.record_verification(item.text, verdict, evidence, item.phase,
                                         command=_COMMAND, path=log_path)
        if verdict == "not-satisfied":
            (unstated if reason in ("missing", "ambiguous") else unsatisfied).append(item.text)
    return unsatisfied, unstated
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess


# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
def _unmatched(items: plan_items.PlanItems, verdicts: Verdicts) -> List[str]:
    """Verdict keys that answer no plan item -- by exact ``(phase, text)``, or by text for a
    phase-less entry. Reported, never counted against completion."""
    item_keys = {(item.phase, item.text) for item in items.items}
    item_texts = {item.text for item in items.items}
    unmatched: List[str] = []
    for key in verdicts.by_key:  # the keys are (phase, text); the values are not needed here
        phase, text = key
        matched = text in item_texts if phase is None else key in item_keys
        if not matched:
            unmatched.append(text if phase is None else f"{text} (phase {phase})")
    return sorted(unmatched)
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess


# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
def assess(plan_dir: Path, verdicts_path: Path, *, log_path: Optional[Path] = None) -> Completion:
    """Reconcile the plan's items against the run's verdicts and decide if the run is complete.

    Reads the items the plan declares and the verdicts the run recorded, records one
    verification event per item, and reports ``INCOMPLETE`` if any item is not satisfied, not
    stated, or had criteria that could not be read. A plan or verdicts file that will not load
    is an ``ERROR`` (a fault), not an incomplete run.
    """
    items = plan_items.read_plan_items(plan_dir)
    if items.error is not None:
        return Completion(status="ERROR", exit_code=1,
                          message=f"the plan could not be read: {items.error}")
    verdicts = _read_verdicts(verdicts_path)
    if verdicts.error is not None:
        return Completion(status="ERROR", exit_code=1,
                          message=f"the verdicts file could not be read: {verdicts.error}")

    unsatisfied, unstated = _reconcile(items, verdicts, log_path)
    unmatched = _unmatched(items, verdicts)

    # A phase whose criteria could not be read means an item may be missing entirely, so the
    # run cannot be shown complete -- fail-safe toward more friction, never toward a pass.
    blocked = bool(unsatisfied) or bool(unstated) or bool(items.read_problems)
    if not items.items and not items.read_problems:
        return Completion(status="COMPLETE", exit_code=0, checked=0, applicable=False,
                          read_problems=list(items.read_problems),
                          phases_without_criteria=list(items.phases_without_criteria),
                          unmatched_verdicts=unmatched,
                          message="the plan declares no deliverable items to verify")
    status, code = ("INCOMPLETE", 2) if blocked else ("COMPLETE", 0)
    return Completion(
        status=status, exit_code=code, checked=len(items.items),
        unsatisfied=unsatisfied, unstated=unstated,
        read_problems=list(items.read_problems),
        phases_without_criteria=list(items.phases_without_criteria),
        unmatched_verdicts=unmatched,
        message=_message(status, len(items.items), unsatisfied, unstated, items.read_problems),
    )


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report
def _message(status: str, checked: int, unsatisfied: List[str],
             unstated: List[str], read_problems: List[str]) -> str:
    """One human line summarising the outcome, naming the first blocking cause."""
    if status == "COMPLETE":
        return f"all {checked} item(s) satisfied"
    parts = []
    if unsatisfied:
        parts.append(f"{len(unsatisfied)} not satisfied")
    if unstated:
        parts.append(f"{len(unstated)} with no recorded verdict")
    if read_problems:
        parts.append(f"{len(read_problems)} phase(s) whose criteria could not be read")
    return "incomplete: " + "; ".join(parts)


def _payload(result: Completion) -> Dict[str, object]:
    """The structured result, one shape for every outcome."""
    return {
        "status": result.status,
        "checked": result.checked,
        "applicable": result.applicable,
        "unsatisfied": result.unsatisfied,
        "unstated": result.unstated,
        "read_problems": result.read_problems,
        "phases_without_criteria": result.phases_without_criteria,
        "unmatched_verdicts": result.unmatched_verdicts,
        "message": result.message,
    }


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report
def _say(payload: Dict[str, object]) -> None:
    """The human rendering: the headline, then each blocking item named."""
    if payload["status"] == "COMPLETE":
        ui.success(f"verify-completion: {payload['message']}")
        return
    ui.error(f"verify-completion: {payload['message']}")
    if payload["status"] == "ERROR":
        return
    for text in payload["unsatisfied"]:  # type: ignore[union-attr]
        ui.detail("not satisfied", str(text))
    for text in payload["unstated"]:  # type: ignore[union-attr]
        ui.detail("no verdict", str(text))


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli
def _parser() -> ui.JsonSafeArgumentParser:
    """The command's arguments.

    A ``JsonSafeArgumentParser`` so a bad argument under ``--json`` still emits a structured
    ERROR object on stdout rather than argparse's plain-text banner and a bare exit.
    """
    parser = ui.JsonSafeArgumentParser(
        prog="cfs verify-completion",
        description="Verify a run against its plan before it may report success. Reads the "
                    "plan's acceptance-criteria items and the verdicts the run recorded, and "
                    "exits 2 if any item is unsatisfied or unstated.")
    parser.add_argument("plan_dir", nargs="?", default=".",
                        help="the plan directory holding plan.toml (default: current dir)")
    parser.add_argument("--verdicts", default=None,
                        help=f"the verdicts file (default: {VERDICTS_FILE} under the plan dir)")
    return parser


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli
def cmd_verify_completion(argv: List[str]) -> int:
    """Run the completion check and return its contract exit code (0/1/2)."""
    args = _parser().parse_args(argv)
    plan_dir = Path(args.plan_dir)
    verdicts_path = Path(args.verdicts) if args.verdicts else plan_dir / VERDICTS_FILE
    if not (plan_dir / PLAN_FILE).exists():
        ui.result({"status": "ERROR", "message": f"no {PLAN_FILE} under {plan_dir}"},
                  human_fn=lambda d: ui.error(f"verify-completion: {d['message']}"))
        return 1
    result = assess(plan_dir, verdicts_path)
    payload = _payload(result)
    ui.result(payload, human_fn=_say)
    return result.exit_code

# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli