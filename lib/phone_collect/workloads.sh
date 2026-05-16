start_workload() {
  case "$PHASE" in
    dtc_ping)
      ping -i 1 -w "$DURATION" "$TARGET" > "${RAW_DIR}/ping.log" 2>&1 &
      PIDS="$PIDS $!"
      ;;
    dtc_tcp)
      python3 "${SCRIPT_DIR}/scripts/tcp_rtt_probe.py" \
        --host "$TCP_HOST" --port "$TCP_PORT" --duration "$DURATION" \
        --interval 1 --out "${RAW_DIR}/tcp_rtt.csv" > "${RAW_DIR}/tcp_rtt.log" 2>&1 &
      PIDS="$PIDS $!"
      ;;
    dtc_iperf|*_iperf*)
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
