"""敏感度檢查：排除大分差樣本後，門檻中位數會不會顯著改變。

承接 `analyze_score_diff_steal_rate.py` 的發現（盜壘嘗試率在分差 ±5 以後明顯
下滑）：這裡把同一批決策依決策當下分差分桶，各桶分別排除後重算
`BreakEvenSuccessRate` 中位數，跟全樣本中位數比較——如果排除後中位數變化很
小，代表大分差樣本對主結論沒有實質影響，文字揭露即可，不需要真的把這些樣本
從主管線剔除。

依賴 `analyze_score_diff_steal_rate.py` 先跑過同一個 tag（讀它輸出的
`cpbl_score_diff_steal_rate_*.csv` 取得每筆決策的分差），以及 step 2
（`model_batter_decisions.py`）產生的 `cpbl_decision_model_*.csv`。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median
from typing import Any

from find_2out_first_base import as_int


def load_thresholds(path: Path) -> dict[tuple[int, int], float]:
    result: dict[tuple[int, int], float] = {}
    with path.open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            try:
                value = float(row["BreakEvenSuccessRate"])
            except (TypeError, ValueError):
                continue
            if not (0 <= value <= 1):
                continue
            key = (as_int(row.get("GameSno")), as_int(row.get("StateRowIndex")))
            result[key] = value
    return result


def load_score_diffs(path: Path) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    with path.open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            key = (as_int(row.get("GameSno")), as_int(row.get("StateRowIndex")))
            result[key] = as_int(row.get("ScoreDiffAtState"))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--caps", type=int, nargs="+", default=[3, 4, 5, 6, 8])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    thresholds = load_thresholds(Path("outputs") / f"cpbl_decision_model_{tag}.csv")
    diffs = load_score_diffs(Path("outputs") / f"cpbl_score_diff_steal_rate_{tag}.csv")

    joined: list[tuple[Any, int]] = []
    missing = 0
    for key, value in thresholds.items():
        if key not in diffs:
            missing += 1
            continue
        joined.append((value, diffs[key]))

    if missing:
        print(f"警告：{missing} 筆門檻找不到對應分差，已略過")

    full_values = [value for value, _ in joined]
    full_median = median(full_values)
    print(f"\n{tag}：全樣本 n={len(full_values)}，門檻中位數={full_median:.3%}\n")

    print(f"{'排除範圍':>14} | {'剩餘n':>6} | {'中位數':>8} | {'差異(pp)':>9}")
    print(f"{'（不排除）':>14} | {len(full_values):>6} | {full_median:>7.3%} | {'0.000':>9}")
    for cap in sorted(args.caps):
        subset = [value for value, diff in joined if abs(diff) < cap]
        excluded = len(full_values) - len(subset)
        if not subset:
            continue
        subset_median = median(subset)
        delta_pp = (subset_median - full_median) * 100
        print(
            f"排除|分差|>={cap:>2}   | {len(subset):>6} | {subset_median:>7.3%} | {delta_pp:>+8.3f}"
            f"  (排除 {excluded} 筆)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
