cleanup() {
  if [ "${CLEANED_UP:-0}" = "1" ]; then
    return
  fi
  CLEANED_UP="1"
  trap - EXIT INT TERM

  for p in $PIDS; do
    kill "$p" >/dev/null 2>&1 || true
  done
  sleep 1
  for p in $PIDS; do
    kill -9 "$p" >/dev/null 2>&1 || true
  done
  record_session_context end
  finish_optional_samplers
  echo "$(now_epoch_ns) finished" >> "${SESSION_DIR}/collector.log"
}

collect_main() {
  if [ "$PRECHECK" = "1" ]; then
    precheck
    exit 0
  fi

  START_EPOCH="$(now_epoch)"
  SESSION_DIR="${OUT_ROOT}/${PHASE}_${START_EPOCH}"
  RAW_DIR="${SESSION_DIR}/raw"
  mkdir -p "$RAW_DIR"
  CELL_IFACE="$(detect_iface)"
  PIDS=""
  CLEANED_UP="0"

  write_manifest
  copy_diag_dir

  trap cleanup EXIT INT TERM

  echo "$(now_epoch_ns) starting ${PHASE}" > "${SESSION_DIR}/collector.log"
  precheck > "${SESSION_DIR}/precheck.log" 2>&1 || true

  start_radio_logcat
  start_all_logcat
  record_session_context start
  sample_proc_stat & PIDS="$PIDS $!"
  sample_processes & PIDS="$PIDS $!"
  sample_netdev & PIDS="$PIDS $!"
  sample_netdev_all & PIDS="$PIDS $!"
  sample_system_context & PIDS="$PIDS $!"
  sample_network_context & PIDS="$PIDS $!"
  sample_cpu_context & PIDS="$PIDS $!"
  start_optional_samplers
  start_workload

  sleep "$DURATION"
  cleanup
}
