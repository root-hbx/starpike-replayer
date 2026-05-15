PHASE=""
DURATION="300"
OUT_ROOT="./sessions"
IFACE=""
TARGET="1.1.1.1"
TCP_HOST="1.1.1.1"
TCP_PORT="443"
IPERF_SERVER=""
IPERF_BW=""
INTERVAL="1"
PRECHECK="0"
ENABLE_PIXEL_CONTEXT="0"
ENABLE_SIGNAL_SAMPLES="0"
ENABLE_LOCATION="0"
ENABLE_RADIO_EVENTS="0"
DIAG_DIR=""

usage() {
  cat <<'EOF'
Usage:
  phone_collect.sh --phase PHASE [options]

Required:
  --phase NAME              airplane_idle|cellular_idle|dtc_ping|dtc_tcp|dtc_iperf

Options:
  --duration SEC            phase duration, default 300
  --out DIR                 output root, default ./sessions
  --iface IFACE             iface or comma-separated ifaces, default auto-detect rmnet*/ccmni*/swlan*
  --target HOST             ping target, default 1.1.1.1
  --tcp-host HOST           TCP RTT target, default 1.1.1.1
  --tcp-port PORT           TCP RTT port, default 443
  --iperf-server HOST       iperf3 server for dtc_iperf
  --iperf-bw RATE           optional iperf3 target bitrate cap, default uncapped
  --interval SEC            sampler interval, default 1
  --enable-pixel-context    record one-shot device/radio/GNSS context
  --enable-signal-samples   record structured telephony signal/cell samples
  --enable-location         record GNSS/location samples when termux-location is available
  --enable-radio-events     record filtered radio/control-plane events from radio/all logcat
  --diag-dir DIR            copy external modem diagnostic logs into raw/diag
  --precheck                only check commands and exit

The script records broad AP-visible raw data, including all logcat buffers,
selected and all-interface netdev counters, routing/VPN state, and telephony
dumpsys snapshots. It does not switch airplane mode, force carrier selection,
or decode modem-internal messages.
EOF
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --phase) PHASE="$2"; shift 2 ;;
      --duration) DURATION="$2"; shift 2 ;;
      --out) OUT_ROOT="$2"; shift 2 ;;
      --iface) IFACE="$2"; shift 2 ;;
      --target) TARGET="$2"; shift 2 ;;
      --tcp-host) TCP_HOST="$2"; shift 2 ;;
      --tcp-port) TCP_PORT="$2"; shift 2 ;;
      --iperf-server) IPERF_SERVER="$2"; shift 2 ;;
      --iperf-bw) IPERF_BW="$2"; shift 2 ;;
      --interval) INTERVAL="$2"; shift 2 ;;
      --enable-pixel-context) ENABLE_PIXEL_CONTEXT="1"; shift ;;
      --enable-signal-samples) ENABLE_SIGNAL_SAMPLES="1"; shift ;;
      --enable-location) ENABLE_LOCATION="1"; shift ;;
      --enable-radio-events) ENABLE_RADIO_EVENTS="1"; shift ;;
      --diag-dir) DIAG_DIR="$2"; shift 2 ;;
      --precheck) PRECHECK="1"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
    esac
  done

  if [ "$PRECHECK" != "1" ] && [ -z "$PHASE" ]; then
    echo "--phase is required" >&2
    usage
    exit 2
  fi
}
