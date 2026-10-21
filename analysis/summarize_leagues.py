"""把 MLB／KBO 各球季既有輸出（outputs/<聯盟>_*）彙整成 markdown 表格，供寫進 分析發現.md。

只讀既有輸出、不重算任何東西；找不到的檔案對應欄位留空。用法：
    python analysis/summarize_leagues.py            # 印出 MLB 與 KBO 兩份
    python analysis/summarize_leagues.py mlb        # 只印 MLB
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import csv
import json
import sys
from pathlib import Path
from typing import Any

OUT = Path("outputs")
TAGS = {
    "mlb": [f"{y}-03-15_{y}-10-10" for y in (2023, 2024, 2025, 2026)],
    "kbo": ["2023", "2024", "2025", "2026"],
}
COMPARISONS = {
    "lineup_front_vs_back": "前段(1-5) vs 後段(6-9)",
    "power_high_vs_low_ISO": "高 ISO vs 低 ISO",
    "patience_high_vs_low_BB": "高 BB% vs 低 BB%",
    "obp_high_vs_low_OBP": "高 OBP vs 低 OBP",
    "contact_high_vs_low_1B": "高單打率 vs 低單打率",
    "tto_high_vs_low_TTO": "高 TTO vs 低 TTO",
}
GROUP_KEYS = {
    "lineup_front_vs_back": ("front_1_5", "back_6_9"),
    "power_high_vs_low_ISO": ("high_ISO", "low_ISO"),
    "patience_high_vs_low_BB": ("high_BB", "low_BB"),
    "obp_high_vs_low_OBP": ("high_OBP", "low_OBP"),
    "contact_high_vs_low_1B": ("high_1B", "low_1B"),
    "tto_high_vs_low_TTO": ("high_TTO", "low_TTO"),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else None


def pct(value: float | None, digits: int = 1) -> str:
    return "" if value is None else f"{value * 100:.{digits}f}%"


def season_label(league: str, tag: str) -> str:
    return tag[:4]


def summarize(league: str) -> str:
    lines: list[str] = []
    tags = TAGS[league]
    lines.append(f"### {league.upper()} 四季總覽\n")
    lines.append("| 季 | 場數 | 決策樣本 | 盜壘成功／失敗 | 保留效應不一致 | RE 門檻中位數 | RE24 引擎 r | WPA 門檻中位數 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for tag in tags:
        find = load_json(OUT / f"{league}_2out_first_base_{tag}_summary.json") or {}
        model = load_json(OUT / f"{league}_decision_model_{tag}_summary.json") or {}
        re24 = load_json(OUT / f"{league}_re24_validation_{tag}_summary.json") or {}
        wpa = load_json(OUT / f"{league}_wpa_decision_model_{tag}_summary.json") or {}
        counts = find.get("outcome_counts", {})
        lines.append(
            f"| {season_label(league, tag)} | {find.get('games_processed', '')} | {find.get('decision_samples', '')} | "
            f"{counts.get('steal_success', '')}／{counts.get('steal_failure', '')} | "
            f"{find.get('failed_steal_retention_mismatches', '')} | {pct(model.get('median_break_even_rate_in_0_1'))} | "
            f"{re24.get('correlation', '')} | {pct(wpa.get('overall_median_threshold_wpa'))} |"
        )

    lines.append("\n### 逐棒次門檻中位數（RE 版）\n")
    lines.append("| 季 | " + " | ".join(str(s) for s in range(1, 10)) + " |")
    lines.append("|---|" + "---|" * 9)
    for tag in tags:
        model = load_json(OUT / f"{league}_decision_model_{tag}_summary.json") or {}
        by_slot = model.get("by_hitter_lineup", {})
        lines.append(f"| {season_label(league, tag)} | " + " | ".join(
            pct(by_slot.get(str(s), {}).get("median_break_even_rate_in_0_1")) for s in range(1, 10)) + " |")

    lines.append("\n### 保留效應貢獻（pp，逐棒次中位數）\n")
    lines.append("| 季 | " + " | ".join(str(s) for s in range(1, 10)) + " |")
    lines.append("|---|" + "---|" * 9)
    for tag in tags:
        path = OUT / f"{league}_retention_contribution_{tag}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as file:
            by_slot = {r["LineupSlot"]: float(r["MedianRetentionPP"]) for r in csv.DictReader(file)}
        lines.append(f"| {season_label(league, tag)} | " + " | ".join(
            f"{by_slot[str(s)]:+.2f}" if str(s) in by_slot else "" for s in range(1, 10)) + " |")

    lines.append("\n### 棒次與打者類型分組比較（門檻中位數，Mann-Whitney p）\n")
    lines.append("| 比較 | " + " | ".join(season_label(league, t) for t in tags) + " |")
    lines.append("|---|" + "---|" * len(tags))
    comparisons = {t: load_json(OUT / f"{league}_group_comparison_{t}.json") for t in tags}
    for key, label in COMPARISONS.items():
        cells = []
        for tag in tags:
            data = comparisons[tag]
            item = next((c for c in (data or {}).get("comparisons", []) if c["comparison"] == key), None)
            if item is None:
                cells.append("")
                continue
            first, second = GROUP_KEYS[key]
            p = item["p_value"]
            cells.append(f"{pct(item[first]['median'])} vs {pct(item[second]['median'])}（p={'<0.001' if p < 0.001 else f'{p:.3f}'}）")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    lines.append("\n### 各隊決策品質 與 跑者名單\n")
    lines.append("| 季 | 整體實際成功率 | 整體門檻 | 判定 | 跑對隊數 | 跑錯隊數 | 無法判定隊數 | 跑者：任一棒次都可跑／視棒次／都不建議／樣本不足 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for tag in tags:
        decisions = load_json(OUT / f"{league}_team_decisions_{tag}.json")
        runners = load_json(OUT / f"{league}_runner_steal_rates_{tag}.json")
        if not decisions:
            continue
        league_row = decisions["league"]
        verdicts = [t["verdict"] for t in decisions["teams"]]
        tiers = (runners or {}).get("tierCounts", {})
        lines.append(
            f"| {season_label(league, tag)} | {pct(league_row['actualSuccessRate'])} | {pct(league_row['thresholdMedian'])} | "
            f"{league_row['verdict']} | {verdicts.count('跑對')} | {verdicts.count('跑錯')} | "
            f"{sum(v.startswith('無法判定') for v in verdicts)} | "
            f"{tiers.get('任一棒次都可跑', 0)}／{tiers.get('視下一棒棒次而定', 0)}／"
            f"{tiers.get('任一棒次都不建議跑', 0)}／{tiers.get('樣本不足', 0)} |"
        )

    lines.append("\n### WPA 版逐局門檻中位數（WPA / RE，pp 差）\n")
    lines.append("| 季 | " + " | ".join(f"第{i}局" for i in range(1, 9)) + " |")
    lines.append("|---|" + "---|" * 8)
    for tag in tags:
        wpa = load_json(OUT / f"{league}_wpa_decision_model_{tag}_summary.json")
        if not wpa:
            continue
        cells = []
        for inning in range(1, 9):
            item = wpa["by_inning"].get(str(inning))
            cells.append("" if not item else f"{pct(item['median_threshold_wpa'], 0)} / {pct(item['median_threshold_re'], 0)}（{item['median_diff_pp']:+.0f}）")
        lines.append(f"| {season_label(league, tag)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    leagues = sys.argv[1:] or ["mlb", "kbo"]
    for league in leagues:
        print(summarize(league))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
