#!/usr/bin/env python3
"""Report one install's site-specific strings in tracked product files.

The patterns are the install's own and are not kept in this repo.
SITE_LINT_PATTERNS names their JSON file:
  {"ignoreCase": true, "comment": "...", "patterns": [{"id": "...", "regex": "..."}]}
Without SITE_LINT_PATTERNS the lint prints one line saying so and passes.

.site-lint.json at the repo root holds only this repo's settings: the roots to
scan and allow-globs, each with a reason. It never lists patterns.
Strict by default: exits 1 on any hit and names each file and line.
SITE_LINT_STRICT=0 reports without failing.
"""

from __future__ import annotations

import contextlib
import io
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
PATTERNS_ENV = "SITE_LINT_PATTERNS"
NOT_GIVEN = "site-lint: site patterns not given (SITE_LINT_PATTERNS is not set); nothing checked"
REPO_KEYS = {"comment", "roots", "allow"}
PATTERN_KEYS = {"comment", "ignoreCase", "patterns"}


def repo_root(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".site-lint.json").is_file():
            return candidate
    raise SystemExit("site-lint: no .site-lint.json found")


def read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"site-lint: cannot read {what} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"site-lint: {what} {path} must be an object")
    return data


def load_repo_config(path: Path) -> dict:
    """Roots and allow-globs from .site-lint.json. A pattern list is refused."""
    data = read_json(path, ".site-lint.json")
    if "patterns" in data:
        raise SystemExit(
            "site-lint: .site-lint.json must not list patterns; "
            "they belong to the install and come from SITE_LINT_PATTERNS"
        )
    unknown = sorted(set(data) - REPO_KEYS)
    if unknown:
        raise SystemExit(f"site-lint: .site-lint.json has unknown keys {unknown}")
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
    return {"allow": allow, "roots": roots}


def load_patterns(path: Path) -> list:
    """Compiled (id, regex) pairs from the install's pattern file."""
    data = read_json(path, "SITE_LINT_PATTERNS file")
    unknown = sorted(set(data) - PATTERN_KEYS)
    if unknown:
        raise SystemExit(f"site-lint: SITE_LINT_PATTERNS file has unknown keys {unknown}")
    patterns = data.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise SystemExit("site-lint: patterns must be a non-empty list")
    flags = re.IGNORECASE if data.get("ignoreCase", True) else 0
    compiled = []
    seen = set()
    for item in patterns:
        if not isinstance(item, dict):
            raise SystemExit("site-lint: each pattern needs id and regex")
        ident = item.get("id")
        regex = item.get("regex")
        if not isinstance(ident, str) or not ident or not isinstance(regex, str) or not regex:
            raise SystemExit("site-lint: each pattern needs id and regex")
        if ident in seen:
            raise SystemExit(f"site-lint: pattern id {ident} is listed twice")
        seen.add(ident)
        try:
            compiled.append((ident, re.compile(regex, flags)))
        except re.error as exc:
            raise SystemExit(f"site-lint: bad regex {ident}: {exc}") from exc
    return compiled


def patterns_from_env(env) -> Path | None:
    """The pattern file named by SITE_LINT_PATTERNS, or None when unset or empty."""
    value = (env.get(PATTERNS_ENV) or "").strip()
    if not value:
        return None
    return Path(os.path.expanduser(value))


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
    """Return (lines_by_pattern, files_with_hits, line_hits, where).

    where lists (path, line number, pattern ids) for every line with a hit.
    """
    counts = {ident: 0 for ident, _rx in config["patterns"]}
    files = 0
    lines = 0
    where = []
    for rel in list_files(root):
        if not in_roots(rel, config["roots"]) or allowed(rel, config["allow"]):
            continue
        text = file_text(root / rel)
        if text is None:
            continue
        file_hit = False
        for number, line in enumerate(text.splitlines(), 1):
            ids = [ident for ident, rx in config["patterns"] if rx.search(line)]
            for ident in ids:
                counts[ident] += 1
            if ids:
                lines += 1
                file_hit = True
                where.append((rel, number, ids))
        if file_hit:
            files += 1
    return counts, files, lines, where


def strict_from_env(env) -> bool:
    """Strict unless SITE_LINT_STRICT is 0."""
    return (env.get("SITE_LINT_STRICT") or "1").strip() != "0"


def report(counts: dict, files: int, lines: int, strict: bool, where=()) -> int:
    flag = "1" if strict else "0"
    print(f"site-lint: files={files} lines={lines} strict={flag}")
    for ident in sorted(counts):
        print(f"  {ident}: {counts[ident]}")
    # Locations only, never the matched text.
    for rel, number, ids in where:
        print(f"  hit {rel}:{number}: {','.join(ids)}")
    if strict and lines:
        print("site-lint: strict mode, hits remain (fix them, or allow a path in .site-lint.json with a reason)", file=sys.stderr)
        return 1
    return 0


def lint(root: Path, env) -> int:
    """Check root against the patterns SITE_LINT_PATTERNS names in env."""
    repo = load_repo_config(root / ".site-lint.json")
    source = patterns_from_env(env)
    if source is None:
        print(NOT_GIVEN)
        return 0
    patterns = load_patterns(source)
    print(f"site-lint: patterns={len(patterns)} from SITE_LINT_PATTERNS")
    config = {"patterns": patterns, **repo}
    counts, files, lines, where = scan(root, config)
    return report(counts, files, lines, strict_from_env(env), where)


def quietly(func, *args):
    """Run func with its output hidden, for the self-test fixtures."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func(*args)


def captured(func, *args) -> tuple:
    """(result, stdout) of func; SystemExit becomes (message, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            result = func(*args)
        except SystemExit as exc:
            result = str(exc.code)
    return result, out.getvalue()


def self_test() -> int:
    """Prove the lint finds planted hits from a pattern file and passes without one.

    The fixture patterns are neutral examples (RFC 5737, .example), not any install's.
    """
    def fail(message: str) -> int:
        print(f"site-lint self-test: {message}", file=sys.stderr)
        return 1

    pattern_doc = {
        "ignoreCase": True,
        "comment": "neutral fixture",
        "patterns": [
            {"id": "room-id", "regex": r"(?<![a-z0-9])zq[0-9]{3}(?![0-9])"},
            {"id": "site-net", "regex": r"198\.51\.100\."},
            {"id": "site-domain", "regex": r"campus\.example"},
        ],
    }
    samples = {
        "room-id": ["zq" + "101", "chrome-room__" + "zq" + "102-Default"],
        "site-net": ["198.51" + ".100.7"],
        "site-domain": ["campus" + ".example"],
    }
    repo_doc = {"comment": "fixture", "roots": ["."], "allow": []}

    for env, want in (({}, True), ({"SITE_LINT_STRICT": "1"}, True), ({"SITE_LINT_STRICT": "0"}, False)):
        if strict_from_env(env) is not want:
            return fail(f"strict_from_env({env}) is not {want}")
    for env in ({}, {PATTERNS_ENV: ""}, {PATTERNS_ENV: "  "}):
        if patterns_from_env(env) is not None:
            return fail(f"patterns_from_env({env}) must be None")
    if patterns_from_env({PATTERNS_ENV: "~/p.json"}) != Path(os.path.expanduser("~/p.json")):
        return fail("SITE_LINT_PATTERNS must expand ~")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "repo"
        (root / "keep").mkdir(parents=True)
        site = base / "site-patterns.json"
        site.write_text(json.dumps(pattern_doc), encoding="utf-8")
        cfg = root / ".site-lint.json"
        cfg.write_text(json.dumps(repo_doc), encoding="utf-8")
        (root / "notes.txt").write_text(
            "ok\nroom " + samples["room-id"][0] + " at " + samples["site-net"][0] + "\n",
            encoding="utf-8",
        )
        (root / "keep" / "stay.txt").write_text(samples["site-domain"][0] + "\n", encoding="utf-8")
        with_patterns = {PATTERNS_ENV: str(site)}

        # Without a pattern file: one line, pass, even with hits planted.
        result, out = captured(lint, root, {})
        if result != 0 or out.strip() != NOT_GIVEN:
            return fail(f"without SITE_LINT_PATTERNS want one notice line and 0, got {result} {out!r}")

        # With it: the planted hits are found, by file and line, not by text.
        config = {"patterns": load_patterns(site), **load_repo_config(cfg)}
        counts, files, lines, where = scan(root, config)
        if counts["room-id"] != 1 or counts["site-net"] != 1 or files != 2 or lines != 2:
            return fail(f"unexpected counts {counts} files={files} lines={lines}")
        if sorted(where) != [("keep/stay.txt", 1, ["site-domain"]), ("notes.txt", 2, ["room-id", "site-net"])]:
            return fail(f"unexpected locations {where}")
        result, out = captured(lint, root, with_patterns)
        if result != 1 or "hit notes.txt:2: room-id,site-net" not in out:
            return fail(f"strict mode did not fail on the planted hit: {result} {out!r}")
        if "patterns=3 from SITE_LINT_PATTERNS" not in out:
            return fail("the pattern count is not printed")
        result, out = captured(lint, root, {**with_patterns, "SITE_LINT_STRICT": "0"})
        if result != 0 or "strict=0" not in out:
            return fail("SITE_LINT_STRICT=0 failed")
        if samples["site-net"][0] in out or samples["site-domain"][0] in out:
            return fail("hits must show file and line, not the text")

        # Allow-globs hide hits.
        cfg.write_text(json.dumps({**repo_doc, "allow": [
            {"glob": "notes.txt", "reason": "fixture"},
            {"glob": "keep/**", "reason": "fixture tree"},
        ]}), encoding="utf-8")
        if quietly(lint, root, with_patterns) != 0:
            return fail("allow-globs did not hide the hits")
        cfg.write_text(json.dumps(repo_doc), encoding="utf-8")

        # A clean tree passes strict mode.
        (root / "notes.txt").write_text("room-101 example.org 192.0.2.10\n", encoding="utf-8")
        (root / "keep" / "stay.txt").write_text("ok\n", encoding="utf-8")
        result, out = captured(lint, root, with_patterns)
        if result != 0 or "site-lint: files=0 lines=0 strict=1" not in out:
            return fail(f"a clean tree failed strict mode: {out!r}")

        # Every pattern finds its samples, so a pattern cannot be a no-op.
        blob = "\n".join(s for items in samples.values() for s in items)
        (root / "all.txt").write_text(blob + "\n", encoding="utf-8")
        counts, _files, _lines, _where = scan(root, config)
        missing = [ident for ident, n in counts.items() if n != len(samples[ident])]
        if missing:
            return fail(f"patterns missed a sample: {missing}")

        # Refusals: a repo-side pattern list, a named file that is missing, bad pattern files.
        cfg.write_text(json.dumps({**repo_doc, "patterns": pattern_doc["patterns"]}), encoding="utf-8")
        result, _out = captured(lint, root, {})
        if "must not list patterns" not in str(result):
            return fail("a pattern list in .site-lint.json was accepted")
        cfg.write_text(json.dumps(repo_doc), encoding="utf-8")
        result, _out = captured(lint, root, {PATTERNS_ENV: str(base / "missing.json")})
        if "cannot read SITE_LINT_PATTERNS file" not in str(result):
            return fail(f"a missing pattern file was accepted: {result}")
        for bad, why in (
            ({"patterns": []}, "non-empty"),
            ({"patterns": [{"id": "x", "regex": "("}]}, "bad regex"),
            ({"patterns": [{"id": "x", "regex": "a"}, {"id": "x", "regex": "b"}]}, "twice"),
            ({**pattern_doc, "allow": []}, "unknown keys"),
        ):
            site.write_text(json.dumps(bad), encoding="utf-8")
            result, _out = captured(lint, root, with_patterns)
            if why not in str(result):
                return fail(f"pattern file {bad} was not refused ({why}): {result}")
    print("site-lint self-test: ok")
    return 0


def main(argv: list) -> int:
    if "--self-test" in argv:
        return self_test()
    try:
        root = repo_root(Path.cwd())
    except SystemExit:
        root = repo_root(Path(__file__).resolve().parent)
    return lint(root, os.environ)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
