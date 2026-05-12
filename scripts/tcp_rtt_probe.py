#!/usr/bin/env python3
"""Lightweight TCP connect RTT probe for constrained cellular links."""

from __future__ import annotations

import argparse
import csv
import socket
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def probe(host: str, port: int, timeout: float) -> tuple[bool, float | None, str]:
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.time() - start) * 1000.0, ""
    except OSError as exc:
        return False, None, str(exc).replace("\n", " ")


def main() -> int:
    args = parse_args()
    end = time.time() + args.duration
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["epoch", "host", "port", "success", "connect_rtt_ms", "error"])
        while time.time() < end:
            ts = time.time()
            ok, rtt_ms, error = probe(args.host, args.port, args.timeout)
            writer.writerow([f"{ts:.6f}", args.host, args.port, int(ok), "" if rtt_ms is None else f"{rtt_ms:.3f}", error])
            fh.flush()
            sleep_for = max(0.0, args.interval - (time.time() - ts))
            time.sleep(sleep_for)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

