#!/usr/bin/env python3
"""Report site-specific strings in tracked product files.

Patterns and path allow-globs live in .site-lint.json (one file per repo).
The scan is report-only unless SITE_LINT_STRICT=1, which exits 1 on any hit.
Existing hits are being removed; this check is what fails once
strict mode is turned on.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".webm",
    ".woff", ".woff2", ".zip", ".gz", ".tgz", ".pdf", ".wasm", ".pyc",
}
MAX_BYTES = 1_000_000


def repo_root(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".site-lint.json").is_file():
            return candidate
    raise SystemExit("site-lint: no .site-lint.json found")


def load_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"site-lint: cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("site-lint: .site-lint.json must be an object")
    patterns = data.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise SystemExit("site-lint: patterns must be a non-empty list")
    compiled = []
    flags = re.IGNORECASE if data.get("ignoreCase", True) else 0
    for item in patterns:
        if not isinstance(item, dict):
            raise SystemExit("site-lint: each pattern needs id and regex")
        ident = item.get("id")
        regex = item.get("regex")
        if not isinstance(ident, str) or not ident or not isinstance(regex, str):
            raise SystemExit("site-lint: each pattern needs id and regex")
        try:
            compiled.append((ident, re.compile(regex, flags)))
        except re.error as exc:
            raise SystemExit(f"site-lint: bad regex {ident}: {exc}") from exc
    allow = []
    for item in data.get("allow") or []:
        if not isinstance(item, dict):
            raise SystemExit("site-lint: each allow entry needs glob and reason")
        glob = item.get("glob")
        reason = item.get("reason")
        if not isinstance(glob, str) or not glob.strip():
            raise SystemExit("site-lint: an allow entry is missing its glob")
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(f"site-lint: allow {glob!r} needs a reason")
        allow.append((glob.strip(), reason.strip()))
    roots = data.get("roots") or ["."]
    if not isinstance(roots, list) or not all(isinstance(r, str) and r for r in roots):
        raise SystemExit("site-lint: roots must be a list of paths")
    return {"patterns": compiled, "allow": allow, "roots": roots}


def glob_match(path: str, pattern: str) -> bool:
    pat = pattern[2:] if pattern.startswith("./") else pattern
    rx = ""
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            rx += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            rx += ".*"
            i += 2
        elif pat[i] == "*":
            rx += "[^/]*"
            i += 1
        elif pat[i] == "?":
            rx += "[^/]"
            i += 1
        else:
            rx += re.escape(pat[i])
            i += 1
    return re.fullmatch(rx, path) is not None


def in_roots(path: str, roots: list) -> bool:
    for root in roots:
        root = root.strip("/")
        if root in ("", "."):
            return True
        if path == root or path.startswith(root + "/"):
            return True
    return False


def allowed(path: str, allow: list) -> bool:
    return any(glob_match(path, glob) for glob, _reason in allow)


def list_files(root: Path) -> list:
    if (root / ".git").exists():
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        return [name.decode() for name in done.stdout.split(b"\0") if name]
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for filename in filenames:
            rel = os.path.relpath(os.path.join(dirpath, filename), root)
            found.append(rel.replace(os.sep, "/"))
    return found


def file_text(path: Path) -> str | None:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_BYTES:
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def scan(root: Path, config: dict) -> tuple:
    """Return (lines_by_pattern, files_with_hits, line_hits)."""
    counts = {ident: 0 for ident, _rx in config["patterns"]}
    files = 0
    lines = 0
    for rel in list_files(root):
        if not in_roots(rel, config["roots"]) or allowed(rel, config["allow"]):
            continue
        text = file_text(root / rel)
        if text is None:
            continue
        file_hit = False
        for line in text.splitlines():
            hit = False
            for ident, rx in config["patterns"]:
                if rx.search(line):
                    counts[ident] += 1
                    hit = True
            if hit:
                lines += 1
                file_hit = True
        if file_hit:
            files += 1
    return counts, files, lines


def report(counts: dict, files: int, lines: int, strict: bool) -> int:
    flag = "1" if strict else "0"
    print(f"site-lint: files={files} lines={lines} strict={flag}")
    for ident in sorted(counts):
        print(f"  {ident}: {counts[ident]}")
    if strict and lines:
        print("site-lint: strict mode, hits remain", file=sys.stderr)
        return 1
    return 0


def self_test() -> int:
    """Prove strict mode fails on a hit, passes an allow-glob, and stays quiet when clean."""
    samples = {
        "room-id": "sw" + "209",
        "cr9-board-room": "cr9" + "-board-room",
        "fi108": "fi" + "108",
        "campus-ip": "172" + ".31." + "0.1",
        "goossen-dev": "goossen" + ".dev",
        "moody-edu": "moody" + ".edu",
    }
    config = {
        "ignoreCase": True,
        "roots": ["."],
        "patterns": [
            {"id": "room-id", "regex": r"\bsw[0-9]{3}\b"},
            {"id": "cr9-board-room", "regex": r"\bcr9-board-room\b"},
            {"id": "fi108", "regex": r"\bfi108\b"},
            {"id": "campus-ip", "regex": r"172\.31\."},
            {"id": "goossen-dev", "regex": r"goossen\.dev"},
            {"id": "moody-edu", "regex": r"moody\.edu"},
        ],
        "allow": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "notes.txt").write_text(
            "room " + samples["room-id"] + " at " + samples["campus-ip"] + "\n",
            encoding="utf-8",
        )
        (root / "keep").mkdir()
        (root / "keep" / "stay.txt").write_text(samples["goossen-dev"] + "\n", encoding="utf-8")
        loaded = load_config_obj(config)
        counts, files, lines = scan(root, loaded)
        if counts["room-id"] != 1 or counts["campus-ip"] != 1 or files != 2 or lines != 2:
            print(f"site-lint self-test: unexpected counts {counts} files={files} lines={lines}", file=sys.stderr)
            return 1
        if report(counts, files, lines, True) != 1:
            print("site-lint self-test: strict mode did not fail", file=sys.stderr)
            return 1
        config["allow"] = [
            {"glob": "notes.txt", "reason": "fixture"},
            {"glob": "keep/**", "reason": "fixture tree"},
        ]
        counts, files, lines = scan(root, load_config_obj(config))
        if files or lines or report(counts, files, lines, True) != 0:
            print("site-lint self-test: allow-globs did not hide the hits", file=sys.stderr)
            return 1
        (root / "notes.txt").write_text("room-101 example.org\n", encoding="utf-8")
        (root / "keep" / "stay.txt").write_text("ok\n", encoding="utf-8")
        config["allow"] = []
        counts, files, lines = scan(root, load_config_obj(config))
        if files or lines or report(counts, files, lines, True) != 0:
            print("site-lint self-test: a clean tree failed strict mode", file=sys.stderr)
            return 1
        # Every configured literal is recognized, so a new pattern cannot be a no-op.
        blob = "\n".join(samples[ident] for ident, _rx in load_config_obj(config)["patterns"])
        (root / "all.txt").write_text(blob + "\n", encoding="utf-8")
        counts, _files, _lines = scan(root, load_config_obj(config))
        missing = [ident for ident, n in counts.items() if n != 1]
        if missing:
            print(f"site-lint self-test: patterns missed a sample: {missing}", file=sys.stderr)
            return 1
    print("site-lint self-test: ok")
    return 0


def load_config_obj(data: dict) -> dict:
    """load_config, but from an object. Used by the self-test."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(data, handle)
        name = handle.name
    try:
        return load_config(Path(name))
    finally:
        os.unlink(name)


def main(argv: list) -> int:
    if "--self-test" in argv:
        return self_test()
    try:
        root = repo_root(Path.cwd())
    except SystemExit:
        root = repo_root(Path(__file__).resolve().parent)
    config = load_config(root / ".site-lint.json")
    counts, files, lines = scan(root, config)
    strict = os.environ.get("SITE_LINT_STRICT") == "1"
    return report(counts, files, lines, strict)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
