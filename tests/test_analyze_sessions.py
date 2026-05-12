import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import analyze_sessions


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
                "1700000100.100000  1  1 I RILJ: setupDataCall\n"
                "1700000100.200000  1  1 I Phone: ServiceState changed\n"
                "1700000101.100000  1  1 I Phone: SignalStrength rsrp=-95\n",
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


if __name__ == "__main__":
    unittest.main()
