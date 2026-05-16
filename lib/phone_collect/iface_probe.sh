PROBE_TARGET="8.8.8.8"

read_netdev_compact() {
  if [ ! -r /proc/net/dev ]; then
    return 1
  fi
  awk -F: '
    NR > 2 {
      iface=$1
      gsub(/^ +| +$/, "", iface)
      split($2, fields, / +/)
      print iface, fields[2], fields[3], fields[10], fields[11]
    }
  ' /proc/net/dev
}

join_csv() {
  awk '
    NF {
      if (out == "") {
        out=$0
      } else {
        out=out ", " $0
      }
    }
    END {
      if (out != "") {
        print out
      } else {
        print "NONE"
      }
    }
  '
}

classify_probe_ifaces() {
  wanted="$1"
  printf '%s\n' "$2" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | awk -v wanted="$wanted" '
    wanted == "cellular" && /^(rmnet|ccmni|wwan|swlan|pdp_ip)/ { print; next }
    wanted == "wifi" && /^wlan/ { print; next }
    wanted == "vpn" && /^(tun|ppp)/ { print; next }
  ' | join_csv
}

probe_traffic_ifaces() {
  tmp_dir="${TMPDIR:-${PREFIX:-/data/local/tmp}}"
  before="${tmp_dir}/phone_collect_netdev_before.$$"
  after="${tmp_dir}/phone_collect_netdev_after.$$"

  if ! read_netdev_compact > "$before" 2>/dev/null; then
    echo "probe_target: ${PROBE_TARGET}"
    echo "probe_status: FAILED"
    echo "traffic interfaces: UNKNOWN"
    echo "cellular_iface: NOT ACTIVATED"
    echo "wifi_iface: NOT ACTIVATED"
    echo "vpn_iface: NOT ACTIVATED"
    rm -f "$before" "$after" 2>/dev/null || true
    return
  fi

  if ping -c 3 -W 2 "$PROBE_TARGET" >/dev/null 2>&1; then
    probe_status="OK"
  else
    probe_status="FAILED"
  fi

  read_netdev_compact > "$after" 2>/dev/null || true

  traffic_ifaces="$(
    awk '
      NR == FNR {
        rx_b[$1]=$2; rx_p[$1]=$3; tx_b[$1]=$4; tx_p[$1]=$5
        next
      }
      $1 == "lo" { next }
      {
        drx_b=$2-rx_b[$1]
        drx_p=$3-rx_p[$1]
        dtx_b=$4-tx_b[$1]
        dtx_p=$5-tx_p[$1]
        if (drx_b > 0 || drx_p > 0 || dtx_b > 0 || dtx_p > 0) {
          print $1
        }
      }
    ' "$before" "$after" | join_csv
  )"

  if [ "$traffic_ifaces" = "NONE" ]; then
    cellular_ifaces="NOT ACTIVATED"
    wifi_ifaces="NOT ACTIVATED"
    vpn_ifaces="NOT ACTIVATED"
  else
    cellular_ifaces="$(classify_probe_ifaces cellular "$traffic_ifaces")"
    wifi_ifaces="$(classify_probe_ifaces wifi "$traffic_ifaces")"
    vpn_ifaces="$(classify_probe_ifaces vpn "$traffic_ifaces")"
    [ "$cellular_ifaces" = "NONE" ] && cellular_ifaces="NOT ACTIVATED"
    [ "$wifi_ifaces" = "NONE" ] && wifi_ifaces="NOT ACTIVATED"
    [ "$vpn_ifaces" = "NONE" ] && vpn_ifaces="NOT ACTIVATED"
  fi

  echo "probe_target: ${PROBE_TARGET}"
  echo "probe_status: ${probe_status}"
  echo "traffic interfaces: ${traffic_ifaces}"
  echo "cellular_iface: ${cellular_ifaces}"
  echo "wifi_iface: ${wifi_ifaces}"
  echo "vpn_iface: ${vpn_ifaces}"

  rm -f "$before" "$after" 2>/dev/null || true
}
