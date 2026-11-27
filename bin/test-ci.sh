#!/usr/bin/env bash
# Linux package suites. No image build, no Omarchy checkout, no hardware.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "test-ci: workflows"
bash "$ROOT/test/workflows.sh"

for package in omarchy-mac omarchy-mac-boot smartroom-boot-os smartroom-omarchy-helpers smartroom-release; do
  echo "test-ci: $package/test/all"
  bash "$ROOT/$package/test/all"
done

echo "test-ci: smartroom/test/all"
bash "$ROOT/smartroom/test/all"
echo "test-ci: passed"
