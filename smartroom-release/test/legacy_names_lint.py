#!/usr/bin/env python3
"""Fail when smartroomos / SmartRoomOS / Room OS appears outside legacy-aliases.txt.

Each allow entry is kind, pattern, reason, separated by tabs.
kind line: the pattern matches the line.
kind path: the pattern matches the repo-relative path.
kind root: only scan paths under this prefix (upstream trees stay out).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN = re.compile(r"smartroomos|room\s+os", re.IGNORECASE)


def find_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "legacy-aliases.txt").is_file() and (candidate / ".git").exists():
            return candidate
    raise SystemExit("legacy-aliases.txt not found above the lint")


def load_rules(path: Path):
    line_rules = []
    path_rules = []
    roots = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            raise SystemExit(f"{path}:{number}: need kind, pattern, and a reason")
        kind, pattern, _reason = parts[0], parts[1], parts[2]
        if kind == "root":
            roots.append(pattern.strip("/"))
            continue
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise SystemExit(f"{path}:{number}: {exc}") from exc
        if kind == "line":
            line_rules.append(compiled)
        elif kind == "path":
            path_rules.append(compiled)
        else:
            raise SystemExit(f"{path}:{number}: unknown kind {kind}")
    return line_rules, path_rules, roots


def allowed(rel: str, line: str, line_rules, path_rules) -> bool:
    if any(rule.search(rel) for rule in path_rules):
        return True
    return any(rule.search(line) for rule in line_rules)


def in_roots(rel: str, roots) -> bool:
    if not roots:
        return True
    return any(rel == root or rel.startswith(root + "/") for root in roots)


def scan(root: Path, line_rules, path_rules, roots) -> list[str]:
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],
        cwd=root,
    )
    hits = []
    for name in listed.split(b"\0"):
        if not name:
            continue
        rel = name.decode("utf-8", "surrogateescape")
        if not in_roots(rel, roots):
            continue
        path = root / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", "replace")
        for number, line in enumerate(text.splitlines(), 1):
            if not FORBIDDEN.search(line):
                continue
            if allowed(rel, line, line_rules, path_rules):
                continue
            hits.append(f"{rel}:{number}:{line.strip()}")
    return hits


def self_test(line_rules, path_rules) -> None:
    bad = "echo " + "smartroomos" + "-oops"
    phrase = "the Room " + "OS image"
    good = 'volume="SmartRoomOS"'
    if allowed("overlay/stray.sh", bad, line_rules, path_rules):
        raise SystemExit("self-test: a stray command name was allowed")
    if allowed("overlay/stray.sh", phrase, line_rules, path_rules):
        raise SystemExit("self-test: the product phrase was allowed")
    if not allowed("overlay/stray.sh", good, line_rules, path_rules):
        raise SystemExit("self-test: the legacy volume name was rejected")
    print("self-test ok")


def main() -> int:
    root = find_root()
    line_rules, path_rules, roots = load_rules(root / "legacy-aliases.txt")
    if "--self-test" in sys.argv[1:]:
        self_test(line_rules, path_rules)
        return 0
    hits = scan(root, line_rules, path_rules, roots)
    if hits:
        print(f"{len(hits)} legacy name(s) outside legacy-aliases.txt:", file=sys.stderr)
        for hit in hits[:200]:
            print(hit, file=sys.stderr)
        return 1
    print("legacy names ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
