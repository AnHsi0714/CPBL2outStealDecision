"""產生簡報用的 4 張圖（PNG），讀 `outputs/cpbl_decision_model_{year}_A_1-360.csv`。

- fig_p06_next_inning_order.png：兩種出局下一局的棒序示意
- fig_p16_threshold_by_slot_4seasons.png：四季逐棒次門檻折線圖
- fig_p17_retention_2025.png：範例年逐棒次保留效應（pp）
- fig_p18_threshold_by_slot_2025.png：範例年逐棒次門檻柱狀圖

門檻 = (V不跑 - V失敗) / (V成功 - V失敗)；保留效應 = 門檻 - 把 V失敗換成
V打者出局後的門檻，逐棒次取中位數。圖檔不進版控的資料夾見 `--output-dir`。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

NAVY = "#163A4F"
RED = "#D9453B"
GOLD = "#D4A02D"
CREAM = "#F7F0E6"
GRAY = "#BDC3C7"
SEASON_COLORS = {2023: "#2C7BB6", 2024: "#E08A1E", 2025: "#2E8B57", 2026: "#B94A5A"}

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Microsoft YaHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


def load(year: int, outputs: Path) -> list[dict[str, float | int]]:
    path = outputs / f"cpbl_decision_model_{year}_A_1-360.csv"
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            vs, vf, vn, vo = (float(row[k]) for k in ("ModelVSuccess", "ModelVFailure", "ModelVNoSteal", "ModelVIfBatterOut"))
            if vs == vf or vs == vo:
                continue
            threshold = (vn - vf) / (vs - vf) * 100
            no_retention = (vn - vo) / (vs - vo) * 100
            rows.append({"slot": int(row["HitterLineup"]), "threshold": threshold, "retention": threshold - no_retention})
    return rows


def median_by_slot(rows: list[dict[str, float | int]], key: str) -> list[float]:
    return [statistics.median(r[key] for r in rows if r["slot"] == slot) for slot in range(1, 10)]


def style_axes(ax) -> None:
    ax.set_facecolor(CREAM)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(NAVY)
    ax.spines["bottom"].set_color(NAVY)
    ax.tick_params(colors=NAVY)
    ax.yaxis.label.set_color(NAVY)


def save(fig, path: Path) -> None:
    fig.patch.set_facecolor(CREAM)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=CREAM)
    plt.close(fig)
    print(f"wrote {path}")


def fig_next_inning_order(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.6)
    ax.axis("off")
    scenarios = [
        ("盜壘刺（跑者出局）：下一局從第 8 棒開始", [8, 9, 1, 2], "要等 2 棒，才輪到棒頭", RED, 3.3),
        ("他自己打出局：下一局從第 9 棒開始", [9, 1, 2], "只等 1 棒", NAVY, 1.4),
    ]
    for title, order, note, color, y in scenarios:
        ax.text(0.2, y + 0.95, title, fontsize=14, fontweight="bold", color=color, va="center")
        for index, slot in enumerate(order):
            x = 0.4 + index * 2.2
            front = slot <= 5
            box = FancyBboxPatch((x, y - 0.35), 1.5, 0.9, boxstyle="round,pad=0.02", linewidth=1.5,
                                 edgecolor=NAVY, facecolor="#EE8A92" if front else GRAY)
            ax.add_patch(box)
            ax.text(x + 0.75, y + 0.1, f"第 {slot} 棒", ha="center", va="center", fontsize=14, color=NAVY, fontweight="bold")
            if index < len(order) - 1:
                ax.add_patch(FancyArrowPatch((x + 1.55, y + 0.1), (x + 2.15, y + 0.1), arrowstyle="-|>", mutation_scale=18, color=NAVY))
        ax.text(0.4 + len(order) * 2.2, y + 0.1, note, fontsize=13, color=color, va="center")
    ax.text(0.2, 0.25, "粉紅：前段棒次（1–5 棒）　灰：後段棒次（6–9 棒）", fontsize=11, color=NAVY)
    save(fig, path)


def fig_four_seasons(data: dict[int, list[float]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    style_axes(ax)
    slots = list(range(1, 10))
    for year, values in data.items():
        ax.plot(slots, values, marker="o", linewidth=2.6 if year == 2025 else 1.8, markersize=7,
                color=SEASON_COLORS[year], label=str(year), markerfacecolor="white", markeredgewidth=2)
    ax.set_xticks(slots)
    ax.set_xticklabels([f"第{s}棒" for s in slots])
    ax.set_ylabel("划算門檻（%）")
    ax.grid(axis="y", color="#E5DDD0")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.12), labelcolor=NAVY)
    save(fig, path)


def fig_bars(values: list[float], path: Path, ylabel: str, highlight: set[int], signed: bool, fmt: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    style_axes(ax)
    slots = list(range(1, 10))
    colors = [RED if slot in highlight else NAVY for slot in slots]
    if signed:
        colors = ["#2E8B57" if v < -0.5 else (RED if v > 0.5 else GRAY) for v in values]
    bars = ax.bar(slots, values, color=colors, width=0.62)
    for bar, value in zip(bars, values):
        offset = 0.3 if value >= 0 else -0.3
        ax.text(bar.get_x() + bar.get_width() / 2, value + offset, ("0" if signed and value == 0 else fmt.format(value)), ha="center",
                va="bottom" if value >= 0 else "top", fontsize=12, color=NAVY, fontweight="bold")
    ax.set_xticks(slots)
    ax.set_xticklabels([f"第{s}棒" for s in slots])
    ax.set_ylabel(ylabel)
    if signed:
        ax.axhline(0, color=NAVY, linewidth=1)
        ax.set_ylim(min(values) - 1.5, max(values) + 1.5)
    else:
        ax.set_ylim(min(values) - 5, max(values) + 2.5)
    ax.grid(axis="y", color="#E5DDD0")
    ax.set_axisbelow(True)
    save(fig, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="產生簡報用圖檔")
    parser.add_argument("--example-year", type=int, default=2025)
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--output-dir", default="簡報圖")
    args = parser.parse_args()

    outputs = Path(args.outputs_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    years = [int(y) for y in args.years.split(",")]
    rows_by_year = {year: load(year, outputs) for year in years}

    fig_next_inning_order(out_dir / "fig_p06_next_inning_order.png")
    fig_four_seasons({y: median_by_slot(r, "threshold") for y, r in rows_by_year.items()},
                     out_dir / "fig_p16_threshold_by_slot_4seasons.png")
    example = rows_by_year[args.example_year]
    retention = median_by_slot(example, "retention")
    fig_bars([round(v) for v in retention], out_dir / f"fig_p17_retention_{args.example_year}.png",
             "保留效應：門檻上升或下降（百分點）", set(), True, "{:+.0f}")
    threshold = median_by_slot(example, "threshold")
    fig_bars(threshold, out_dir / f"fig_p18_threshold_by_slot_{args.example_year}.png",
             "划算門檻（%）", {4}, False, "{:.1f}")


if __name__ == "__main__":
    main()
