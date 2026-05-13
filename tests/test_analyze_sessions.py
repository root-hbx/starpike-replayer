import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import analyze_sessions
from scripts.extract_telephony_metrics import extract_metrics


class AnalyzeSessionsTest(unittest.TestCase):
    def test_cpu_busy_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp)
            raw = session / "raw"
            raw.mkdir()
            (raw / "proc_stat.tsv").write_text(
                "100.0\tcpu  100 0 100 800 0 0 0 0 0 0\n"
                "101.0\tcpu  150 0 150 850 0 0 0 0 0 0\n",
                encoding="utf-8",
            )
            points = analyze_sessions.cpu_busy_points(session)
            self.assertEqual(len(points), 1)
            self.assertAlmostEqual(points[0].busy_pct, 66.666666, places=4)

    def test_activity_proxy_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "dtc_ping_100"
            raw = session / "raw"
            raw.mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps({"phase": "dtc_ping", "start_epoch": 1700000100}),
                encoding="utf-8",
            )
            (raw / "radio.log").write_text(
                "         1700000100.100000  1  1 I RILJ: setupDataCall\n"
                "         1700000100.200000  1  1 I Phone: ServiceState changed\n"
                "         1700000101.100000  1  1 I Phone: SignalStrength rsrp=-95\n",
                encoding="utf-8",
            )
            (raw / "netdev.tsv").write_text(
                "1700000100.0\trmnet_data0\t100\t10\t100\t20\n"
                "1700000101.0\trmnet_data0\t200\t15\t300\t35\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "out"
            out.mkdir()
            analyze_sessions.write_activity_rate(session, out)
            with (out / "activity_proxy_rate_1s.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["radio_control_events"], "1")
            self.assertEqual(rows[0]["cell_state_events"], "1")
            self.assertEqual(rows[1]["signal_metric_updates"], "1")
            self.assertEqual(rows[1]["user_plane_packets"], "20")

    def test_activity_proxy_counts_multiple_ifaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "dtc_iperf_1700000200"
            raw = session / "raw"
            raw.mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps({"phase": "dtc_iperf", "start_epoch": 1700000200}),
                encoding="utf-8",
            )
            (raw / "netdev.tsv").write_text(
                "1700000200.0\trmnet_ipa0\t100\t10\t100\t20\n"
                "1700000200.0\trmnet_data3\t1000\t100\t1000\t200\n"
                "1700000201.0\trmnet_ipa0\t200\t15\t300\t35\n"
                "1700000201.0\trmnet_data3\t2000\t150\t3000\t260\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "out"
            out.mkdir()
            analyze_sessions.write_activity_rate(session, out)
            with (out / "activity_proxy_rate_1s.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[1]["user_plane_packets"], "130")

    def test_extract_lte_signal_metrics_filters_unknowns(self):
        block = (
            "mSignalStrength=SignalStrength:{"
            "mLte=CellSignalStrengthLte: rssi=-65 rsrp=-90 rsrq=-7 rssnr=22 "
            "cqiTableIndex=2147483647 cqi=2147483647 ta=2147483647 level=4,"
            "mNr=CellSignalStrengthNr:{ ssRsrp = 2147483647 ssRsrq = 2147483647 "
            "ssSinr = 2147483647 timingAdvance = 2147483647 },primary=CellSignalStrengthLte}\n"
            "mCellIdentity=CellIdentityLte:{ mCi=19695115 mPci=132 mTac=4136 "
            "mEarfcn=39148 mBands=[40] mBandwidth=20000 mMcc=460 mMnc=00 }\n"
            "mPhysicalChannelConfigs=[{mCellBandwidthDownlinkKhz=20000,mPhysicalCellId=132}]"
        )
        metrics = extract_metrics(block)
        self.assertEqual(metrics["lte_rssi_dbm"], -65)
        self.assertEqual(metrics["lte_rsrp_dbm"], -90)
        self.assertEqual(metrics["lte_rsrq_db"], -7)
        self.assertEqual(metrics["lte_sinr_db"], 22)
        self.assertIsNone(metrics["lte_cqi"])
        self.assertIsNone(metrics["lte_ta"])
        self.assertEqual(metrics["pci"], 132)
        self.assertEqual(metrics["tac"], 4136)
        self.assertEqual(metrics["earfcn"], 39148)

    def test_signal_rows_from_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "dtc_iperf_100"
            raw = session / "raw"
            raw.mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps({"phase": "dtc_iperf", "start_epoch": 100}),
                encoding="utf-8",
            )
            (raw / "telephony_snapshots.log").write_text(
                "### SNAPSHOT 100.0\n"
                "  Phone Id=0\n"
                "    mSignalStrength=SignalStrength:{mLte=CellSignalStrengthLte: "
                "rssi=-65 rsrp=-90 rsrq=-7 rssnr=22 cqi=2147483647 ta=2147483647 level=4,"
                "mNr=CellSignalStrengthNr:{ ssRsrp = 2147483647 ssRsrq = 2147483647 "
                "ssSinr = 2147483647 timingAdvance = 2147483647 },primary=CellSignalStrengthLte}\n"
                "    mCellIdentity=CellIdentityLte:{ mCi=19695115 mPci=132 mTac=4136 "
                "mEarfcn=39148 mMcc=460 mMnc=00 }\n",
                encoding="utf-8",
            )
            rows = analyze_sessions.signal_rows(session)
            self.assertEqual(rows[0]["lte_rsrp_dbm"], "-90")
            self.assertEqual(rows[0]["lte_cqi"], "")
            self.assertEqual(rows[0]["lte_ta"], "")

    def test_signal_rows_from_radio_log_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "dtc_iperf_100"
            raw = session / "raw"
            raw.mkdir(parents=True)
            (session / "manifest.json").write_text(
                json.dumps({"phase": "dtc_iperf", "start_epoch": 100}),
                encoding="utf-8",
            )
            (raw / "radio.log").write_text(
                "         1700000100.100000  1  1 D OplusSignalSmooth/0: notifySignalStrength, "
                "mSignalStrength: SignalStrength:{mLte=CellSignalStrengthLte: "
                "rssi=-63 rsrp=-90 rsrq=-6 rssnr=29 cqi=2147483647 ta=2147483647 level=4,"
                "mNr=CellSignalStrengthNr:{ ssRsrp = 2147483647 ssRsrq = 2147483647 "
                "ssSinr = 2147483647 timingAdvance = 2147483647 },primary=CellSignalStrengthLte}\n"
                "         1700000101.100000  1  1 D VirtualcommTelephonyCallback: onSignalStrengthsChanged[0]: "
                "SignalStrength:{mLte=CellSignalStrengthLte: "
                "rssi=-59 rsrp=-84 rsrq=-7 rssnr=28 cqi=2147483647 ta=2147483647 level=4,"
                "mNr=CellSignalStrengthNr:{ ssRsrp = 2147483647 ssRsrq = 2147483647 "
                "ssSinr = 2147483647 timingAdvance = 2147483647 },primary=CellSignalStrengthLte}\n",
                encoding="utf-8",
            )
            rows = analyze_sessions.signal_rows(session)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["epoch"], "1700000100.1")
            self.assertEqual(rows[0]["phone_id"], "0")
            self.assertEqual(rows[0]["lte_rsrp_dbm"], "-90")
            self.assertEqual(rows[1]["lte_rsrp_dbm"], "-84")


if __name__ == "__main__":
    unittest.main()
