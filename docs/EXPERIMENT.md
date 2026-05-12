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

## 2. Airplane Baseline

Manually enable airplane mode. Wait 30 seconds.

```sh
sh phone_collect.sh --phase airplane_idle --duration 300 --out ./sessions --iface rmnet_data0
```

## 3. Cellular Idle Baseline

Manually disable airplane mode. Connect to docomo/DTC. 

Wait 1 minute for the network state to stabilize.

```sh
sh phone_collect.sh --phase cellular_idle --duration 300 --out ./sessions --iface rmnet_data0
```

## 4. TCP Active Measurement

Required.

```sh
sh phone_collect.sh --phase dtc_tcp --duration 300 --tcp-host 1.1.1.1 --tcp-port 443 --out ./sessions --iface rmnet_data0
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

If `dtc_ping` was not collected, remove this line:

```sh
--active sessions/dtc_ping_... \
```
