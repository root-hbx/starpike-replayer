from __future__ import annotations

import json
from pathlib import Path

from .common import read_manifest


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
