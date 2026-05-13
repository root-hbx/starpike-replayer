from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .common import read_manifest


@dataclass
class CpuPoint:
    ts: float
    label: str
    busy_pct: float


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
            _prev_ts, prev = previous[label]
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


def write_cpu_summary(path: Path, sessions: list[Path]) -> None:
    path.write_text(json.dumps(summarize_cpu_delta(sessions), indent=2), encoding="utf-8")
