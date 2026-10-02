"""Project a run's close into four headings from the decision log.

The end of a run, read back rather than re-constructed: **defaults applied**, **rulings**,
**open questions**, and **completed actions**. Every line is a projection over events earlier
steps already wrote -- this records nothing new and invents nothing the ledger does not hold.

The one rule that matters: a **ruling** (something decided for the user) and an **open question**
(something nobody has decided) never share a heading. They come from different event kinds -- a
ruling from a resolved ``gate`` event, an open question from the outstanding register -- so one
event can never land in both buckets, and the two are rendered under different headings.

**Scoped to one run**, exactly like the open-questions register and for the same reason: the log
is shared across runs, so the summary projects only the run being closed (``run_id``, defaulting
to the current run). Run stand-alone with no ``--run-id`` it summarises *this* command's own run,
which did nothing -- so it is empty; the summary bites in the in-process close (a later increment)
or when the executing run's id is passed.

**Empty is stated, never hidden**: a heading with nothing under it says so, rather than vanishing,
so a reader can tell "nothing happened" from "the summary forgot".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..utils import decision_log, open_questions, ui
# The ledger's own display transform (redact + cap + neutralise lone surrogates + strip control
# characters), reused rather than re-spelled: ledger values are rendered to a human and serialised to
# JSON here, and an un-neutralised surrogate crashes both, exactly as gate-log already guards against.
from ..utils.plan_decisions import _bounded

_COMMAND = "run-summary"

# @cpt-begin:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-model
#: The gate-event kinds that are a decision made or surfaced for the user this run (the rulings
#: heading): `plan-resolved`/`blocking-confirmed` are resolved, and `exception-asked` is a gate the
#: autonomous flow surfaced as an exception rather than deciding — included here so no live gate kind
#: silently vanishes from the summary (the five `decision_log.GATE_KINDS` are now all accounted for:
#: these three plus `auto-proceeded` below and `open-question` via the register).
_RULING_KINDS = ("plan-resolved", "blocking-confirmed", "exception-asked")

#: The gate-event kind that is a safe default taken with no plan answer (the defaults heading).
_DEFAULT_KIND = "auto-proceeded"


@dataclass(frozen=True)
class _Entry:
    """One line under a heading: a short label and the detail that belongs with it."""

    label: str
    detail: str


@dataclass(frozen=True)
class Summary:
    """A run's close under four headings, each a list projected from the ledger.

    Every heading is present even when empty -- an empty list is rendered as "none" rather than
    omitted, so "nothing happened" is distinguishable from a dropped section. ``rulings`` and
    ``open_questions`` are **reconciled** at projection time: a key the register still reports
    outstanding (resolved, then reopened) is dropped from ``rulings``, so no key appears in both.
    """

    defaults_applied: List[_Entry] = field(default_factory=list)
    rulings: List[_Entry] = field(default_factory=list)
    open_questions: List[_Entry] = field(default_factory=list)
    completed_actions: List[_Entry] = field(default_factory=list)
# @cpt-end:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-model


# @cpt-begin:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-gate
def _field(payload: Dict[str, object], key: str) -> str:
    """One gate-event field for display: empty for a missing field **or** the ledger's internal
    ``UNSPECIFIED`` sentinel (which an omitted field legitimately carries), so neither the raw
    sentinel nor an empty string leaks into the ruling text or the JSON payload."""
    value = str(payload.get(key) or "")
    return "" if value == decision_log.UNSPECIFIED else value


def _bucket_gate(payload: Dict[str, object], defaults: List[_Entry],
                 rulings: List[_Entry], ruling_keys: List[str]) -> None:
    """Sort one ``gate`` event into the defaults or rulings heading (or neither).

    An ``auto-proceeded`` gate is a default applied; a ``plan-resolved``/``blocking-confirmed``
    gate is a ruling. An ``open-question`` gate is **not** bucketed here -- outstanding questions
    come from the register. A ruling records its ``decision_key`` in ``ruling_keys`` (parallel to
    ``rulings``) so the caller can drop a key that the register still reports outstanding: a key
    resolved and then **reopened** must appear only under open questions, never also as a ruling.
    """
    kind = payload.get("kind")
    gate = str(payload.get("gate") or "") or _field(payload, "decision_key") or "a gate"
    why = _field(payload, "why")
    if kind == _DEFAULT_KIND:
        defaults.append(_Entry(gate, why or "proceeded on a safe default"))
    elif kind in _RULING_KINDS:
        cost = _field(payload, "cost_if_wrong")
        value = _field(payload, "value")
        detail = " — ".join(p for p in (value, why) if p) or "resolved"
        if cost:
            detail = f"{detail} (cost if wrong: {cost})"
        rulings.append(_Entry(gate, detail))
        ruling_keys.append(_field(payload, "decision_key"))


def _bucket_completed(event: object, obj: Dict[str, object],
                      payload: Dict[str, object], completed: List[_Entry]) -> None:
    """Append a completed action for a **satisfied** verification, an invocation, or a validation.

    A verification that is not ``satisfied`` is deliberately not a completed action; failed/other
    verifications are the completion check's business, not this close summary's.
    """
    if event == "verification" and payload.get("verdict") == "satisfied":
        completed.append(_Entry(str(payload.get("item") or "an item"), "satisfied"))
    elif event == "invocation":
        completed.append(_Entry(str(obj.get("command") or "a command"),
                                f"exit {payload.get('exit_code', 0)}"))
    elif event == "validation":
        completed.append(_Entry(str(payload.get("check") or "a check"),
                                str(payload.get("status") or "")))
# @cpt-end:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-gate


# @cpt-begin:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-project
def summarise(log_path: Optional[Path] = None, *, run_id: Optional[str] = None) -> Summary:
    """Project the run's close into the four headings, reading the ledger once, scoped to a run.

    Buckets ``gate`` events into defaults/rulings, ``verification`` events that are ``satisfied``
    plus ``invocation``/``validation`` events into completed actions, and reads the outstanding
    open questions from the register (same run scope). Re-reads every call; never caches.
    """
    # `run_id or current_run_id()`, not `run_id if run_id is not None`: an empty string is "no
    # run", and `read_events` treats an empty `run_id` as "no filter" (every run), which would read
    # another run's events into this summary. Fall back to the current run instead. (Same fix the
    # open-question register carries.)
    scope = run_id or decision_log.current_run_id()
    defaults: List[_Entry] = []
    rulings: List[_Entry] = []
    ruling_keys: List[str] = []
    completed: List[_Entry] = []
    for obj in decision_log.read_events(log_path, run_id=scope):
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        event = obj.get("event")
        if event == "gate":
            _bucket_gate(payload, defaults, rulings, ruling_keys)
        else:
            _bucket_completed(event, obj, payload, completed)
    register = open_questions.read_open_questions(log_path, run_id=scope)
    outstanding = register.outstanding
    open_q = [_Entry(q.key, q.reason or "could not be ruled")
              for q in outstanding.values()]
    # Reconcile the two projections: a key the register still reports outstanding (resolved earlier,
    # then reopened) belongs only under open questions, so drop it from rulings -- no key appears in
    # both headings. A ruling with no decision_key cannot be an open question, so it is kept.
    rulings = [entry for entry, key in zip(rulings, ruling_keys)
               if not (key and key in outstanding)]
    return Summary(defaults_applied=defaults, rulings=rulings,
                   open_questions=open_q, completed_actions=completed)
# @cpt-end:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-project


# @cpt-begin:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-report
_HEADINGS = (
    ("defaults applied", "defaults_applied"),
    ("rulings", "rulings"),
    ("open questions", "open_questions"),
    ("completed actions", "completed_actions"),
)


def _rows(entries: List[_Entry]) -> List[Dict[str, str]]:
    """One heading's entries as ``{label, detail}`` dicts, each value passed through the ledger's
    display transform so a corrupt value (control characters, an escaped lone surrogate) can neither
    crash the JSON serialisation nor the human render -- the one sink both outputs read from."""
    return [{"label": _bounded(e.label), "detail": _bounded(e.detail)} for e in entries]


def _payload(summary: Summary) -> Dict[str, object]:
    """One structured shape: each heading as a list of ``{label, detail}`` (empty list = none).

    Each field is read **by name** (not ``getattr``) so the dead-code scanner sees the use."""
    return {
        "defaults_applied": _rows(summary.defaults_applied),
        "rulings": _rows(summary.rulings),
        "open_questions": _rows(summary.open_questions),
        "completed_actions": _rows(summary.completed_actions),
    }


def _say(payload: Dict[str, object]) -> None:
    """Human rendering: each heading in order; an empty heading is stated as "none"."""
    ui.info("run summary")
    for title, attr in _HEADINGS:
        entries = payload.get(attr) or []
        if not entries:
            ui.detail(title, "none")
            continue
        for entry in entries:  # type: ignore[union-attr]
            label = str(entry.get("label", ""))  # type: ignore[union-attr]
            detail = str(entry.get("detail", ""))  # type: ignore[union-attr]
            ui.detail(title, f"{label}: {detail}" if detail else label)
# @cpt-end:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-report


# @cpt-begin:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-cli
def _parser() -> ui.JsonSafeArgumentParser:
    """The command's arguments."""
    parser = ui.JsonSafeArgumentParser(
        prog="cfs run-summary",
        description="Project a run's close into four headings (defaults applied, rulings, open "
                    "questions, completed actions) from the local decision log.",
        epilog="How events map to headings: 'defaults applied' = auto-proceeded gates; 'rulings' = "
               "plan-resolved / blocking-confirmed gates (a key later reopened moves to open "
               "questions instead); 'open questions' = keys still outstanding in the register; "
               "'completed actions' = satisfied verifications, command invocations, and validations.")
    parser.add_argument("--run-id", default=None,
                        help="the run to summarise; defaults to this command's own run. The log "
                             "is shared across runs, so run stand-alone with no --run-id the "
                             "summary covers this command's run (which did nothing); pass the "
                             "executing run's id to summarise that run")
    return parser


def cmd_run_summary(argv: List[str]) -> int:
    """Print the run summary. Exits 0 on success; 2 on a malformed argument."""
    args = ui.parse_args_or_json_error(_parser(), argv)
    if args is None:
        return 2  # a bad argument -- the standard structured ERROR was already emitted
    summary = summarise(run_id=args.run_id)
    ui.result(_payload(summary), human_fn=_say)
    return 0
# @cpt-end:cpt-studio-algo-execution-plans-run-summary:p1:inst-summary-cli
