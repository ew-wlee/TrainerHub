#!/usr/bin/env bash
# Local macOS build, mainly for smoke-testing the PyInstaller recipe.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --extra dev
uv run pyinstaller packaging/trainerhub.spec --noconfirm --distpath dist --workpath build

echo "Built: dist/TrainerHub"
