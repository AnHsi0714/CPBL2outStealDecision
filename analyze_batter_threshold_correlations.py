"""打者層級相關係數：門檻中位數 vs 六種打擊率（HR／長打／保送／單打／打擊率／出局）。

跟 `compare_groups.py` 的 `batter_type_correlations`（ISO_proxy 對 BBpct_proxy 等
四個複合指標互比）是不同問題：這裡回答的是「決定門檻的到底是打者的『能力高低』還是
『打擊型態』」，所以要看門檻本身跟六個原始事件機率（而非複合指標）的相關係數。

「這位打者的門檻」定義為該打者所有決策點 `BreakEvenSuccessRate` 的中位數（跟其餘
逐棒次／分組比較用同一個統計口徑），只納入 `cpbl_batter_profiles_*.csv` 裡
`PA >= --min-pa`（預設 100，跟 `analyze_batter_types.py` 一致）的合格打者。

依賴 `model_batter_decisions.py` 的 `cpbl_decision_model_*.csv`（門檻）與
`cpbl_batter_profiles_*.csv`（P_HR/P_XBH/P_BB_HBP/P_1B/P_HIT/P_OUT），不需要
重跑模擬、不需要原始 JSON 快取。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median
from typing import Any


def as_float_or_none(value: str) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def pearson_correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = (
        sum((x - left_mean) ** 2 for x in left) ** 0.5
        * sum((y - right_mean) ** 2 for y in right) ** 0.5
    )
    return numerator / denominator if denominator else None


def batter_thresholds(decision_rows: list[dict[str, Any]]) -> dict[str, float]:
    by_batter: dict[str, list[float]] = {}
    for row in decision_rows:
        value = as_float_or_none(row["BreakEvenSuccessRate"])
        if value is None or not (0 < value <= 1):
            continue
        by_batter.setdefault(row["HitterAcnt"], []).append(value)
    return {hitter: median(values) for hitter, values in by_batter.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--decision-csv", type=Path, default=None)
    parser.add_argument("--profiles-csv", type=Path, default=None)
    parser.add_argument("--min-pa", type=float, default=100.0)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


METRICS = [
    ("P_HR", "全壘打率"),
    ("P_XBH", "長打率（2B+3B）"),
    ("P_BB_HBP", "保送率"),
    ("P_1B", "單打率"),
    ("P_HIT", "打擊率"),
    ("P_OUT", "出局率"),
]


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    decision_csv = args.decision_csv or Path("outputs") / f"cpbl_decision_model_{tag}.csv"
    profiles_csv = args.profiles_csv or Path("outputs") / f"cpbl_batter_profiles_{tag}.csv"

    thresholds = batter_thresholds(load_rows(decision_csv))
    profiles = load_rows(profiles_csv)

    qualified = [
        row
        for row in profiles
        if as_float_or_none(row["PA"]) is not None
        and as_float_or_none(row["PA"]) >= args.min_pa
        and row["HitterAcnt"] in thresholds
    ]

    threshold_values = [thresholds[row["HitterAcnt"]] for row in qualified]

    output_rows = []
    print(f"\n{tag}：合格打者（PA >= {args.min_pa}）{len(qualified)} 位，門檻中位數 {median(threshold_values)*100:.1f}%\n")
    print(f"{'指標':<16} | {'相關係數':>8}")
    for column, label in METRICS:
        metric_values = [as_float_or_none(row[column]) for row in qualified]
        r = pearson_correlation(threshold_values, metric_values)
        output_rows.append({"Metric": column, "Label": label, "N": len(qualified), "PearsonR": r})
        r_str = f"{r:+.3f}" if r is not None else "NA"
        print(f"{label:<16} | {r_str:>8}")

    output_path = args.output_dir / f"cpbl_batter_threshold_correlations_{tag}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
