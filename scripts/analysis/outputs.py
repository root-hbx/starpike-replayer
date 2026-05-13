from __future__ import annotations

import csv
import json
from pathlib import Path

from .activity import PROXY_CATEGORIES, combine_activity_csvs, write_activity_rate
from .common import read_manifest
from .cpu import cpu_busy_points, process_cpu_rows, summarize_cpu_delta
from .iperf import iperf_rows
from .signal import signal_rows


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


def write_signal_outputs(sessions: list[Path], out_dir: Path) -> None:
    rows: list[dict[str, str]] = []
    for session in sessions:
        rows.extend(signal_rows(session))
    with (out_dir / "signal_timeseries.csv").open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "session",
            "phase",
            "epoch",
            "phone_id",
            "network_type",
            "operator",
            "lte_rssi_dbm",
            "lte_rsrp_dbm",
            "lte_rsrq_db",
            "lte_sinr_db",
            "lte_cqi",
            "lte_ta",
            "nr_ss_rsrp_dbm",
            "nr_ss_rsrq_db",
            "nr_ss_sinr_db",
            "nr_timing_advance",
            "pci",
            "tac",
            "earfcn",
            "nr_arfcn",
            "source",
            "confidence",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_all_outputs(sessions: list[Path], out_dir: Path) -> None:
    per_session_outs: list[Path] = []
    for session in sessions:
        if not session.exists():
            raise SystemExit(f"session not found: {session}")
        session_out = out_dir / f"_session_{session.name}"
        session_out.mkdir(parents=True, exist_ok=True)
        write_activity_rate(session, session_out)
        per_session_outs.append(session_out)

    combine_activity_csvs(per_session_outs, out_dir)
    write_cpu_outputs(sessions, out_dir)
    write_iperf_outputs(sessions, out_dir)
    write_signal_outputs(sessions, out_dir)

    metadata = {
        "proxy_categories": PROXY_CATEGORIES,
        "activity_caption": (
            "AP-visible cellular activity proxy rate on Pixel 10. These are not "
            "modem-internal OTA messages and should not be interpreted as "
            "PHY/MAC/RLC/PDCP/RRC message rates."
        ),
        "signal_caption": (
            "Signal metrics are Android/Termux-visible fields. Empty values mean "
            "the platform reported unknown or the field was unavailable."
        ),
    }
    (out_dir / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
