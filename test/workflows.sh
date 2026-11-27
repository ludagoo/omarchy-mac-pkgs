#!/usr/bin/env bash
# Every workflow is workflow_dispatch only. pull_request_target is not a trigger.
# Pins are required on the workflows this fork added. Upstream files keep their own pins.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$ROOT/.github/workflows" <<'PY'
import re
import sys
from pathlib import Path
import yaml

root = Path(sys.argv[1])
files = sorted(root.glob("*.yml"))
assert {p.name for p in files} >= {"check.yml", "tests.yml", "mac-manual.yml", "smartroom-ci.yml", "package-resolution.yml"}
forbidden = ("push", "pull_request", "pull_request_target", "schedule", "workflow_run", "release", "repository_dispatch")

def on_map(data, name):
    on = data.get(True)
    if on is None:
        on = data.get("on")
    if not isinstance(on, dict):
        raise SystemExit(f"{name}: trigger is not a mapping: {on!r}")
    return on

for path in files:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    keys = list(on_map(data, path.name))
    if keys != ["workflow_dispatch"]:
        raise SystemExit(f"{path.name}: trigger must be workflow_dispatch only, got {keys}")
    for word in forbidden:
        if word in keys:
            raise SystemExit(f"{path.name}: forbidden trigger {word}")
    if "pull_request_target" in text:
        raise SystemExit(f"{path.name}: pull_request_target")

text = (root / "check.yml").read_text(encoding="utf-8")
data = yaml.safe_load(text)
job = data["jobs"]["check"]
if job.get("runs-on") != "ubuntu-latest":
    raise SystemExit("check.yml must run on ubuntu-latest")
if "secrets." in text:
    raise SystemExit("check.yml names a secret")
if "bash bin/test-ci.sh" not in text:
    raise SystemExit("check.yml does not run bin/test-ci.sh")
step = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))
if not re.search(r"uses: actions/checkout@[0-9a-f]{40} # v[0-9]", text):
    raise SystemExit("check.yml checkout is not pinned")
if (step.get("with") or {}).get("persist-credentials") is not False:
    raise SystemExit("check.yml checkout keeps credentials")
ci = (root / "smartroom-ci.yml").read_text(encoding="utf-8")
if "secrets." in ci or "contents: write" in ci or "id-token" in ci:
    raise SystemExit("smartroom-ci.yml gained a secret or a write token")
print(f"workflows: {len(files)} dispatch-only")
PY
echo ok
