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
  if [ ! -r /proc/net/dev ]; then
    return
  fi
  awk -F: '/rmnet|ccmni|wwan|swlan|pdp_ip/ { gsub(/ /, "", $1); print $1; exit }' /proc/net/dev
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}
