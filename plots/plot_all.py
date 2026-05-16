#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scripts.analysis.activity import PROXY_CATEGORIES, merge_counts, parse_netdev, parse_probe_logs, parse_radio_log, parse_telephony_snapshots
from scripts.analysis.common import read_manifest, session_origin
from scripts.analysis.iperf import iperf_rows
from scripts.analysis.signal import signal_rows


PING_RE = re.compile(r"icmp_seq=(?P<seq>\d+).*time=(?P<rtt>[0-9.]+)\s*ms")
LOGCAT_TS_RE = re.compile(r"^\s*(?P<ts>\d{9,}(?:\.\d+)?)\s+")

EVENT_CLASSES: list[tuple[str, re.Pattern[str]]] = [
    ("data network", re.compile(r"DataNetwork|DNC|DN-\d+|setupDataCall|deactivateDataCall|DataCall", re.I)),
    ("network request", re.compile(r"onNetworkNeeded|onNetworkUnneeded|onAddNetworkRequest|onRemoveNetworkRequest|NetworkRequest", re.I)),
    ("validation/capability", re.compile(r"validation|VALIDATED|Capabilities changed|LinkUpBandwidth|LinkDnBandwidth", re.I)),
    ("registration/service/cell", re.compile(r"ServiceState|NetworkRegistrationInfo|CellIdentity|PhysicalChannel|registered|voiceRegState|dataRegState", re.I)),
    ("signal", re.compile(r"SignalStrength|RSRP|RSRQ|RSSI|SINR|ssRsrp|ssRsrq|ssSinr|cqi|level", re.I)),
    ("subscription/operator", re.compile(r"Subscription|carrierName|displayName|mcc=|mnc=|PLMN|operator", re.I)),
]

SIGNAL_PANELS = [
    ("LTE power", [("lte_rssi_dbm", "RSSI dBm"), ("lte_rsrp_dbm", "RSRP dBm")]),
    ("LTE quality", [("lte_rsrq_db", "RSRQ dB"), ("lte_sinr_db", "SINR dB")]),
    ("LTE scheduling", [("lte_cqi", "CQI"), ("lte_ta", "TA")]),
    ("NR quality", [("nr_ss_rsrp_dbm", "SS-RSRP dBm"), ("nr_ss_rsrq_db", "SS-RSRQ dB"), ("nr_ss_sinr_db", "SS-SINR dB"), ("nr_timing_advance", "NR TA")]),
]

CELL_CONTEXT_FIELDS = [
    ("network_type", "network_type"),
    ("operator", "operator"),
    ("pci", "PCI"),
    ("tac", "TAC"),
    ("earfcn", "EARFCN"),
    ("nr_arfcn", "NR-ARFCN"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--folder", type=Path, required=True)
    return parser.parse_args()


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def plot_label(value: str) -> str:
    if value == "中国广电":
        return "China Broadnet"
    try:
        value.encode("ascii")
        return value
    except UnicodeEncodeError:
        return value.encode("ascii", errors="replace").decode("ascii")


def discover_sessions(input_dir: Path) -> list[Path]:
    if (input_dir / "manifest.json").exists():
        return [input_dir]
    sessions = sorted({p.parent for p in input_dir.rglob("manifest.json")})
    return sessions


def to_float(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val):
        return None
    return val


def relative_epoch(row: dict[str, str], origin: float) -> float | None:
    val = to_float(row.get("epoch"))
    if val is None:
        return None
    return val - origin


def plot_ping_rtt(session: Path, out_dir: Path) -> Path | None:
    path = session / "raw" / "ping.log"
    if not path.exists():
        return None
    xs: list[float] = []
    ys: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = PING_RE.search(line)
        if not match:
            continue
        xs.append(float(match.group("seq")))
        ys.append(float(match.group("rtt")))
    if not xs:
        return None
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(xs, ys, marker="o", linewidth=1.2, markersize=2.5)
    ax.set_xlabel("ICMP sequence (approx seconds)")
    ax.set_ylabel("RTT (ms)")
    ax.set_title(f"RTT over time: {session.name}")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out = out_dir / f"fig_rtt_timeseries_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_tcp_rtt(session: Path, out_dir: Path) -> Path | None:
    path = session / "raw" / "tcp_rtt.csv"
    if not path.exists():
        return None
    rows = list(csv.DictReader(path.open(encoding="utf-8", errors="replace", newline="")))
    points: list[tuple[float, float]] = []
    manifest = read_manifest(session)
    origin = session_origin(session, manifest)
    for row in rows:
        x = to_float(row.get("epoch"))
        rtt = to_float(row.get("rtt_ms") or row.get("latency_ms") or row.get("connect_ms"))
        if x is not None and rtt is not None:
            points.append((x - origin, rtt))
    if not points:
        return None
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", linewidth=1.2, markersize=2.5)
    ax.set_xlabel("Time since session start (s)")
    ax.set_ylabel("TCP RTT/connect latency (ms)")
    ax.set_title(f"TCP RTT over time: {session.name}")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out = out_dir / f"fig_tcp_rtt_timeseries_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_iperf_bw(session: Path, out_dir: Path) -> Path | None:
    rows = iperf_rows(session)
    if not rows:
        return None
    xs = [(float(row["start_sec"]) + float(row["end_sec"])) / 2.0 for row in rows]
    ys = [float(row["throughput_mbps"]) for row in rows]
    retrans = [to_float(row.get("retransmits")) for row in rows]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(xs, ys, marker="o", linewidth=1.2, markersize=2.5)
    ax.set_xlabel("Time since iperf start (s)")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_title(f"iperf3 TCP bandwidth over time: {session.name}")
    ax.grid(True, alpha=0.25)
    if any(v is not None for v in retrans):
        ax2 = ax.twinx()
        ax2.bar(xs, [v or 0 for v in retrans], width=0.35, alpha=0.2, color="tab:red")
        ax2.set_ylabel("Retransmits/interval")
    fig.tight_layout()
    out = out_dir / f"fig_bw_iperf_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def iter_netdev_rows(path: Path) -> list[tuple[float, str, int, int, int, int]]:
    rows: list[tuple[float, str, int, int, int, int]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        try:
            rows.append((float(parts[0]), parts[1], int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])))
        except ValueError:
            continue
    return rows


def plot_iface_throughput(session: Path, out_dir: Path) -> Path | None:
    rows = iter_netdev_rows(session / "raw" / "netdev_all.tsv") or iter_netdev_rows(session / "raw" / "netdev.tsv")
    if not rows:
        return None
    by_iface: dict[str, list[tuple[float, int, int]]] = {}
    for ts, iface, rx_b, _rx_p, tx_b, _tx_p in rows:
        by_iface.setdefault(iface, []).append((ts, rx_b, tx_b))
    series: dict[str, tuple[list[float], list[float], list[float]]] = {}
    totals: list[tuple[int, str]] = []
    origin = min(ts for ts, _iface, _rx_b, _rx_p, _tx_b, _tx_p in rows)
    for iface, vals in by_iface.items():
        vals = sorted(vals)
        xs: list[float] = []
        rx_mbps: list[float] = []
        tx_mbps: list[float] = []
        total = 0
        for prev, cur in zip(vals, vals[1:]):
            dt = cur[0] - prev[0]
            if dt <= 0:
                continue
            drx = max(0, cur[1] - prev[1])
            dtx = max(0, cur[2] - prev[2])
            if drx == 0 and dtx == 0:
                continue
            xs.append(cur[0] - origin)
            rx_mbps.append(drx * 8.0 / dt / 1e6)
            tx_mbps.append(dtx * 8.0 / dt / 1e6)
            total += drx + dtx
        if xs:
            series[iface] = (xs, rx_mbps, tx_mbps)
            totals.append((total, iface))
    if not series:
        return None
    top_ifaces = [iface for _total, iface in sorted(totals, reverse=True)[:6]]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for iface in top_ifaces:
        xs, rx, tx = series[iface]
        ax.plot(xs, tx, linewidth=1.1, label=f"{iface} tx")
        if max(rx, default=0) > 0:
            ax.plot(xs, rx, linewidth=0.9, linestyle="--", label=f"{iface} rx")
    ax.set_xlabel("Time since first netdev sample (s)")
    ax.set_ylabel("Interface throughput (Mbps)")
    ax.set_title(f"Interface traffic over time: {session.name}")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    out = out_dir / f"fig_iface_throughput_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_signal_quality(session: Path, out_dir: Path) -> Path | None:
    rows = signal_rows(session)
    if not rows:
        return None
    origin = session_origin(session, read_manifest(session))
    plotted = False
    fig, axes = plt.subplots(len(SIGNAL_PANELS), 1, figsize=(9, 8), sharex=True)
    for ax, (title, fields) in zip(axes, SIGNAL_PANELS):
        panel_plotted = False
        for field, label in fields:
            points = [(relative_epoch(row, origin), to_float(row.get(field))) for row in rows]
            points = [(x, y) for x, y in points if x is not None and y is not None]
            if not points:
                continue
            ax.plot([p[0] for p in points], [p[1] for p in points], marker=".", linewidth=1.0, markersize=2.5, label=label)
            panel_plotted = True
            plotted = True
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.25)
        if panel_plotted:
            ax.legend(fontsize=7, ncol=4)
        else:
            ax.text(0.5, 0.5, "not available", transform=ax.transAxes, ha="center", va="center", color="0.5")
    axes[-1].set_xlabel("Time since session start (s)")
    fig.suptitle(f"UE signal quality over time: {session.name}", fontsize=12)
    fig.tight_layout()
    out = out_dir / f"fig_ue_signal_quality_{safe_name(session.name)}.pdf"
    if not plotted:
        plt.close(fig)
        return None
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_cell_context(session: Path, out_dir: Path) -> Path | None:
    rows = signal_rows(session)
    if not rows:
        return None
    origin = session_origin(session, read_manifest(session))
    fig, axes = plt.subplots(len(CELL_CONTEXT_FIELDS), 1, figsize=(9, 9), sharex=True)
    plotted = False
    for ax, (field, label) in zip(axes, CELL_CONTEXT_FIELDS):
        points_raw = [(relative_epoch(row, origin), row.get(field, "")) for row in rows if row.get(field, "")]
        if not points_raw:
            ax.text(0.5, 0.5, "not available", transform=ax.transAxes, ha="center", va="center", color="0.5")
            ax.set_ylabel(label)
            continue
        values = [p[1] for p in points_raw]
        numeric = [to_float(v) for v in values]
        if all(v is not None for v in numeric):
            ax.step([p[0] for p in points_raw], [float(v) for v in numeric if v is not None], where="post", linewidth=1.1)
        else:
            categories = {value: idx for idx, value in enumerate(dict.fromkeys(values))}
            ax.step([p[0] for p in points_raw], [categories[p[1]] for p in points_raw], where="post", linewidth=1.1)
            ax.set_yticks(list(categories.values()), [plot_label(value) for value in categories.keys()])
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.25)
        plotted = True
    axes[-1].set_xlabel("Time since session start (s)")
    fig.suptitle(f"UE cell context over time: {session.name}", fontsize=12)
    fig.tight_layout()
    out = out_dir / f"fig_ue_cell_context_{safe_name(session.name)}.pdf"
    if not plotted:
        plt.close(fig)
        return None
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_activity(session: Path, out_dir: Path) -> Path | None:
    manifest = read_manifest(session)
    origin = session_origin(session, manifest)
    counts = merge_counts(
        parse_radio_log(session, origin),
        parse_telephony_snapshots(session, origin),
        parse_netdev(session, origin),
        parse_probe_logs(session, origin),
    )
    if not counts:
        return None
    max_sec = max(sec for sec, _cat in counts)
    xs = list(range(max_sec + 1))
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for cat in PROXY_CATEGORIES:
        ys = [counts[(sec, cat)] for sec in xs]
        if any(ys):
            ax.plot(xs, ys, linewidth=1.1, label=cat)
    if not ax.lines:
        plt.close(fig)
        return None
    ax.set_xlabel("Time since session start (s)")
    ax.set_ylabel("Events or packets/s")
    ax.set_title(f"AP-visible activity proxy rate: {session.name}")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    out = out_dir / f"fig_ap_visible_activity_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def classify_event(line: str) -> str | None:
    for name, pattern in EVENT_CLASSES:
        if pattern.search(line):
            return name
    return None


def compact_event_label(line: str) -> str:
    text = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\[[^\]]{80,}\]", "[...]", text)
    return text[:95]


def plot_event_timeline(session: Path, out_dir: Path) -> Path | None:
    path = session / "raw" / "radio_events.log"
    if not path.exists():
        return None
    origin = session_origin(session, read_manifest(session))
    events: list[tuple[float, str, str]] = []
    seen: set[tuple[int, str, str]] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LOGCAT_TS_RE.match(line)
        if not match:
            continue
        cat = classify_event(line)
        if cat is None:
            continue
        ts = float(match.group("ts")) - origin
        if ts < -5:
            continue
        label = compact_event_label(line)
        key = (int(ts * 10), cat, label)
        if key in seen:
            continue
        seen.add(key)
        events.append((ts, cat, label))
    if not events:
        return None
    events.sort(key=lambda x: x[0])
    lanes = [name for name, _pat in EVENT_CLASSES]
    lane_index = {name: idx for idx, name in enumerate(lanes)}
    fig_height = max(4.0, 2.2 + len(lanes) * 0.45)
    fig, ax = plt.subplots(figsize=(11, fig_height))
    xs = [e[0] for e in events]
    ys = [lane_index[e[1]] for e in events]
    ax.scatter(xs, ys, s=22, alpha=0.8)
    for idx, (ts, cat, label) in enumerate(events[:80]):
        offset = 0.08 if idx % 2 == 0 else -0.18
        ax.text(ts, lane_index[cat] + offset, label, fontsize=5.5, rotation=25, ha="left", va="bottom")
    ax.set_yticks(range(len(lanes)), lanes)
    ax.set_xlabel("Time since session start (s)")
    ax.set_title(f"AP-visible UE/base-station interaction timeline: {session.name}")
    ax.grid(True, axis="x", alpha=0.25)
    ax.set_ylim(-0.6, len(lanes) - 0.4)
    fig.tight_layout()
    out = out_dir / f"fig_ue_gnb_event_timeline_{safe_name(session.name)}.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


PLOTTERS = [
    ("ping RTT", plot_ping_rtt),
    ("TCP RTT", plot_tcp_rtt),
    ("iperf bandwidth", plot_iperf_bw),
    ("interface throughput", plot_iface_throughput),
    ("UE signal quality", plot_signal_quality),
    ("UE cell context", plot_cell_context),
    ("AP-visible activity", plot_activity),
    ("UE-gNB event timeline", plot_event_timeline),
]


def main() -> int:
    args = parse_args()
    input_dir = args.folder
    if not input_dir.exists():
        raise SystemExit(f"input folder not found: {input_dir}")
    out_dir = input_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = discover_sessions(input_dir)
    summary: list[str] = [f"input: {input_dir}", f"sessions: {len(sessions)}"]
    if not sessions:
        summary.append("ERROR: no manifest.json found")
        (out_dir / "plot_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
        return 1

    for session in sessions:
        summary.append(f"\n[{session.name}]")
        for name, plotter in PLOTTERS:
            try:
                out = plotter(session, out_dir)
            except Exception as exc:  # Keep plotting non-blocking across data types.
                summary.append(f"ERROR {name}: {exc}")
                continue
            if out is None:
                summary.append(f"SKIP {name}")
            else:
                summary.append(f"OK {name}: {out.name}")

    (out_dir / "plot_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"wrote plots to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
