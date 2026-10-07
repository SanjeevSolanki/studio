"""``cfs verify-subagent-work``: check a sub-agent's claim against the tree, not its report.

Two modes, one command, because they share the fingerprint's definition and splitting them
would let the two halves drift:

* ``--mark`` prints a fingerprint of the tree. The run takes one **before** dispatching.
* ``--since <mark>`` compares the tree against that fingerprint afterwards.

Exit codes follow the completion check's shape so a caller reads them the same way: **0**
the tree moved, or the question could not be asked; **2** the tree did not move, so the
report and the tree disagree; **1** only when the command itself could not run -- today that
means a malformed argument. A project with **no repository** is not a fault here: that is an
ordinary case and exits 0, which is why 1 is never reached by anything about the tree.

Why not-knowing exits ``0``: refusing to proceed wherever there is no git checkout would
make the common case unusable, and the trust this replaces was worth nothing anyway. The
reason is always stated, so a degraded check is visible rather than silent.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from ..utils import subagent_work, ui

_COMMAND = "verify-subagent-work"


# @cpt-begin:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-cli
def _parser() -> ui.JsonSafeArgumentParser:
    """The command's arguments: take a mark, or compare against one."""
    parser = ui.JsonSafeArgumentParser(
        prog="cfs verify-subagent-work",
        description="Check a dispatched sub-agent's work against the working tree rather than "
                    "its own success report: take a mark before dispatch, compare after.")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mark", action="store_true",
                       help="print a fingerprint of the tree now, to pass to --since later")
    group.add_argument("--since", default=None, metavar="MARK",
                       help="the fingerprint taken before dispatch")
    return parser


def cmd_verify_subagent_work(argv: List[str]) -> int:
    """Take or compare a tree mark. Exits 0 (moved or unknown), 2 (did not move)."""
    args = ui.parse_args_or_json_error(_parser(), argv)
    if args is None:
        # **Not 2.** A caller reads 2 as "the tree did not move" and blocks on it, so returning it
        # for a malformed argument would make a typo in the dispatch look like a sub-agent that
        # did nothing -- a false UNCHANGED produced by the very command that exists to never
        # produce one. A bad argument is the caller's fault and reproducible, unlike the absent
        # repository the no-fault-exit reasoning was about.
        return 1
    root = Path(args.root)

    if args.mark:
        taken = subagent_work.mark(root)
        ui.result(
            {"status": "marked" if taken else "unmarked", "mark": taken,
             # Two reasons reach `unmarked` -- an unreadable tree, and too many dirty paths to
             # fingerprint without skipping some. Both mean the same thing to the caller, so
             # the message names the consequence rather than guessing which one applied.
             "message": ("tree mark taken" if taken
                         else "no usable tree mark here, so the check will report unknown")},
            human_fn=lambda d: ui.info(f"{_COMMAND}: {d['message']}"
                                       + (f" ({d['mark']})" if d["mark"] else "")))
        return 0

    result = subagent_work.compare(root, args.since)
    ui.result(
        {"status": result.verdict.value, "reason": result.reason, "blocks": result.blocks},
        human_fn=lambda d: ui.info(f"{_COMMAND}: {d['status']} - {d['reason']}"))
    return 2 if result.blocks else 0
# @cpt-end:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-cli
