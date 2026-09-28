"""T7 (HYP-2992): the review-fix scope must honour a marked finding subset.

The review-fix flow in ``skills/studio/modules/review/fix-approval.md`` is PDSL
executed by the model at runtime, not by Python, so the #322 regression is
pinned here structurally -- by asserting the source routes a marked subset
through a confirm -- rather than by running the flow. Each assertion fails if
the fix is reverted (the bug: a broad scope option discarded the marks
silently), which is what makes these tests, not just the docstrings, the guard.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIX_APPROVAL = "skills/studio/modules/review/fix-approval.md"


def _source() -> str:
    path = REPO_ROOT / FIX_APPROVAL
    return path.read_text(encoding="utf-8")


def _menu_option_lines(text: str, menu: str) -> dict:
    """The option lines of one ``MENU``, keyed by their leading number.

    Scans from the ``MENU <name>`` header to the next unit/menu/fence, keeping
    only lines whose first token is a digit -- the numbered options.
    """
    out: dict = {}
    in_menu = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(f"MENU {menu}") and stripped[len(f"MENU {menu}"):len(f"MENU {menu}") + 1] in ("", " ", ":"):
            in_menu = True
            continue
        if not in_menu:
            continue
        if stripped.startswith(("MENU ", "UNIT ", "```")):
            break
        head = stripped.split(maxsplit=1)
        if head and head[0].isdigit():
            out[head[0]] = stripped
    return out


def test_a_broad_scope_with_marks_routes_through_the_confirm() -> None:
    """The core #322 fix: with marks present, 'critical + major' and 'all' must
    ask before discarding them, not resolve their own scope directly.

    Reverting the fix (removing the marks-present branch so the options continue
    straight to their approve units) fails this test -- that is the point.
    """
    options = _menu_option_lines(_source(), "ReviewFixScope")
    for number in ("1", "2"):
        line = options.get(number, "")
        assert "ReviewFixMarkedOverrideConfirm WHEN SELECTED_FINDING_IDS != empty" in line, (
            f"ReviewFixScope option {number} no longer routes a marked subset through the "
            f"confirm -- a marked subset would be discarded silently:\n  {line}")


def test_no_marks_keeps_the_direct_broad_path() -> None:
    """With no marks the broad options go straight to their approve units, unchanged."""
    options = _menu_option_lines(_source(), "ReviewFixScope")
    assert "ReviewFixScopeApproveCriticalMajor WHEN SELECTED_FINDING_IDS == empty" in options.get("1", "")
    assert "ReviewFixScopeApproveAll WHEN SELECTED_FINDING_IDS == empty" in options.get("2", "")


def test_the_override_confirm_can_honour_the_marks() -> None:
    """The confirm's first option honours the marks via the existing partial path."""
    options = _menu_option_lines(_source(), "ReviewFixMarkedOverride")
    assert options, "ReviewFixMarkedOverride menu is missing"
    assert "ReviewFixPartialScopeResolve" in options.get("1", "")


def test_the_override_confirm_discards_marks_only_on_an_explicit_choice() -> None:
    """The confirm's second option clears the marks before applying the broader scope."""
    options = _menu_option_lines(_source(), "ReviewFixMarkedOverride")
    discard = options.get("2", "")
    assert "SELECTED_FINDING_IDS = empty" in discard, (
        f"the discard option must explicitly clear the marks:\n  {discard}")
    assert any(unit in discard for unit in
               ("ReviewFixScopeApproveCriticalMajor", "ReviewFixScopeApproveAll")), (
        f"the discard option must continue to a broad approve unit:\n  {discard}")


def test_the_gate_carries_the_honour_marks_rule() -> None:
    """The approval gate states the honour-marks invariant, so it is not only in the routing."""
    text = _source()
    assert "route a broad scope" in text
    assert "ReviewFixMarkedOverrideConfirm" in text
