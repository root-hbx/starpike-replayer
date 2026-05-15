sample_proc_stat() {
  if [ ! -r /proc/stat ]; then
    echo "$(now_epoch_ns) PROC_STAT_UNAVAILABLE" >> "${RAW_DIR}/proc_stat.err"
    return
  fi
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
  if [ ! -r /proc/net/dev ]; then
    echo "$(now_epoch_ns) NETDEV_UNAVAILABLE" >> "${RAW_DIR}/netdev.err"
    return
  fi
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

record_pixel_context() {
  MODEL="$(getprop ro.product.model 2>/dev/null)"
  DEVICE="$(getprop ro.product.device 2>/dev/null)"
  FINGERPRINT="$(getprop ro.build.fingerprint 2>/dev/null)"
  ANDROID_RELEASE="$(getprop ro.build.version.release 2>/dev/null)"
  BASEBAND="$(getprop gsm.version.baseband 2>/dev/null)"
  RADIO_HAL="$(getprop init.svc.vendor.ril-daemon 2>/dev/null)"
  cat > "${RAW_DIR}/device_context.json" <<EOF
{
  "epoch": "$(now_epoch_ns)",
  "model": "$(json_escape "$MODEL")",
  "device": "$(json_escape "$DEVICE")",
  "build_fingerprint": "$(json_escape "$FINGERPRINT")",
  "android_release": "$(json_escape "$ANDROID_RELEASE")",
  "baseband": "$(json_escape "$BASEBAND")",
  "radio_hal": "$(json_escape "$RADIO_HAL")"
}
EOF
  {
    echo "### dumpsys phone"
    dumpsys phone 2>&1
    echo "### dumpsys location"
    dumpsys location 2>&1
  } > "${RAW_DIR}/device_context.log"
}

sample_signal_samples() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    if have_cmd python3; then
      dumpsys telephony.registry 2>&1 | python3 "${SCRIPT_DIR}/scripts/extract_telephony_metrics.py" --epoch "$TS" >> "${RAW_DIR}/signal_samples.jsonl" 2>> "${RAW_DIR}/signal_samples.err"
    else
      echo "{\"epoch\":${TS},\"source\":\"dumpsys telephony.registry\",\"error\":\"python3 unavailable\"}" >> "${RAW_DIR}/signal_samples.jsonl"
    fi
    sleep "$INTERVAL"
  done
}

sample_location() {
  END=$((START_EPOCH + DURATION))
  while [ "$(now_epoch)" -le "$END" ]; do
    TS="$(now_epoch_ns)"
    if have_cmd termux-location; then
      printf '{"epoch":%s,"source":"termux-location","location":' "$TS" >> "${RAW_DIR}/location_gnss.jsonl"
      termux-location -p gps 2>> "${RAW_DIR}/location_gnss.err" >> "${RAW_DIR}/location_gnss.jsonl"
      echo "}" >> "${RAW_DIR}/location_gnss.jsonl"
    else
      echo "{\"epoch\":${TS},\"source\":\"termux-location\",\"error\":\"termux-location unavailable\"}" >> "${RAW_DIR}/location_gnss.jsonl"
    fi
    sleep "$INTERVAL"
  done
}

start_radio_events() {
  : > "${RAW_DIR}/radio_events.log"
  : > "${RAW_DIR}/radio_events.err"
}

finish_radio_events() {
  [ "$ENABLE_RADIO_EVENTS" = "1" ] || return
  [ -r "${RAW_DIR}/radio.log" ] || return
  grep -Ei 'RRC|registration|attach|detach|DataCall|setupDataCall|deactivateDataCall|handover|TAU|Tracking Area|Authentication|Security mode|Identity|Random access|RACH|preamble|contention|SignalStrength|CellIdentity|PhysicalChannel' \
    "${RAW_DIR}/radio.log" > "${RAW_DIR}/radio_events.log" 2> "${RAW_DIR}/radio_events.err" || true
}

start_optional_samplers() {
  if [ "$ENABLE_PIXEL_CONTEXT" = "1" ]; then
    record_pixel_context
  fi
  if [ "$ENABLE_SIGNAL_SAMPLES" = "1" ]; then
    sample_signal_samples & PIDS="$PIDS $!"
  fi
  if [ "$ENABLE_LOCATION" = "1" ]; then
    sample_location & PIDS="$PIDS $!"
  fi
  if [ "$ENABLE_RADIO_EVENTS" = "1" ]; then
    start_radio_events
  fi
}

finish_optional_samplers() {
  finish_radio_events
}
