"""The coverage XML must name files the way the repository does.

`coverage.py` writes two reports from one run that disagree on paths: the JSON keeps
`skills/studio/scripts/studio/cli.py`, the XML strips the common root into `<sources>` and
leaves `filename="cli.py"`. A reader resolving the XML against the repository matches nothing,
which is why SonarCloud reported 0.0% coverage on every pull request (#155) while the same run
measured 95% locally — and why it went unnoticed: the gate has no coverage condition, so 0.0%
renders beside a green tick.

These pin the rewrite, and above all that it **refuses to guess** when the prefix is ambiguous.
A wrong prefix produces a report that looks correct and matches nothing, which is the bug.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "rewrite_coverage_xml_paths.py"


def _xml(tmp_path: Path, sources: list[str], filenames: list[str]) -> Path:
    src = "".join(f"<source>{s}</source>" for s in sources)
    cls = "".join(f'<class filename="{f}" name="x" line-rate="1"/>' for f in filenames)
    path = tmp_path / "coverage.xml"
    path.write_text(
        f'<?xml version="1.0" ?><coverage><sources>{src}</sources>'
        f"<packages><package><classes>{cls}</classes></package></packages></coverage>",
        encoding="utf-8")
    return path


def _names(path: Path) -> list[str]:
    return [c.get("filename") for c in ET.parse(path).getroot().iter("class")]


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                          capture_output=True, text=True, check=False)


def test_the_single_source_becomes_the_prefix(tmp_path: Path) -> None:
    path = _xml(tmp_path, ["skills/studio/scripts/studio"], ["cli.py", "utils/ui.py"])
    assert _run(path).returncode == 0
    assert _names(path) == ["skills/studio/scripts/studio/cli.py",
                            "skills/studio/scripts/studio/utils/ui.py"]


def test_a_trailing_slash_does_not_double_up(tmp_path: Path) -> None:
    path = _xml(tmp_path, ["skills/studio/scripts/studio/"], ["cli.py"])
    _run(path)
    assert _names(path) == ["skills/studio/scripts/studio/cli.py"]


def test_running_twice_is_the_same_as_running_once(tmp_path: Path) -> None:
    """`make test-coverage` may be re-run over an existing report; a second prefix would break it."""
    path = _xml(tmp_path, ["skills/studio/scripts/studio"], ["cli.py"])
    _run(path)
    first = _names(path)
    _run(path)
    assert _names(path) == first


def test_two_sources_are_refused_not_guessed(tmp_path: Path) -> None:
    """The failure this whole change exists to stop: a prefix that looks right and matches nothing.

    Two `--cov` roots make the correct prefix genuinely ambiguous. Choosing one silently would
    mis-path every file of the other, and the report would still look healthy.
    """
    path = _xml(tmp_path, ["skills/studio/scripts/studio", "src/studio_proxy"], ["cli.py"])
    result = _run(path)
    assert result.returncode != 0, result.stdout
    assert "cannot choose a prefix" in (result.stdout + result.stderr)
    assert _names(path) == ["cli.py"], "the report must be left untouched when it refuses"


@pytest.mark.parametrize("source", [".", ""])
def test_a_repo_root_run_is_left_alone(tmp_path: Path, source: str) -> None:
    """Filenames are already repo-relative there; prefixing `./` would be noise, not a fix."""
    path = _xml(tmp_path, [source], ["skills/studio/scripts/studio/cli.py"])
    assert _run(path).returncode == 0
    assert _names(path) == ["skills/studio/scripts/studio/cli.py"]


def test_a_missing_report_is_not_an_error(tmp_path: Path) -> None:
    """`make test-coverage` can be run for the terminal report alone; failing there would turn a
    working command into a broken one for no benefit."""
    result = _run(tmp_path / "absent.xml")
    assert result.returncode == 0, result.stderr


def test_every_rewritten_path_resolves_against_the_repository(tmp_path: Path) -> None:
    """The check a coverage reader actually performs, and the one that currently fails.

    Names taken from real modules rather than invented, so a rename that moved them would fail
    this test rather than leaving it passing against fiction.
    """
    repo = Path(__file__).parent.parent
    path = _xml(tmp_path, ["skills/studio/scripts/studio"], ["cli.py", "utils/ui.py"])
    _run(path)
    for name in _names(path):
        assert (repo / name).is_file(), name
