#!/usr/bin/env python3
"""Make coverage.xml filenames repo-relative, so a coverage reader can find the files.

`coverage.py` writes two reports from one run and they do not agree on paths. The JSON keeps
the full path (`skills/studio/scripts/studio/cli.py`); the XML writer strips the common root
into `<sources>` and leaves each `filename` relative to it (`cli.py`). Anything reading the XML
against the repository therefore matches nothing.

That is why SonarCloud has reported **0.0% coverage on new code** on every pull request since at
least 2026-09-08 (#155) while the same run measured 95% locally. It went unnoticed because the
quality gate has no coverage condition, so `0.0%` renders beside a green tick.

This rewrites each `filename` to `<source>/<filename>`, leaving everything else untouched. The
JSON report is already correct and is not read here — `scripts/check_coverage.py` enforces the
per-file threshold from it, and that enforcement is deliberately not disturbed.

**It refuses rather than guesses.** With more than one usable `<source>` the correct prefix for
a given file is ambiguous, and a wrong prefix would produce a report that looks fine and matches
nothing — exactly the failure being fixed, which survived two and a half weeks unnoticed. A
second `--cov` root is the realistic way that happens, so it exits non-zero and says so.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _usable_sources(root: ET.Element) -> list[str]:
    """The `<source>` entries that can serve as a prefix.

    `.` and the empty string are dropped: coverage.py emits them for a repo-root run, where the
    filenames are already repo-relative and need no prefix at all.
    """
    out = []
    for node in root.findall("./sources/source"):
        text = (node.text or "").strip()
        if text and text != ".":
            out.append(text.rstrip("/"))
    return out


def rewrite(xml_path: Path) -> tuple[int, int]:
    """Prefix every `class/@filename` with the single `<source>`. Returns (rewritten, total)."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    sources = _usable_sources(root)

    if not sources:
        # Already repo-relative (a repo-root run). Nothing to do, and saying so is not an error.
        classes = list(root.iter("class"))
        return 0, len(classes)

    if len(sources) > 1:
        raise SystemExit(
            f"{xml_path}: {len(sources)} usable <source> entries {sources} — cannot choose a "
            "prefix. Adding a second --cov root makes every filename ambiguous; fix the "
            "coverage invocation rather than letting this guess."
        )

    prefix = sources[0] + "/"
    rewritten = total = 0
    for cls in root.iter("class"):
        total += 1
        name = cls.get("filename") or ""
        if name and not name.startswith(prefix):
            cls.set("filename", prefix + name)
            rewritten += 1

    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return rewritten, total


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("coverage_xml", help="Path to the Cobertura XML report (rewritten in place)")
    p.add_argument("--quiet", action="store_true", help="Print nothing on success")
    args = p.parse_args()

    path = Path(args.coverage_xml)
    if not path.is_file():
        # Not an error: `make test-coverage` may be run for the terminal report alone.
        if not args.quiet:
            print(f"{path}: no such file, nothing to rewrite")
        return 0

    rewritten, total = rewrite(path)
    if not args.quiet:
        print(f"{path}: {rewritten} of {total} filenames made repo-relative")
    return 0


if __name__ == "__main__":
    sys.exit(main())
