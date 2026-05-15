# Checklist + Measurement

Run these commands on the Pixel 10 in `Termux` from the repository root.

```sh
cd starpike-replayer
```

## 1. Precheck

```sh
sh phone_collect.sh --precheck
```

Confirm root:

```sh
su -c id
```

Confirm the cellular network interface:

```sh
cat /proc/net/dev
```

If you see `rmnet_data0`, use this in all measurement commands:

```sh
--iface rmnet_data0
```

If the active cellular interface is different, replace `rmnet_data0` below with
that interface name.

Multiple cellular interfaces can be recorded with a comma-separated list. Do
not include VPN interfaces such as `tun0`.

```sh
--iface rmnet_data3,rmnet_ipa0
```

For example, on my *One Plus* phone, it's `rmnet_ipa0` and `rmnet_data3`.

## Pixel 10 DTC-Oriented Raw Capture

For the Japan Pixel 10 run, keep the legacy samplers enabled and add the
opt-in DTC-oriented raw sources:

```sh
--enable-pixel-context \
--enable-signal-samples \
--enable-location \
--enable-radio-events
```

These add:

- `raw/device_context.json` and `raw/device_context.log`: model/build/baseband,
  radio, phone, and GNSS context.
- `raw/signal_samples.jsonl`: parsed Android-visible signal and cell fields,
  including RSRP/RSSI/RSRQ/SINR/CQI/TA when the platform exposes them.
- `raw/location_gnss.jsonl`: GNSS samples from `termux-location`, if available.
- `raw/radio_events.log`: filtered RRC/registration/attach/handover/auth and
  signal-related radio log events.

The collector now always records a broader AP-visible raw capture profile:

- `raw/logcat_all.log`: all Android logcat buffers, in addition to
  `raw/radio.log`.
- `raw/session_context_start.log` and `raw/session_context_end.log`: full
  start/end snapshots of `getprop`, Android settings, service lists, major
  telephony/connectivity dumps, routes, sockets, and netdev state.
- `raw/telephony_snapshots.log`: repeated telephony, phone, carrier config,
  subscription, IMS, satellite, connectivity, and cell-info snapshots.
- `raw/network_context.log`: repeated routing, socket, netstats, Wi-Fi,
  connectivity, and procfs network snapshots.
- `raw/netdev_all.tsv`: all-interface counters. `raw/netdev.tsv` still records
  only the interface list passed through `--iface`.

If Clash Meta for Android or another VPN is enabled, keep it enabled for the
whole phase if that is part of the scenario. Afterward, use
`raw/network_context.log`, `raw/netdev_all.tsv`, and the start/end context logs
to distinguish `rmnet*`, `wlan*`, `swlan*`, `tun*`, and VPN-routed traffic.

Android unknown sentinel values such as `2147483647` are treated as missing by
the host-side analysis. Precise TA, CQI, Doppler/frequency shift, RRC setup
delay, and attach phase breakdown still require the phone to expose those fields
or an external modem diagnostic log copied via `--diag-dir DIR`.

## 2. Airplane Baseline

Manually enable airplane mode. Wait 30 seconds.

```sh
sh phone_collect.sh --phase airplane_idle --duration 300 --out ./sessions --iface rmnet_data0
```

## 3. Cellular Idle Baseline

Manually disable airplane mode. Connect to docomo/DTC. 

Wait 1 minute for the network state to stabilize.

```sh
sh phone_collect.sh \
  --phase cellular_idle \
  --duration 300 \
  --out ./sessions \
  --iface rmnet_data0 \
  --enable-pixel-context \
  --enable-signal-samples \
  --enable-location \
  --enable-radio-events
```

## 4. TCP Active Measurement

Required.

```sh
sh phone_collect.sh \
  --phase dtc_tcp \
  --duration 300 \
  --tcp-host 1.1.1.1 \
  --tcp-port 443 \
  --out ./sessions \
  --iface rmnet_data0 \
  --enable-pixel-context \
  --enable-signal-samples \
  --enable-location \
  --enable-radio-events
```

## 5. Ping Active Measurement

Optional. Run this if ICMP works.

```sh
sh phone_collect.sh --phase dtc_ping --duration 300 --target 1.1.1.1 --out ./sessions --iface rmnet_data0
```

## 6. iperf3 Active Measurement

Optional. Run this only if you have an iperf3 server.

```sh
sh phone_collect.sh --phase dtc_iperf --duration 300 --iperf-server YOUR_IPERF_SERVER --iperf-bw 256K --out ./sessions --iface rmnet_data0
```

For bandwidth-capacity measurement, omit `--iperf-bw`:

```sh
sh phone_collect.sh --phase dtc_iperf --duration 300 --iperf-server YOUR_IPERF_SERVER --out ./sessions --iface rmnet_data0
```

Use `--iperf-bw 256K` only when you want a capped low-rate load instead of a
capacity test.

## 7. Confirm Data

```sh
ls sessions
find sessions -maxdepth 2 -type f | head -50
```

## 8. Pack Data

```sh
tar -czf sessions_jp.tar.gz sessions
```

## 9. Analyze On Host

Transfer `sessions_jp.tar.gz` to the host, then run:

```sh
tar -xzf sessions_jp.tar.gz
python3 scripts/analyze_sessions.py \
  --baseline-airplane sessions/airplane_idle_... \
  --baseline-cellular sessions/cellular_idle_... \
  --active sessions/dtc_tcp_... \
  --active sessions/dtc_ping_... \
  --out results
```

The analyzer now also writes `signal_timeseries.csv` when either
`raw/signal_samples.jsonl` or `raw/telephony_snapshots.log` contains parseable
signal fields.

If `dtc_ping` was not collected, remove this line:

```sh
--active sessions/dtc_ping_... \
```
