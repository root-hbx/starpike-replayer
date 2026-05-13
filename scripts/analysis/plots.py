from __future__ import annotations

import csv
from pathlib import Path

from .activity import PROXY_CATEGORIES


def plot_outputs(out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        (out_dir / "PLOTS_SKIPPED.txt").write_text("matplotlib is not installed\n", encoding="utf-8")
        return

    activity = out_dir / "activity_proxy_rate_1s.csv"
    if activity.exists():
        rows = list(csv.DictReader(activity.open(encoding="utf-8", newline="")))
        if rows:
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                xs = [int(row["second"]) for row in subset]
                ys = [[float(row[cat]) for row in subset] for cat in PROXY_CATEGORIES]
                plt.figure(figsize=(8, 3))
                plt.stackplot(xs, ys, labels=PROXY_CATEGORIES)
                plt.xlabel("Time (second)")
                plt.ylabel("Events or packets/s")
                plt.title(f"AP-visible cellular activity proxy rate: {session}")
                plt.legend(loc="upper right", fontsize=7)
                plt.tight_layout()
                plt.savefig(out_dir / f"fig_activity_proxy_rate_stacked_{session}.pdf")
                plt.close()

            averages = {cat: 0.0 for cat in PROXY_CATEGORIES}
            for cat in PROXY_CATEGORIES:
                values = [float(row[cat]) for row in rows]
                averages[cat] = sum(values) / len(values)
            plt.figure(figsize=(7, 3))
            plt.bar(list(averages), [averages[cat] for cat in averages])
            values = list(averages.values())
            if any(value == 0 for value in values):
                plt.yscale("symlog", linthresh=0.1)
            else:
                plt.yscale("log")
            plt.ylabel("Events or packets/s")
            plt.xticks(rotation=25, ha="right")
            plt.tight_layout()
            plt.savefig(out_dir / "fig_activity_proxy_rate_bar.pdf")
            plt.close()

    cpu = out_dir / "ap_cpu_timeseries.csv"
    if cpu.exists():
        rows = [row for row in csv.DictReader(cpu.open(encoding="utf-8", newline="")) if row["cpu_label"] == "cpu"]
        if rows:
            plt.figure(figsize=(8, 3))
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                origin = float(subset[0]["epoch"])
                xs = [float(row["epoch"]) - origin for row in subset]
                ys = [float(row["busy_pct"]) for row in subset]
                plt.plot(xs, ys, label=session)
            plt.xlabel("Time (second)")
            plt.ylabel("AP CPU busy (%)")
            plt.legend(fontsize=7)
            plt.tight_layout()
            plt.savefig(out_dir / "fig_ap_cpu_delta.pdf")
            plt.close()

    iperf = out_dir / "iperf_timeseries.csv"
    if iperf.exists():
        rows = list(csv.DictReader(iperf.open(encoding="utf-8", newline="")))
        if rows:
            plt.figure(figsize=(8, 3))
            for session in sorted({row["session"] for row in rows}):
                subset = [row for row in rows if row["session"] == session]
                xs = [(float(row["start_sec"]) + float(row["end_sec"])) / 2.0 for row in subset]
                ys = [float(row["throughput_mbps"]) for row in subset]
                plt.plot(xs, ys, marker="o", linewidth=1.2, markersize=2.5, label=session)
            plt.xlabel("Time (second)")
            plt.ylabel("Throughput (Mbps)")
            plt.legend(fontsize=7)
            plt.tight_layout()
            plt.savefig(out_dir / "fig_iperf_throughput.pdf")
            plt.close()
