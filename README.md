# STARPIKE Pixel NTN Replayer

Tools for Pixel 10 measurements that support STARPIKE NTN experiments.

This repository intentionally measures AP-visible quantities:

- AP cellular CPU overhead on the Android application processor.
- AP-visible cellular activity proxy rates.
- Android-visible radio signal/cell metrics, when available from `dumpsys`
  or Termux APIs.
- Broad AP-visible raw evidence: all logcat buffers, telephony/connectivity
  dumpsys snapshots, routing state, VPN/tunnel state, and all-interface counters.

**NOTE:** It does not decode modem-internal OTA messages and cannot be interpreted as
MobileInsight-equivalent PHY/MAC/RLC/PDCP/RRC message rates.

## Workflow

1. Run a field phase on the phone.
2. Capture raw evidence into a session directory.
3. Pull sessions to a host.
4. Analyze sessions into CSV summaries.
5. Plot proxy-rate, CPU-overhead, throughput, and signal timeseries outputs.

## Project Layout

- `phone_collect.sh`: small Android/Termux entrypoint.
- `lib/phone_collect/`: shell modules for argument parsing, manifests,
  prechecks, samplers, workloads, and lifecycle handling.
- `scripts/analyze_sessions.py`: small host-side analysis entrypoint.
- `scripts/analysis/`: analysis modules for activity, CPU, iperf, signal, and
  plotting outputs.
- `scripts/extract_telephony_metrics.py`: parser for Android telephony dumps.

See [docs/EXPERIMENT.md](docs/EXPERIMENT.md) for setup and details.

See [docs/oneplus_base.md](docs/oneplus_base.md) for getting started.
