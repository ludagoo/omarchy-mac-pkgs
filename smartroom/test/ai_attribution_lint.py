#!/usr/bin/env python3
"""Fail when AI attribution appears outside ai-attribution-allow.txt.

The maintainer is the author of everything published here, so no file names an
AI tool as author or helper. Checked, case-insensitive:
- Co-Authored-By and Assisted-by trailers;
- "generated / written / drafted ... by / with" an AI tool, "AI-generated",
  "AI agent", "AI assistant";
- AI tool names in prose: Claude, Grok, Copilot, ChatGPT, Codex, Gemini, Fable,
  and Cursor as the tool (cursor-agent, .cursor/, "Cursor IDE", "by Cursor").
  A mouse, text, or database cursor is not the tool and does not match.

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

ALLOW_FILE = "ai-attribution-allow.txt"
TOOLS = r"claude|grok|cursor|copilot|chatgpt|codex|gemini|fable|llms?"
RULES = [
    ("trailer", re.compile(r"\bco-authored-by\b|\bassisted-by\b", re.IGNORECASE)),
    (
        "made-by",
        re.compile(
            r"\b(generated|written|drafted|authored|created|produced|assisted|coded)"
            r"\s+(with|by|using|via)\s+(an?\s+|the\s+)?(ai|" + TOOLS + r")\b",
            re.IGNORECASE,
        ),
    ),
    ("ai-made", re.compile(r"\bai[- ](generated|written|authored|assisted)\b", re.IGNORECASE)),
    ("ai-agent", re.compile(r"\bai[- ](agents?|assistants?|coding)\b", re.IGNORECASE)),
    ("tool", re.compile(r"\b(claude|grok|copilot|chatgpt|codex|gemini|fable)", re.IGNORECASE)),
    (
        "cursor-tool",
        re.compile(
            r"cursor[-_ ]agent|\.cursor/|\bcursor-run\b|\bcursor@"
            r"|\bcursor/[a-z0-9][\w.-]*"
            r"|\bcursor\s+(ide|editor|composer|rules?|bugbot|cloud|background)\b"
            r"|\b(by|with|using|via)\s+cursor\b(?![-_:.(\[])",
            re.IGNORECASE,
        ),
    ),
    ("robot", re.compile("\U0001f916")),
]


def find_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / ALLOW_FILE).is_file() and (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"{ALLOW_FILE} not found above the lint")


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


def matches(line: str) -> list[str]:
    return [name for name, rule in RULES if rule.search(line)]


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
            found = matches(line)
            if not found:
                continue
            if allowed(rel, line, line_rules, path_rules):
                continue
            hits.append(f"{rel}:{number}: [{','.join(found)}] {line.strip()[:200]}")
    return hits


def self_test(line_rules, path_rules) -> None:
    tool = "Clau" + "de"
    bad = [
        "Co-" + "Authored-By: " + tool + " <noreply@example.org>",
        "Assisted" + "-by: " + tool + ":model",
        "\U0001f916 Generated with " + tool + " Code",
        "# Written by " + tool,
        "this file was generated by " + "AI",
        "notes drafted with " + "Gro" + "k",
        "Synthetic, " + "AI-" + "generated test clips",
        "Run by an " + "AI " + "agent over SSH",
        "the " + "Cur" + "sor agent ran the tests",
        "see ." + "cursor/rules/x.mdc",
        "delegated to " + "Co" + "dex",
        "Gem" + "ini found the bug",
        "Fa" + "ble 5.2 wrote it",
        "Chat" + "GPT suggested this",
        "Co" + "pilot completion",
    ]
    good = [
        "cursor: pointer;",
        "cursor { invisible = true }",
        "hyprctl getoption cursor:invisible",
        "Rooms never show a mouse cursor.",
        "let changesCursor = null;",
        "vt.global_cursor_default=0",
        "params.set('before', cursor.before)",
        "the text cursor moves with the caret",
        "no-cursor-on-rooms",
        "Synthetic test clips (p01-p10). No real people.",
        "the Room Controller agent reports health",
        "the remote admin runs this over SSH",
    ]
    for line in bad:
        if not matches(line):
            raise SystemExit(f"self-test: not caught: {line!r}")
        if allowed("src/stray.txt", line, line_rules, path_rules):
            raise SystemExit(f"self-test: the allow list lets a stray line through: {line!r}")
    for line in good:
        if matches(line):
            raise SystemExit(f"self-test: false positive {matches(line)}: {line!r}")
    print("self-test ok")


def main() -> int:
    root = find_root()
    line_rules, path_rules, roots = load_rules(root / ALLOW_FILE)
    if "--self-test" in sys.argv[1:]:
        self_test(line_rules, path_rules)
        return 0
    hits = scan(root, line_rules, path_rules, roots)
    if hits:
        print(f"{len(hits)} AI attribution line(s) outside {ALLOW_FILE}:", file=sys.stderr)
        for hit in hits[:300]:
            print(hit, file=sys.stderr)
        return 1
    print("AI attribution ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
