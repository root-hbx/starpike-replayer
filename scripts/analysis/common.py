from __future__ import annotations

import json
import math
from pathlib import Path


def floor_second(ts: float, origin: float) -> int:
    return int(math.floor(ts - origin))


def read_manifest(session: Path) -> dict:
    path = session / "manifest.json"
    if not path.exists():
        return {"phase": session.name, "start_epoch": None}
    return json.loads(path.read_text(encoding="utf-8"))


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
