precheck() {
  echo "phone_collect precheck"
  for c in sh awk sed date ps logcat dumpsys settings service cmd ip ss ping python3; do
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
  if have_cmd termux-location; then
    echo "ok: termux-location"
  else
    echo "missing: termux-location (only needed for --enable-location)"
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
  echo "root_uid: $(id -u 2>/dev/null || echo unknown)"
  echo "android_release: $(getprop ro.build.version.release 2>/dev/null || echo unknown)"
  echo "device: $(getprop ro.product.model 2>/dev/null || echo unknown)"
  echo "baseband: $(getprop gsm.version.baseband 2>/dev/null || echo unknown)"
  echo "active_routes:"
  if have_cmd ip; then
    ip route 2>&1
    ip rule 2>&1
  else
    echo "ip unavailable"
  fi
  echo "netdev_snapshot:"
  if [ ! -r /proc/net/dev ]; then
    echo "/proc/net/dev unavailable"
  elif [ "$(id -u 2>/dev/null)" = "0" ]; then
    cat /proc/net/dev 2>&1
  elif have_cmd su; then
    su -c "cat /proc/net/dev" 2>&1
  else
    cat /proc/net/dev 2>&1
  fi
}
