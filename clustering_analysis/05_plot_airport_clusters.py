"""Create report figures from the airport cluster assignments and profiles."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator, PercentFormatter
import pandas as pd


OUTPUTS = Path(__file__).resolve().parent / "outputs"
COLORS = ["#286A94", "#AB5F1D", "#87517D"]
MARKERS = ["o", "^", "s"]
INK = "#243344"
MUTED = "#526174"


def set_style() -> None:
    preferred = [
        "Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "SimSun", "PingFang SC",
        "WenQuanYi Zen Hei", "Noto Sans CJK JP",
    ]
    installed = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in preferred if name in installed), None)
    if font is None:
        raise RuntimeError("No Chinese font found. Install Microsoft YaHei or Noto Sans CJK SC.")
    plt.rcParams.update({
        "font.family": font,
        "font.size": 11,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.spines.bottom": False,
        "axes.axisbelow": True,
    })


def plot_profiles(profiles: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.1))
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.19, top=0.79, wspace=0.37, hspace=0.68)
    fig.text(0.08, 0.94, "三类机场的延误和天气特征有什么差别？", fontsize=19, weight="bold")
    fig.text(0.08, 0.875, f"2024 年 · {profiles['airports'].sum():,} 个出发机场 · K-means 三类方案", color=MUTED)
    labels = [f"第 {c} 类" for c in profiles["cluster"]]
    metrics = [
        ("mean_delay_rate", "到达延误率", "%"),
        ("mean_median_delay_min", "延误分钟中位数", "分钟"),
        ("mean_high_wind_rate", "强风比例（≥20 节）", "%"),
        ("mean_low_visibility_rate", "低能见度比例（<5 公里）", "%"),
    ]
    for ax, (column, title, unit) in zip(axes.flat, metrics):
        values = profiles[column] * (100 if unit == "%" else 1)
        bars = ax.barh(labels, values, height=0.56, color=COLORS)
        labels_text = [f"{value:.2f}%" if unit == "%" else f"{value:.2f} 分钟" for value in values]
        ax.bar_label(bars, labels=labels_text, padding=4, fontsize=10)
        ax.set_title(title, loc="left", weight="bold", pad=9)
        ax.set_xlim(0, values.max() * (1.38 if unit == "分钟" else 1.30))
        ax.invert_yaxis()
        ax.grid(axis="x", color="#E6EBEF")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, integer=unit == "%"))
        ax.tick_params(length=0)
        if unit == "%":
            ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    fig.text(0.08, 0.094, "各项先按机场计算，再对同类机场等权取平均。延误分钟中位数仅在已延误航班中计算。", fontsize=9, color=MUTED)
    fig.text(0.08, 0.055, "数据来源  BTS 航班与 NOAA 天气融合数据（2024 年）。", fontsize=9, color=MUTED)
    fig.savefig(path, dpi=240, facecolor="white")
    plt.close(fig)


def plot_airports(airports: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.20, top=0.76)
    fig.text(0.08, 0.94, "强风比例与延误率能区分三类机场吗？", fontsize=19, weight="bold")
    fig.text(0.08, 0.879, f"2024 年 · {len(airports):,} 个出发机场 · 每个点代表一个机场", color=MUTED)
    for (cluster, group), color, marker in zip(airports.groupby("cluster"), COLORS, MARKERS):
        ax.scatter(group["high_wind_rate"], group["delay_rate"], s=34, c=color, marker=marker,
                   alpha=0.72, edgecolor="white", linewidth=0.35, label=f"第 {cluster} 类（{len(group)} 个）")
    highest_wind = airports.loc[airports["high_wind_rate"].idxmax()]
    ax.annotate(str(highest_wind["origin"]), (highest_wind["high_wind_rate"], highest_wind["delay_rate"]),
                xytext=(-6, 9), textcoords="offset points", ha="right", color=MUTED, fontsize=10)
    ax.set_xlabel("强风比例（风速 ≥20 节）", labelpad=8)
    ax.set_ylabel("到达延误率（延误 ≥15 分钟）", labelpad=8)
    ax.set_xlim(0, airports["high_wind_rate"].max() * 1.09)
    ax.set_ylim(0, airports["delay_rate"].max() * 1.09)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(color="#E6EBEF")
    ax.tick_params(length=0, pad=7)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.015), ncol=3, frameon=False, borderaxespad=0, fontsize=10)
    fig.text(0.08, 0.085, "图中展示两个指标。机场分组还使用延误分钟中位数与低能见度比例。", fontsize=9, color=MUTED)
    fig.text(0.08, 0.050, "数据来源  BTS 航班与 NOAA 天气融合数据（2024 年）。", fontsize=9, color=MUTED)
    fig.savefig(path, dpi=240, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=Path, default=OUTPUTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS / "figures")
    args = parser.parse_args()

    profiles = pd.read_csv(args.tables / "airport_cluster_profiles.csv").sort_values("cluster")
    airports = pd.read_csv(args.tables / "airport_cluster_assignments.csv")
    counts = airports.groupby("cluster").size()
    if profiles["cluster"].tolist() != [1, 2, 3] or not counts.equals(profiles.set_index("cluster")["airports"]):
        raise ValueError("Expected three groups with the same airport counts in both input tables.")

    set_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = args.output_dir / "01_cluster_profiles.png"
    scatter_path = args.output_dir / "02_airport_cluster_scatter.png"
    plot_profiles(profiles, profile_path)
    plot_airports(airports, scatter_path)
    print(f"Saved: {profile_path.resolve()}")
    print(f"Saved: {scatter_path.resolve()}")


if __name__ == "__main__":
    main()
