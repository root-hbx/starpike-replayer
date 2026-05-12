#!/system/bin/sh
set -u

PHASE=""
DURATION="300" # TODO: can be customized
OUT_ROOT="./sessions"
IFACE=""
TARGET="1.1.1.1" # TODO: for ping
TCP_HOST="1.1.1.1" # TODO: for iperf3
TCP_PORT="443"
IPERF_SERVER=""
IPERF_BW="" # NOTE: default best-effort
INTERVAL="1"
PRECHECK="0"

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
  --precheck                only check commands and exit

The script records raw AP-visible data. It does not switch airplane mode,
force carrier selection, or decode modem-internal messages.
EOF
}

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

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_root() {
  if [ "$(id -u 2>/dev/null)" = "0" ]; then
    sh -c "$1"
  elif have_cmd su; then
    su -c "$1"
  else
    sh -c "$1"
  fi
}

now_epoch() {
  date +%s
}

now_epoch_ns() {
  date +%s.%N 2>/dev/null || date +%s
}

detect_iface() {
  if [ -n "$IFACE" ]; then
    echo "$IFACE"
    return
  fi
  awk -F: '/rmnet|ccmni|wwan|swlan|pdp_ip/ { gsub(/ /, "", $1); print $1; exit }' /proc/net/dev
}

precheck() {
  echo "phone_collect precheck"
  for c in sh awk sed date ps logcat dumpsys ping python3; do
    if have_cmd "$c"; then
      echo "ok: $c"
    else
      echo "missing: $c"
    fi
  done
  if have_cmd termux-telephony-cellinfo; then
    echo "ok: termux-telephony-cellinfo"
  else
    echo "missing: termux-telephony-cellinfo (fallback to dumpsys)"
  fi
  if have_cmd iperf3; then
    echo "ok: iperf3"
  else
    echo "missing: iperf3 (only needed for dtc_iperf)"
  fi
  DETECTED_IFACE="$(detect_iface)"
  if [ -n "$DETECTED_IFACE" ]; then
    echo "cellular_iface: $DETECTED_IFACE"
  else
    echo "cellular_iface: not detected; pass --iface manually"
  fi
  echo "netdev_snapshot:"
  if [ "$(id -u 2>/dev/null)" = "0" ]; then
    cat /proc/net/dev 2>&1
  elif have_cmd su; then
    su -c "cat /proc/net/dev" 2>&1
  else
    cat /proc/net/dev 2>&1
  fi
}

if [ "$PRECHECK" = "1" ]; then
  precheck
  exit 0
fi

START_EPOCH="$(now_epoch)"
SESSION_DIR="${OUT_ROOT}/${PHASE}_${START_EPOCH}"
RAW_DIR="${SESSION_DIR}/raw"
mkdir -p "$RAW_DIR"

CELL_IFACE="$(detect_iface)"

cat > "${SESSION_DIR}/manifest.json" <<EOF
{
  "phase": "${PHASE}",
  "start_epoch": ${START_EPOCH},
  "duration_sec": ${DURATION},
  "interval_sec": ${INTERVAL},
  "cellular_iface": "${CELL_IFACE}",
  "target": "${TARGET}",
  "tcp_host": "${TCP_HOST}",
  "tcp_port": ${TCP_PORT},
  "iperf_server": "${IPERF_SERVER}",
  "iperf_bw": "${IPERF_BW}",
  "claim": "AP-visible cellular activity proxy rate; not modem-internal OTA messages"
}
EOF

PIDS=""

cleanup() {
  for p in $PIDS; do
    kill "$p" >/dev/null 2>&1 || true
  done
  wait >/dev/null 2>&1 || true
  echo "$(now_epoch_ns) finished" >> "${SESSION_DIR}/collector.log"
}
trap cleanup EXIT INT TERM

sample_proc_stat() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    awk -v ts="$TS" '/^cpu/ { print ts "\t" $0 }' /proc/stat >> "${RAW_DIR}/proc_stat.tsv"
    sleep "$INTERVAL"
  done
}

sample_processes() {
  END=$((START_EPOCH + DURATION))
  PATTERN='phone|ims|ril|radio|telephony|netd|connectivity|qcril|vendor.*data|modem'
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    for d in /proc/[0-9]*; do
      PID="${d#/proc/}"
      [ -r "$d/cmdline" ] || continue
      CMD="$(tr '\000' ' ' < "$d/cmdline" 2>/dev/null | sed 's/[[:space:]]*$//')"
      if [ -z "$CMD" ] && [ -r "$d/comm" ]; then
        CMD="$(cat "$d/comm" 2>/dev/null)"
      fi
      echo "$CMD" | grep -Eiq "$PATTERN" || continue
      if [ -r "$d/stat" ]; then
        STAT="$(cat "$d/stat" 2>/dev/null)"
        echo "${TS}	${PID}	${CMD}	${STAT}" >> "${RAW_DIR}/proc_pid_stat.tsv"
      fi
    done
    sleep "$INTERVAL"
  done
}

sample_netdev() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    MATCHED="$(
      awk -v ts="$TS" -v want="$CELL_IFACE" -F':' '
      BEGIN {
        n = split(want, wanted, ",")
        for (i = 1; i <= n; i++) {
          gsub(/^ +| +$/, "", wanted[i])
          if (wanted[i] != "") wants[wanted[i]] = 1
        }
      }
      NR > 2 {
        iface=$1
        gsub(/^ +| +$/, "", iface)
        split($2, fields, /[ ]+/)
        if (want == "" || (iface in wants)) {
          print ts "\t" iface "\t" fields[2] "\t" fields[3] "\t" fields[10] "\t" fields[11]
        }
      }' /proc/net/dev
    )"
    if [ -n "$MATCHED" ]; then
      echo "$MATCHED" >> "${RAW_DIR}/netdev.tsv"
    else
      echo "${TS} NETDEV_IFACE_MISSING iface=${CELL_IFACE}" >> "${RAW_DIR}/netdev.err"
    fi
    sleep "$INTERVAL"
  done
}

sample_system_context() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    {
      echo "### SNAPSHOT ${TS}"
      echo "### dumpsys telephony.registry"
      dumpsys telephony.registry 2>&1
      echo "### dumpsys connectivity"
      dumpsys connectivity 2>&1
      echo "### termux-telephony-cellinfo"
      if have_cmd termux-telephony-cellinfo; then
        termux-telephony-cellinfo 2>&1
      else
        echo "termux-telephony-cellinfo unavailable"
      fi
    } >> "${RAW_DIR}/telephony_snapshots.log"
    sleep "$INTERVAL"
  done
}

sample_cpu_context() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    {
      echo "### SNAPSHOT ${TS}"
      echo "### softirqs"
      cat /proc/softirqs 2>&1
      echo "### cpufreq"
      for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq; do
        if [ -r "$f" ]; then
          VALUE="$(cat "$f" 2>/dev/null || true)"
          [ -n "$VALUE" ] && echo "$f $VALUE"
        fi
      done
      echo "### thermal"
      for z in /sys/class/thermal/thermal_zone*/temp; do
        if [ -r "$z" ]; then
          VALUE="$(cat "$z" 2>/dev/null || true)"
          [ -n "$VALUE" ] && echo "$z $VALUE"
        fi
      done
      echo "### battery"
      dumpsys battery 2>&1
    } >> "${RAW_DIR}/system_context.log"
    sleep "$INTERVAL"
  done
}

start_radio_logcat() {
  run_root "logcat -b radio -v epoch,usec" > "${RAW_DIR}/radio.log" 2> "${RAW_DIR}/radio.log.err" &
  PIDS="$PIDS $!"
}

start_workload() {
  case "$PHASE" in
    dtc_ping)
      ping -i 1 -w "$DURATION" "$TARGET" > "${RAW_DIR}/ping.log" 2>&1 &
      PIDS="$PIDS $!"
      ;;
    dtc_tcp)
      python3 "$(dirname "$0")/scripts/tcp_rtt_probe.py" \
        --host "$TCP_HOST" --port "$TCP_PORT" --duration "$DURATION" \
        --interval 1 --out "${RAW_DIR}/tcp_rtt.csv" > "${RAW_DIR}/tcp_rtt.log" 2>&1 &
      PIDS="$PIDS $!"
      ;;
    dtc_iperf)
      if [ -z "$IPERF_SERVER" ]; then
        echo "dtc_iperf requires --iperf-server" >> "${RAW_DIR}/iperf3.log"
      elif have_cmd iperf3; then
        IPERF_DURATION=$((DURATION - 2))
        if [ "$IPERF_DURATION" -lt 1 ]; then
          IPERF_DURATION="$DURATION"
        fi
        if [ -n "$IPERF_BW" ]; then
          iperf3 -c "$IPERF_SERVER" -t "$IPERF_DURATION" -b "$IPERF_BW" -i 1 \
            --json > "${RAW_DIR}/iperf3.json" 2> "${RAW_DIR}/iperf3.log" &
        else
          iperf3 -c "$IPERF_SERVER" -t "$IPERF_DURATION" -i 1 \
            --json > "${RAW_DIR}/iperf3.json" 2> "${RAW_DIR}/iperf3.log" &
        fi
        PIDS="$PIDS $!"
      else
        echo "iperf3 unavailable" >> "${RAW_DIR}/iperf3.log"
      fi
      ;;
    *)
      ;;
  esac
}

echo "$(now_epoch_ns) starting ${PHASE}" > "${SESSION_DIR}/collector.log"
precheck > "${SESSION_DIR}/precheck.log" 2>&1 || true

start_radio_logcat
sample_proc_stat & PIDS="$PIDS $!"
sample_processes & PIDS="$PIDS $!"
sample_netdev & PIDS="$PIDS $!"
sample_system_context & PIDS="$PIDS $!"
sample_cpu_context & PIDS="$PIDS $!"
start_workload

sleep "$DURATION"
cleanup
trap - EXIT INT TERM
