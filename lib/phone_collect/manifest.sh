write_manifest() {
  mkdir -p "$RAW_DIR"
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
  "enable_pixel_context": ${ENABLE_PIXEL_CONTEXT},
  "enable_signal_samples": ${ENABLE_SIGNAL_SAMPLES},
  "enable_location": ${ENABLE_LOCATION},
  "enable_radio_events": ${ENABLE_RADIO_EVENTS},
  "diag_dir": "$(json_escape "$DIAG_DIR")",
  "claim": "AP-visible cellular activity proxy rate; not modem-internal OTA messages"
}
EOF
}

copy_diag_dir() {
  if [ -z "$DIAG_DIR" ]; then
    return
  fi
  if [ ! -d "$DIAG_DIR" ]; then
    echo "$(now_epoch_ns) diag_dir_missing ${DIAG_DIR}" >> "${SESSION_DIR}/collector.log"
    return
  fi
  mkdir -p "${RAW_DIR}/diag"
  cp -R "${DIAG_DIR}/." "${RAW_DIR}/diag/" 2>> "${SESSION_DIR}/collector.log" || true
}
