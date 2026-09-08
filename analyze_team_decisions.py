"""層次四｜六隊決策品質評估：各隊兩出局、一壘有人的盜壘實際行為，跟該隊自己的損益兩平門檻比對。

判定邏輯（計畫書 3.1 節「層次四」的操作化，見 兩出局一壘有人盜壘決策_專案計畫書.md）：
- 該隊實際成功率 = 該隊兩出局、一壘有人的盜壘嘗試中，成功的比例
- 該隊門檻 = 該隊所有兩出局、一壘有人決策機會（不論當時有沒有跑）的 BreakEvenSuccessRate 中位數
- 用二項檢定（binomtest）檢驗「實際成功次數」跟「假設真實成功率＝該隊門檻」是否顯著不同，
  同時算 Wilson 95% 信賴區間：只有 p < 0.05 才判「跑對」或「跑錯」，否則標記「無法判定（不顯著）」。
  2025 年各隊嘗試僅 27–49 次（拆前段/後段棒次後更只剩個位數到二十幾次），點估計的成功率離門檻沒差
  幾個百分點就可能只是抽樣雜訊，若只比大小、不做顯著性檢定，會誤把雜訊講成「跑錯」，這點顯著性檢定
  能挑出來（六隊裡最後只有一隊在統計上顯著）。
- 該隊嘗試次數為 0 時無法判定，直接標記「樣本不足（無嘗試）」，不套用二項檢定

只做「跑對／跑錯」，不做「該跑不跑」——後者需要額外定義一個「嘗試率」基準，而 2025 年各隊兩出局、一壘
有人的盜壘嘗試次數本來就不多，計畫書 3.3 節已明講這類切層後樣本不足、須誠實揭露，留待跨年度資料補齊後再做。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent
SIGNIFICANCE_LEVEL = 0.05


def as_float_or_none(value: str) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def valid_threshold(row: dict[str, Any]) -> float | None:
    value = as_float_or_none(row["BreakEvenSuccessRate"])
    if value is None or not (0 < value <= 1):
        return None
    return value


def team_stats(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = [row["_threshold"] for row in rows if row["_threshold"] is not None]
    successes = sum(1 for row in rows if row["Outcome"] == "steal_success")
    failures = sum(1 for row in rows if row["Outcome"] == "steal_failure")
    attempts = successes + failures
    actual_success_rate = successes / attempts if attempts else None
    threshold_median = median(thresholds) if thresholds else None

    verdict = "樣本不足（無嘗試）"
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    if attempts and threshold_median is not None:
        test = binomtest(successes, attempts, threshold_median, alternative="two-sided")
        p_value = test.pvalue
        ci = test.proportion_ci(confidence_level=0.95, method="wilson")
        ci_low, ci_high = ci.low, ci.high
        if p_value < SIGNIFICANCE_LEVEL:
            verdict = "跑對" if actual_success_rate >= threshold_median else "跑錯"
        else:
            verdict = "無法判定（不顯著）"

    return {
        "team": label,
        "opportunities": len(rows),
        "attempts": attempts,
        "successes": successes,
        "failures": failures,
        "actualSuccessRate": actual_success_rate,
        "thresholdMedian": threshold_median,
        "thresholdSamples": len(thresholds),
        "pValue": p_value,
        "ci95Low": ci_low,
        "ci95High": ci_high,
        "verdict": verdict,
    }


def lineup_half_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def in_range(row: dict[str, Any], low: int, high: int) -> bool:
        return row["HitterLineup"].isdigit() and low <= int(row["HitterLineup"]) <= high

    front = [row for row in rows if in_range(row, 1, 5)]
    back = [row for row in rows if in_range(row, 6, 9)]
    return {
        "front_1_5": team_stats("front_1_5", front),
        "back_6_9": team_stats("back_6_9", back),
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        row["_threshold"] = valid_threshold(row)

    teams = sorted({row["BattingTeam"] for row in rows})
    rows_by_team = {team: [row for row in rows if row["BattingTeam"] == team] for team in teams}

    league_thresholds = [row["_threshold"] for row in rows if row["_threshold"] is not None]
    league = team_stats("league", rows)
    league["thresholdMedian"] = median(league_thresholds) if league_thresholds else None

    return {
        "opportunities": len(rows),
        "league": league,
        "teams": [team_stats(team, rows_by_team[team]) for team in teams],
        "teamsByLineupHalf": {team: lineup_half_stats(rows_by_team[team]) for team in teams},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_csv = args.input or ROOT / "outputs" / f"cpbl_decision_model_{tag}.csv"
    output_json = args.output or ROOT / "outputs" / f"cpbl_team_decisions_{tag}.json"

    rows = load_rows(input_csv)
    summary = build_summary(rows)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("六隊決策品質評估（二項檢定：實際成功次數 vs 該隊門檻，p<0.05 才判跑對/跑錯）")
    for team in summary["teams"]:
        rate = f"{team['actualSuccessRate']:.1%}" if team["actualSuccessRate"] is not None else "無嘗試"
        threshold = f"{team['thresholdMedian']:.1%}" if team["thresholdMedian"] is not None else "無資料"
        p_text = f"p={team['pValue']:.3f}" if team["pValue"] is not None else "p=無"
        print(
            f"  {team['team']}: 嘗試 {team['attempts']}（成功 {team['successes']}／失敗 {team['failures']}）"
            f"，實際成功率 {rate}，該隊門檻 {threshold}，{p_text} → {team['verdict']}"
        )

    print(f"\n輸出：{output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
