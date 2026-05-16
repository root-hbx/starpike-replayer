#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash plots/plot_all.sh -f INPUT_DIR

Generate PDF plots under INPUT_DIR/output for all sessions found in INPUT_DIR.
EOF
}

INPUT_DIR=""
while getopts ":f:h" opt; do
  case "$opt" in
    f) INPUT_DIR="$OPTARG" ;;
    h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [ -z "$INPUT_DIR" ]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/starpike_matplotlib}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${TMPDIR:-/tmp}/starpike_xdg_cache}"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "$XDG_CACHE_HOME"

cd "$REPO_ROOT"
exec "$PYTHON_BIN" "$SCRIPT_DIR/plot_all.py" -f "$INPUT_DIR"
