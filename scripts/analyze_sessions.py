#!/usr/bin/env python3
"""Analyze Pixel AP-visible NTN measurement sessions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROXY_CATEGORIES = [
    "radio_control_events",
    "cell_state_events",
    "signal_metric_updates",
    "user_plane_packets",
    "tcp_probe_events",
]

SIGNAL_RE = re.compile(r"SignalStrength|RSRP|RSRQ|RSSI|RSSNR|SINR|ssRsrp|ssRsrq|ssSinr|csiRsrp|level", re.I)
CELL_STATE_RE = re.compile(
    r"ServiceState|CellIdentity|CellInfo|NetworkRegistrationInfo|PhysicalChannel|"
    r"voiceRegState|dataRegState|mDataNetworkType|mVoiceNetworkType|nrState|"
    r"registered|roaming|operator|PLMN|\bTac\b|\bCi=|\bPci=",
    re.I,
)
RADIO_CONTROL_RE = re.compile(
    r"RIL|RILJ|RILC|Radio|DataCall|setupDataCall|deactivateDataCall|IMS|Ims|"
    r"APN|DcTracker|DataNetwork|PhoneSwitcher|CarrierConfig|Subscription|"
    r"REGISTRATION|registration|attach|detach|PDP|PDN|allowedNetwork",
    re.I,
)
LOGCAT_TS_RE = re.compile(r"^\s*(?P<ts>\d{9,}(?:\.\d+)?)\s+")
SNAPSHOT_RE = re.compile(r"^### SNAPSHOT (?P<ts>\d+(?:\.\d+)?)")


@dataclass
class CpuPoint:
    ts: float
    label: str
    busy_pct: float


def floor_second(ts: float, origin: float) -> int:
    return int(math.floor(ts - origin))


def read_manifest(session: Path) -> dict:
    path = session / "manifest.json"
    if not path.exists():
        return {"phase": session.name, "start_epoch": None}
    return json.loads(path.read_text(encoding="utf-8"))


def iter_proc_stat(path: Path) -> Iterable[tuple[float, str, list[int]]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                ts_text, stat_line = line.split("\t", 1)
                parts = stat_line.split()
                if not parts[0].startswith("cpu"):
                    continue
                yield float(ts_text), parts[0], [int(x) for x in parts[1:]]
            except (ValueError, IndexError):
                continue


def cpu_busy_points(session: Path) -> list[CpuPoint]:
    previous: dict[str, tuple[float, list[int]]] = {}
    points: list[CpuPoint] = []
    for ts, label, values in iter_proc_stat(session / "raw" / "proc_stat.tsv") or []:
        if label in previous:
            prev_ts, prev = previous[label]
            total_delta = sum(values) - sum(prev)
            idle_delta = (values[3] + (values[4] if len(values) > 4 else 0)) - (
                prev[3] + (prev[4] if len(prev) > 4 else 0)
            )
            if total_delta > 0:
                busy = 100.0 * (1.0 - idle_delta / total_delta)
                points.append(CpuPoint(ts=ts, label=label, busy_pct=max(0.0, min(100.0, busy))))
        previous[label] = (ts, values)
    return points


def parse_pid_stat_line(stat_line: str) -> tuple[int, int] | None:
    # /proc/[pid]/stat has comm in parentheses; fields 14 and 15 are utime/stime.
    end = stat_line.rfind(")")
    if end < 0:
        return None
    tail = stat_line[end + 2 :].split()
    try:
        return int(tail[11]), int(tail[12])
    except (ValueError, IndexError):
        return None


def process_cpu_rows(session: Path) -> list[dict[str, str]]:
    path = session / "raw" / "proc_pid_stat.tsv"
    if not path.exists():
        return []
    last: dict[tuple[str, str], tuple[float, int]] = {}
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ts_text, pid, cmd, stat_line = line.rstrip("\n").split("\t", 3)
                parsed = parse_pid_stat_line(stat_line)
                if parsed is None:
                    continue
                ts = float(ts_text)
                ticks = parsed[0] + parsed[1]
                key = (pid, cmd)
                if key in last:
                    prev_ts, prev_ticks = last[key]
                    dt = ts - prev_ts
                    if dt > 0:
                        # Android kernels commonly use 100 ticks/s. This is a process
                        # trend metric, not a replacement for perf-based attribution.
                        cpu_pct = 100.0 * ((ticks - prev_ticks) / 100.0) / dt
                        rows.append(
                            {
                                "session": session.name,
                                "epoch": f"{ts:.6f}",
                                "pid": pid,
                                "cmd": cmd,
                                "cpu_pct_approx": f"{max(0.0, cpu_pct):.6f}",
                            }
                        )
                last[key] = (ts, ticks)
            except ValueError:
                continue
    return rows


def classify_log_line(line: str) -> str | None:
    if SIGNAL_RE.search(line):
        return "signal_metric_updates"
    if CELL_STATE_RE.search(line):
        return "cell_state_events"
    if RADIO_CONTROL_RE.search(line):
        return "radio_control_events"
    return None


def parse_radio_log(session: Path, origin: float) -> Counter[tuple[int, str]]:
    counts: Counter[tuple[int, str]] = Counter()
    path = session / "raw" / "radio.log"
    if not path.exists():
        return counts
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = LOGCAT_TS_RE.match(line)
            if not match:
                continue
            category = classify_log_line(line)
            if category is None:
                continue
            sec = floor_second(float(match.group("ts")), origin)
            if sec >= 0:
                counts[(sec, category)] += 1
    return counts


def parse_telephony_snapshots(session: Path, origin: float) -> Counter[tuple[int, str]]:
    counts: Counter[tuple[int, str]] = Counter()
    path = session / "raw" / "telephony_snapshots.log"
    if not path.exists():
        return counts

    current_ts: float | None = None
    current_lines: list[str] = []
    previous_digest: str | None = None

    def flush() -> None:
        nonlocal previous_digest
        if current_ts is None or not current_lines:
            return
        text = "\n".join(current_lines)
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        sec = floor_second(current_ts, origin)
        if sec < 0:
            return
        if SIGNAL_RE.search(text):
            counts[(sec, "signal_metric_updates")] += 1
        if previous_digest is not None and digest != previous_digest and CELL_STATE_RE.search(text):
            counts[(sec, "cell_state_events")] += 1
        previous_digest = digest

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = SNAPSHOT_RE.match(line)
            if match:
                flush()
                current_ts = float(match.group("ts"))
                current_lines = []
            else:
                current_lines.append(line.rstrip("\n"))
        flush()
    return counts


def parse_netdev(session: Path, origin: float) -> Counter[tuple[int, str]]:
    counts: Counter[tuple[int, str]] = Counter()
    path = session / "raw" / "netdev.tsv"
    if not path.exists():
        return counts
    previous: dict[str, tuple[float, int, int]] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ts_text, iface, _rx_bytes, rx_packets, _tx_bytes, tx_packets = line.rstrip("\n").split("\t")
                ts = float(ts_text)
                packets = int(rx_packets) + int(tx_packets)
            except ValueError:
                continue
            if iface in previous:
                _prev_ts, prev_packets, prev_sec = previous[iface]
                delta = max(0, packets - prev_packets)
                sec = floor_second(ts, origin)
                if sec >= 0:
                    counts[(sec, "user_plane_packets")] += delta
                previous[iface] = (ts, packets, sec)
            else:
                previous[iface] = (ts, packets, floor_second(ts, origin))
    return counts


def parse_probe_logs(session: Path, origin: float) -> Counter[tuple[int, str]]:
    counts: Counter[tuple[int, str]] = Counter()
    raw = session / "raw"

    tcp = raw / "tcp_rtt.csv"
    if tcp.exists():
        with tcp.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    sec = floor_second(float(row["epoch"]), origin)
                except (ValueError, KeyError):
                    continue
                if sec >= 0:
                    counts[(sec, "tcp_probe_events")] += 1

    ping = raw / "ping.log"
    if ping.exists():
        # Android ping logs usually do not include epoch timestamps. Distribute
        # successful replies by read order at 1 Hz from session origin.
        index = 0
        with ping.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "time=" in line or "bytes from" in line:
                    counts[(index, "tcp_probe_events")] += 1
                    index += 1

    iperf = raw / "iperf3.json"
    if iperf.exists():
        try:
            data = json.loads(iperf.read_text(encoding="utf-8", errors="replace"))
            for interval in data.get("intervals", []):
                start = int(math.floor(interval.get("sum", {}).get("start", 0)))
                counts[(start, "tcp_probe_events")] += 1
        except json.JSONDecodeError:
            pass

    return counts


def merge_counts(*items: Counter[tuple[int, str]]) -> Counter[tuple[int, str]]:
    merged: Counter[tuple[int, str]] = Counter()
    for item in items:
        merged.update(item)
    return merged


def session_origin(session: Path, manifest: dict) -> float:
    if manifest.get("start_epoch") is not None:
        return float(manifest["start_epoch"])
    proc = session / "raw" / "proc_stat.tsv"
    if proc.exists():
        with proc.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    return float(line.split("\t", 1)[0])
                except ValueError:
                    continue
    return 0.0


def write_activity_rate(session: Path, out_dir: Path) -> Path:
    manifest = read_manifest(session)
    origin = session_origin(session, manifest)
    counts = merge_counts(
        parse_radio_log(session, origin),
        parse_telephony_snapshots(session, origin),
        parse_netdev(session, origin),
        parse_probe_logs(session, origin),
    )
    max_sec = max((sec for sec, _cat in counts), default=0)
    out_path = out_dir / "activity_proxy_rate_1s.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["session", "phase", "second", *PROXY_CATEGORIES])
        for sec in range(max_sec + 1):
            writer.writerow(
                [
                    session.name,
                    manifest.get("phase", session.name),
                    sec,
                    *[counts[(sec, category)] for category in PROXY_CATEGORIES],
                ]
            )
    return out_path


def write_cpu_outputs(sessions: list[Path], out_dir: Path) -> None:
    with (out_dir / "ap_cpu_timeseries.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["session", "phase", "epoch", "cpu_label", "busy_pct"])
        for session in sessions:
            phase = read_manifest(session).get("phase", session.name)
            for point in cpu_busy_points(session):
                writer.writerow([session.name, phase, f"{point.ts:.6f}", point.label, f"{point.busy_pct:.6f}"])

    process_rows: list[dict[str, str]] = []
    for session in sessions:
        process_rows.extend(process_cpu_rows(session))
    with (out_dir / "process_cpu_breakdown.csv").open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["session", "epoch", "pid", "cmd", "cpu_pct_approx"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(process_rows)

    summary = summarize_cpu_delta(sessions)
    (out_dir / "ap_cpu_delta_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def iperf_rows(session: Path) -> list[dict[str, str]]:
    manifest = read_manifest(session)
    path = session / "raw" / "iperf3.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []

    rows: list[dict[str, str]] = []
    for interval in data.get("intervals", []):
        summary = interval.get("sum", {})
        start = float(summary.get("start", 0.0))
        end = float(summary.get("end", start))
        bps = float(summary.get("bits_per_second", 0.0))
        rows.append(
            {
                "session": session.name,
                "phase": manifest.get("phase", session.name),
                "start_sec": f"{start:.6f}",
                "end_sec": f"{end:.6f}",
                "throughput_bps": f"{bps:.6f}",
                "throughput_mbps": f"{bps / 1e6:.6f}",
                "bytes": str(summary.get("bytes", "")),
                "retransmits": str(summary.get("retransmits", "")),
            }
        )
    return rows


def write_iperf_outputs(sessions: list[Path], out_dir: Path) -> None:
    rows: list[dict[str, str]] = []
    for session in sessions:
        rows.extend(iperf_rows(session))
    with (out_dir / "iperf_timeseries.csv").open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "session",
            "phase",
            "start_sec",
            "end_sec",
            "throughput_bps",
            "throughput_mbps",
            "bytes",
            "retransmits",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_cpu_delta(sessions: list[Path]) -> dict:
    by_phase: dict[str, list[float]] = defaultdict(list)
    for session in sessions:
        phase = read_manifest(session).get("phase", session.name)
        for point in cpu_busy_points(session):
            if point.label == "cpu":
                by_phase[phase].append(point.busy_pct)

    means = {phase: (sum(values) / len(values) if values else None) for phase, values in by_phase.items()}
    airplane = means.get("airplane_idle")
    cellular = means.get("cellular_idle")
    active = {k: v for k, v in means.items() if k.startswith("dtc_")}
    return {
        "mean_cpu_busy_pct_by_phase": means,
        "cellular_idle_minus_airplane_idle": None if airplane is None or cellular is None else cellular - airplane,
        "active_minus_cellular_idle": {
            phase: None if cellular is None or value is None else value - cellular for phase, value in active.items()
        },
        "claim": "AP CPU overhead measured on the Android application processor; not modem CPU.",
    }


def combine_activity_csvs(session_out_dirs: list[Path], out_dir: Path) -> Path:
    combined = out_dir / "activity_proxy_rate_1s.csv"
    with combined.open("w", encoding="utf-8", newline="") as out_fh:
        writer: csv.writer | None = None
        for session_out in session_out_dirs:
            path = session_out / "activity_proxy_rate_1s.csv"
            if not path.exists():
                continue
            with path.open(encoding="utf-8", newline="") as in_fh:
                reader = csv.reader(in_fh)
                header = next(reader, None)
                if header is None:
                    continue
                if writer is None:
                    writer = csv.writer(out_fh)
                    writer.writerow(header)
                for row in reader:
                    writer.writerow(row)
    return combined


def plot_outputs(out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        (out_dir / "PLOTS_SKIPPED.txt").write_text("matplotlib is not installed\n", encoding="utf-8")
        return

    activity = out_dir / "activity_proxy_rate_1s.csv"
    if activity.exists():
        rows = list(csv.DictReader(activity.open(encoding="utf-8", newline="")))
        if rows:
            # Plot each phase independently to avoid connecting unrelated sessions.
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                xs = [int(row["second"]) for row in subset]
                ys = [[float(row[cat]) for row in subset] for cat in PROXY_CATEGORIES]
                plt.figure(figsize=(8, 3))
                plt.stackplot(xs, ys, labels=PROXY_CATEGORIES)
                plt.xlabel("Time (second)")
                plt.ylabel("Events or packets/s")
                plt.title(f"AP-visible cellular activity proxy rate: {session}")
                plt.legend(loc="upper right", fontsize=7)
                plt.tight_layout()
                plt.savefig(out_dir / f"fig_activity_proxy_rate_stacked_{session}.pdf")
                plt.close()

            averages = {cat: 0.0 for cat in PROXY_CATEGORIES}
            for cat in PROXY_CATEGORIES:
                values = [float(row[cat]) for row in rows]
                averages[cat] = sum(values) / len(values)
            plt.figure(figsize=(7, 3))
            plt.bar(list(averages), [averages[cat] for cat in averages])
            values = list(averages.values())
            if any(value == 0 for value in values):
                plt.yscale("symlog", linthresh=0.1)
            else:
                plt.yscale("log")
            plt.ylabel("Events or packets/s")
            plt.xticks(rotation=25, ha="right")
            plt.tight_layout()
            plt.savefig(out_dir / "fig_activity_proxy_rate_bar.pdf")
            plt.close()

    cpu = out_dir / "ap_cpu_timeseries.csv"
    if cpu.exists():
        rows = [row for row in csv.DictReader(cpu.open(encoding="utf-8", newline="")) if row["cpu_label"] == "cpu"]
        if rows:
            plt.figure(figsize=(8, 3))
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                origin = float(subset[0]["epoch"])
                xs = [float(row["epoch"]) - origin for row in subset]
                ys = [float(row["busy_pct"]) for row in subset]
                plt.plot(xs, ys, label=session)
            plt.xlabel("Time (second)")
            plt.ylabel("AP CPU busy (%)")
            plt.legend(fontsize=7)
            plt.tight_layout()
            plt.savefig(out_dir / "fig_ap_cpu_delta.pdf")
            plt.close()

    iperf = out_dir / "iperf_timeseries.csv"
    if iperf.exists():
        rows = list(csv.DictReader(iperf.open(encoding="utf-8", newline="")))
        if rows:
            plt.figure(figsize=(8, 3))
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                xs = [(float(row["start_sec"]) + float(row["end_sec"])) / 2.0 for row in subset]
                ys = [float(row["throughput_mbps"]) for row in subset]
                plt.plot(xs, ys, marker="o", linewidth=1.2, markersize=2.5, label=session)
            plt.xlabel("Time (second)")
            plt.ylabel("Throughput (Mbps)")
            plt.legend(fontsize=7)
            plt.tight_layout()
            plt.savefig(out_dir / "fig_iperf_throughput.pdf")
            plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-airplane", type=Path)
    parser.add_argument("--baseline-cellular", type=Path)
    parser.add_argument("--active", type=Path, action="append", default=[])
    parser.add_argument("--session", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sessions = [p for p in [args.baseline_airplane, args.baseline_cellular, *args.active, *args.session] if p is not None]
    if not sessions:
        raise SystemExit("at least one session directory is required")
    args.out.mkdir(parents=True, exist_ok=True)

    per_session_outs: list[Path] = []
    for session in sessions:
        if not session.exists():
            raise SystemExit(f"session not found: {session}")
        session_out = args.out / f"_session_{session.name}"
        session_out.mkdir(parents=True, exist_ok=True)
        write_activity_rate(session, session_out)
        per_session_outs.append(session_out)

    combine_activity_csvs(per_session_outs, args.out)
    write_cpu_outputs(sessions, args.out)
    write_iperf_outputs(sessions, args.out)

    metadata = {
        "proxy_categories": PROXY_CATEGORIES,
        "activity_caption": (
            "AP-visible cellular activity proxy rate on Pixel 10. These are not "
            "modem-internal OTA messages and should not be interpreted as "
            "PHY/MAC/RLC/PDCP/RRC message rates."
        ),
    }
    (args.out / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if not args.no_plots:
        plot_outputs(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
