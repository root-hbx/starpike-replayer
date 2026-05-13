#!/usr/bin/env python3
"""Extract Android telephony signal/cell metrics from dumpsys text."""

from __future__ import annotations

import argparse
import json
import re
import sys


UNKNOWN_INT = 2147483647


def clean_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed == UNKNOWN_INT:
        return None
    return parsed


def search_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    return clean_int(match.group(1) if match else None)


def search_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def search_first_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    for value in match.groups():
        if value is not None:
            return value
    return None


def extract_phone_blocks(text: str) -> list[tuple[int | None, str]]:
    matches = list(re.finditer(r"^\s*Phone Id=(\d+)\s*$", text, re.M))
    if not matches:
        return [(None, text)]
    blocks: list[tuple[int | None, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        tail = text[match.start() : end]
        for boundary in ("\n  mPhoneCapability=", "\n  mActiveDataSubId=", "\nlocal logs:"):
            boundary_index = tail.find(boundary)
            if boundary_index >= 0:
                end = match.start() + boundary_index
                tail = text[match.start() : end]
                break
        blocks.append((clean_int(match.group(1)), text[match.start() : end]))
    return blocks


def extract_metrics(block: str) -> dict[str, object]:
    lte = search_text(r"mLte=CellSignalStrengthLte:([^,}]+(?:,[^,}]+)*)", block) or block
    nr = search_text(r"mNr=CellSignalStrengthNr:\{([^}]*)\}", block) or block
    cell_lte = search_text(r"CellIdentityLte:\{([^}]*)\}", block) or ""
    cell_nr = search_text(r"CellIdentityNr:\{([^}]*)\}", block) or ""
    physical = search_text(r"mPhysicalChannelConfigs=\[(.*?)\]", block) or ""

    network_type = search_text(r"TelephonyDisplayInfo \{network=([^,}]+)", block)
    if network_type is None:
        network_type = search_text(r"getRilDataRadioTechnology=\d+\(([^)]+)\)", block)

    return {
        "network_type": network_type,
        "operator": search_text(r"mOperatorAlphaLong=([^,}]*)", block),
        "mcc": search_first_text(r"mMcc\s*=\s*(\d+)|mMcc=(\d+)", block),
        "mnc": search_first_text(r"mMnc\s*=\s*(\d+)|mMnc=(\d+)", block),
        "lte_rssi_dbm": search_int(r"\brssi=(-?\d+)", lte),
        "lte_rsrp_dbm": search_int(r"\brsrp=(-?\d+)", lte),
        "lte_rsrq_db": search_int(r"\brsrq=(-?\d+)", lte),
        "lte_sinr_db": search_int(r"\brssnr=(-?\d+)", lte),
        "lte_cqi": search_int(r"\bcqi=(\d+)", lte),
        "lte_ta": search_int(r"\bta=(\d+)", lte),
        "nr_ss_rsrp_dbm": search_int(r"\bssRsrp\s*=\s*(-?\d+)", nr),
        "nr_ss_rsrq_db": search_int(r"\bssRsrq\s*=\s*(-?\d+)", nr),
        "nr_ss_sinr_db": search_int(r"\bssSinr\s*=\s*(-?\d+)", nr),
        "nr_csi_rsrp_dbm": search_int(r"\bcsiRsrp\s*=\s*(-?\d+)", nr),
        "nr_csi_rsrq_db": search_int(r"\bcsiRsrq\s*=\s*(-?\d+)", nr),
        "nr_timing_advance": search_int(r"\btimingAdvance\s*=\s*(\d+)", nr),
        "ci": search_int(r"\bmCi=(\d+)", cell_lte),
        "pci": search_int(r"\bmPci\s*=?\s*(\d+)", cell_lte or cell_nr),
        "tac": search_int(r"\bmTac\s*=?\s*(\d+)", cell_lte or cell_nr),
        "earfcn": search_int(r"\bmEarfcn=(\d+)", cell_lte),
        "nci": search_int(r"\bmNci\s*=\s*(\d+)", cell_nr),
        "nr_arfcn": search_int(r"\bmNrArfcn\s*=\s*(\d+)", cell_nr),
        "bandwidth_khz": search_int(r"mCellBandwidthDownlinkKhz=(\d+)", physical),
        "physical_cell_id": search_int(r"mPhysicalCellId=(\d+)", physical),
        "raw_source": "dumpsys telephony.registry",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epoch", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = sys.stdin.read()
    for phone_id, block in extract_phone_blocks(text):
        record = extract_metrics(block)
        record["epoch"] = args.epoch
        record["phone_id"] = phone_id
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
