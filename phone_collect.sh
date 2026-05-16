#!/system/bin/sh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

. "${SCRIPT_DIR}/lib/phone_collect/args.sh"
. "${SCRIPT_DIR}/lib/phone_collect/common.sh"
. "${SCRIPT_DIR}/lib/phone_collect/iface_probe.sh"
. "${SCRIPT_DIR}/lib/phone_collect/precheck.sh"
. "${SCRIPT_DIR}/lib/phone_collect/manifest.sh"
. "${SCRIPT_DIR}/lib/phone_collect/samplers.sh"
. "${SCRIPT_DIR}/lib/phone_collect/workloads.sh"
. "${SCRIPT_DIR}/lib/phone_collect/lifecycle.sh"

parse_args "$@"
collect_main
