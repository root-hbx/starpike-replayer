from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .common import floor_second, read_manifest, session_origin


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
                _prev_ts, prev_packets, _prev_sec = previous[iface]
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
