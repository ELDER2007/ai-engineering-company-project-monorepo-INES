#!/usr/bin/env python3
"""
check_bilingual_sync.py — verify that every bilingual doc pair (X.md / X.es.md)
in the repo has matching Markdown heading structure.

Usage:
    python3 check_bilingual_sync.py [repo_root] [--files a.md b.es.md ...]

Args:
    repo_root   Path to scan for doc pairs. Defaults to the current directory.
    --files     Optional explicit list of changed file paths (e.g. from
                `git diff --name-only`). When given, only pairs touching one
                of these paths are checked — use this in the pre-commit flow
                to scope the check to what actually changed.

Exit codes:
    0   Every checked pair matches (or only produced warnings).
    1   At least one pair has a structural mismatch.

No third-party dependencies — stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# Doc pairs that are intentionally NOT structural translations of each other
# (e.g. a placeholder pointing elsewhere) — skip the heading-structure check
# for these but still report them so they aren't silently forgotten.
KNOWN_EXCEPTIONS = {
    "CONTEXT.md",  # CONTEXT.es.md is a placeholder that points at other briefing files, not a translation of CONTEXT.md
}

IGNORE_DIR_NAMES = {".git", "node_modules", ".venv", "__pycache__"}


def extract_headings(path: Path) -> list[tuple[int, str]]:
    """Return [(level, text), ...] for every Markdown heading in the file, in order."""
    headings = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    """Find every (en_path, es_path) pair under root where both files exist."""
    pairs = []
    for es_path in root.rglob("*.es.md"):
        if any(part in IGNORE_DIR_NAMES for part in es_path.parts):
            continue
        en_path = es_path.with_name(es_path.name[: -len(".es.md")] + ".md")
        if en_path.exists():
            pairs.append((en_path, es_path))
    return sorted(pairs)


def check_pair(en_path: Path, es_path: Path) -> list[str]:
    """Return a list of human-readable mismatch descriptions (empty if structure matches)."""
    en_headings = extract_headings(en_path)
    es_headings = extract_headings(es_path)
    problems = []

    if len(en_headings) != len(es_headings):
        problems.append(
            f"heading count differs: {en_path.name} has {len(en_headings)}, "
            f"{es_path.name} has {len(es_headings)}"
        )

    for i, ((en_level, en_text), (es_level, es_text)) in enumerate(
        zip(en_headings, es_headings), start=1
    ):
        if en_level != es_level:
            problems.append(
                f"heading #{i} level differs: '{en_text}' is H{en_level} in "
                f"{en_path.name}, but its counterpart '{es_text}' is H{es_level} "
                f"in {es_path.name}"
            )

    return problems


def main() -> int:
    args = sys.argv[1:]
    files_filter: set[str] | None = None
    if "--files" in args:
        idx = args.index("--files")
        files_filter = set(args[idx + 1 :])
        args = args[:idx]

    root = Path(args[0]).resolve() if args else Path.cwd()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1

    pairs = find_pairs(root)
    if not pairs:
        print("No X.md / X.es.md pairs found.")
        return 0

    exit_code = 0
    checked = 0
    for en_path, es_path in pairs:
        rel_en = en_path.relative_to(root)
        rel_es = es_path.relative_to(root)

        if files_filter is not None:
            touched = {str(rel_en), str(rel_es), en_path.name, es_path.name}
            if not touched & files_filter:
                continue

        checked += 1

        if en_path.name in KNOWN_EXCEPTIONS:
            print(f"SKIP  {rel_en} <-> {rel_es}  (known exception, not a structural translation)")
            continue

        problems = check_pair(en_path, es_path)
        if problems:
            exit_code = 1
            print(f"FAIL  {rel_en} <-> {rel_es}")
            for problem in problems:
                print(f"      - {problem}")
        else:
            print(f"OK    {rel_en} <-> {rel_es}")

    if files_filter is not None and checked == 0:
        print("No bilingual pairs matched the given --files list.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
