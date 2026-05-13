from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.extract_telephony_metrics import UNKNOWN_INT, extract_metrics, extract_phone_blocks

from .common import read_manifest


SNAPSHOT_RE = re.compile(r"^### SNAPSHOT (?P<ts>\d+(?:\.\d+)?)")
LOGCAT_TS_RE = re.compile(r"^\s*(?P<ts>\d{9,}(?:\.\d+)?)\s+")
SIGNAL_STRENGTH_RE = re.compile(r"SignalStrength:\{.*")


SIGNAL_FIELDS = [
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
]


def value_to_cell(value: object) -> str:
    if value is None:
        return ""
    if value == UNKNOWN_INT:
        return ""
    if isinstance(value, str) and value.lower() in {"null", "none"}:
        return ""
    return str(value)


def has_useful_radio_value(record: dict) -> bool:
    useful_fields = [
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
    ]
    return any(value_to_cell(record.get(field)) for field in useful_fields)


def row_from_record(session: Path, phase: str, record: dict, source: str, confidence: str) -> dict[str, str]:
    row = {
        "session": session.name,
        "phase": phase,
        "epoch": value_to_cell(record.get("epoch")),
        "source": source,
        "confidence": confidence,
    }
    for field in SIGNAL_FIELDS:
        row[field] = value_to_cell(record.get(field))
    return row


def iter_signal_sample_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def iter_snapshot_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    current_ts: float | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_ts is None or not current_lines:
            return
        text = "\n".join(current_lines)
        for phone_id, block in extract_phone_blocks(text):
            record = extract_metrics(block)
            record["epoch"] = current_ts
            record["phone_id"] = phone_id
            records.append(record)

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
    return records


def phone_id_from_radio_line(line: str) -> int | None:
    for pattern in (r"OplusSignalSmooth/(\d+)", r"onSignalStrengthsChanged\[(\d+)\]"):
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def iter_radio_signal_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    seen: set[tuple[float, int | None, str]] = set()
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            ts_match = LOGCAT_TS_RE.match(line)
            signal_match = SIGNAL_STRENGTH_RE.search(line)
            if not ts_match or not signal_match:
                continue
            text = signal_match.group(0)
            if "CellSignalStrength" not in text:
                continue
            ts = float(ts_match.group("ts"))
            phone_id = phone_id_from_radio_line(line)
            key = (ts, phone_id, text)
            if key in seen:
                continue
            seen.add(key)
            record = extract_metrics(text)
            record["epoch"] = ts
            record["phone_id"] = phone_id
            records.append(record)
    return records


def signal_rows(session: Path) -> list[dict[str, str]]:
    manifest = read_manifest(session)
    phase = manifest.get("phase", session.name)
    rows: list[dict[str, str]] = []

    sample_path = session / "raw" / "signal_samples.jsonl"
    for record in iter_signal_sample_records(sample_path):
        if not has_useful_radio_value(record):
            continue
        rows.append(row_from_record(session, phase, record, "signal_samples.jsonl", "high"))

    if rows:
        return rows

    radio_path = session / "raw" / "radio.log"
    for record in iter_radio_signal_records(radio_path):
        if not has_useful_radio_value(record):
            continue
        rows.append(row_from_record(session, phase, record, "radio.log", "medium"))

    if rows:
        return rows

    snapshot_path = session / "raw" / "telephony_snapshots.log"
    for record in iter_snapshot_records(snapshot_path):
        if not has_useful_radio_value(record):
            continue
        rows.append(row_from_record(session, phase, record, "telephony_snapshots.log", "medium"))
    return rows
