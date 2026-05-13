#!/usr/bin/env python3
"""Analyze Android AP-visible NTN measurement sessions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analysis.activity import (
    CELL_STATE_RE,
    LOGCAT_TS_RE,
    PROXY_CATEGORIES,
    RADIO_CONTROL_RE,
    SIGNAL_RE,
    SNAPSHOT_RE,
    classify_log_line,
    combine_activity_csvs,
    merge_counts,
    parse_netdev,
    parse_probe_logs,
    parse_radio_log,
    parse_telephony_snapshots,
    write_activity_rate,
)
from scripts.analysis.common import floor_second, read_manifest, session_origin
from scripts.analysis.cpu import (
    CpuPoint,
    cpu_busy_points,
    iter_proc_stat,
    parse_pid_stat_line,
    process_cpu_rows,
    summarize_cpu_delta,
)
from scripts.analysis.iperf import iperf_rows
from scripts.analysis.outputs import write_all_outputs, write_cpu_outputs, write_iperf_outputs, write_signal_outputs
from scripts.analysis.plots import plot_outputs
from scripts.analysis.signal import signal_rows


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

    write_all_outputs(sessions, args.out)

    if not args.no_plots:
        plot_outputs(args.out)
    return 0


__all__ = [
    "CELL_STATE_RE",
    "LOGCAT_TS_RE",
    "PROXY_CATEGORIES",
    "RADIO_CONTROL_RE",
    "SIGNAL_RE",
    "SNAPSHOT_RE",
    "CpuPoint",
    "classify_log_line",
    "combine_activity_csvs",
    "cpu_busy_points",
    "floor_second",
    "iperf_rows",
    "iter_proc_stat",
    "main",
    "merge_counts",
    "parse_args",
    "parse_netdev",
    "parse_pid_stat_line",
    "parse_probe_logs",
    "parse_radio_log",
    "parse_telephony_snapshots",
    "plot_outputs",
    "process_cpu_rows",
    "read_manifest",
    "session_origin",
    "signal_rows",
    "summarize_cpu_delta",
    "write_activity_rate",
    "write_all_outputs",
    "write_cpu_outputs",
    "write_iperf_outputs",
    "write_signal_outputs",
]


if __name__ == "__main__":
    raise SystemExit(main())
