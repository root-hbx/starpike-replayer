precheck() {
  echo "phone_collect precheck"
  missing_required=""
  for c in sh awk sed date ps logcat dumpsys settings service cmd ip ss ping python3; do
    if ! have_cmd "$c"; then
      missing_required="${missing_required} ${c}"
    fi
  done

  if [ -z "$missing_required" ]; then
    echo "required_tools: OK"
  else
    echo "required_tools: MISSING${missing_required}"
  fi

  missing_optional=""
  if ! have_cmd termux-telephony-cellinfo; then
    missing_optional="${missing_optional} termux-telephony-cellinfo"
  fi
  if ! have_cmd termux-location; then
    missing_optional="${missing_optional} termux-location"
  fi
  if ! have_cmd iperf3; then
    missing_optional="${missing_optional} iperf3"
  fi

  if [ -z "$missing_optional" ]; then
    echo "optional_tools: OK"
  else
    echo "optional_tools: MISSING${missing_optional}"
  fi

  echo "root_uid: $(id -u 2>/dev/null || echo unknown)"
  echo "android_release: $(getprop ro.build.version.release 2>/dev/null || echo unknown)"
  echo "device: $(getprop ro.product.model 2>/dev/null || echo unknown)"
  echo "baseband: $(getprop gsm.version.baseband 2>/dev/null || echo unknown)"
  probe_traffic_ifaces
}
