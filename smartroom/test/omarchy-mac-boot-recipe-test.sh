#!/bin/bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "$here/../pkgbuilds/omarchy-mac-boot/recipe-test.sh"
