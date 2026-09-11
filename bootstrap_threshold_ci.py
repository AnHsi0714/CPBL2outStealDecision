"""損益兩平門檻中位數的 95% bootstrap 信賴區間（整體／逐棒次／打者類型分組比較）。

計畫書第 7–8 週待辦「對門檻估計值加上 bootstrap 信賴區間」。同時捕捉兩種不確定性
來源，一次 bootstrap 迭代做兩件事：

1. **決策樣本的抽樣誤差**——對決策列做 case resampling（取後放回）。
2. **蒙地卡羅模擬雜訊**——`model_batter_decisions.py` 的 `branch_stats` 其實已經
   算出每筆決策 `ModelVSuccess`/`ModelVFailure`/`ModelVNoSteal` 各自的標準誤
   （`*SE` 欄位，模擬次數不夠多時這個值較大），只是原本沒用上。這裡對每個被抽中
   的決策，用常態分布依 SE 對三個 V 值加雜訊，模擬「如果那天模擬次數不同，這筆
   決策的門檻會抖動多少」，再算門檻——比只做 case resampling 更完整。

讀 `cpbl_decision_with_types_*.csv`（需要棒次與打者類型分組欄位），不需要重跑
模擬、不需要原始 JSON 快取。
"""

from __future__ import annotations

import argparse
import csv
import json
import random
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


def threshold_value(v_success: float, v_failure: float, v_no_steal: float) -> float | None:
    denominator = v_success - v_failure
    if denominator <= 0:
        return None
    return (v_no_steal - v_failure) / denominator


class RowValues:
    __slots__ = ("v_success", "v_success_se", "v_failure", "v_failure_se", "v_no_steal", "v_no_steal_se")

    def __init__(self, row: dict[str, Any]) -> None:
        self.v_success = float(row["ModelVSuccess"])
        self.v_success_se = float(row["ModelVSuccessSE"] or 0.0)
        self.v_failure = float(row["ModelVFailure"])
        self.v_failure_se = float(row["ModelVFailureSE"] or 0.0)
        self.v_no_steal = float(row["ModelVNoSteal"])
        self.v_no_steal_se = float(row["ModelVNoStealSE"] or 0.0)


def extract_values(rows: list[dict[str, Any]]) -> list[RowValues]:
    result = []
    for row in rows:
        value = as_float_or_none(row.get("BreakEvenSuccessRate"))
        if value is None or not (0 < value <= 1):
            continue
        try:
            result.append(RowValues(row))
        except (TypeError, ValueError):
            continue
    return result


def bootstrap_median_ci(
    values: list[RowValues], rng: random.Random, iterations: int
) -> dict[str, Any] | None:
    """回傳原始中位數與 bootstrap 2.5/50/97.5 百分位。"""
    if len(values) < 5:
        return None
    n = len(values)
    point_thresholds = []
    for item in values:
        t = threshold_value(item.v_success, item.v_failure, item.v_no_steal)
        if t is not None and 0 < t <= 1:
            point_thresholds.append(t)
    if not point_thresholds:
        return None
    point_median = median(point_thresholds)

    boot_medians: list[float] = []
    indices = range(n)
    for _ in range(iterations):
        sample_thresholds = []
        for _ in range(n):
            item = values[rng.choice(indices)]
            v_success = rng.gauss(item.v_success, item.v_success_se) if item.v_success_se > 0 else item.v_success
            v_failure = rng.gauss(item.v_failure, item.v_failure_se) if item.v_failure_se > 0 else item.v_failure
            v_no_steal = rng.gauss(item.v_no_steal, item.v_no_steal_se) if item.v_no_steal_se > 0 else item.v_no_steal
            t = threshold_value(v_success, v_failure, v_no_steal)
            if t is not None and 0 < t <= 1:
                sample_thresholds.append(t)
        if sample_thresholds:
            boot_medians.append(median(sample_thresholds))

    if len(boot_medians) < iterations // 2:
        return None
    boot_medians.sort()

    def percentile(p: float) -> float:
        index = min(len(boot_medians) - 1, max(0, round(p * (len(boot_medians) - 1))))
        return boot_medians[index]

    return {
        "n": len(point_thresholds),
        "point_median": point_median,
        "ci_low": percentile(0.025),
        "ci_high": percentile(0.975),
        "bootstrap_replicates": len(boot_medians),
    }


def bootstrap_diff_ci(
    values_a: list[RowValues], values_b: list[RowValues], rng: random.Random, iterations: int
) -> dict[str, Any] | None:
    """兩組中位數差（A－B）的 bootstrap 信賴區間，對應 compare_groups.py 的 high/low 分組比較。"""
    stats_a = bootstrap_median_ci(values_a, rng, iterations)
    stats_b = bootstrap_median_ci(values_b, rng, iterations)
    if stats_a is None or stats_b is None:
        return None
    n_a, n_b = len(values_a), len(values_b)
    diffs: list[float] = []
    for _ in range(iterations):
        sample_a = [threshold_value(*_perturb(values_a[rng.choice(range(n_a))], rng)) for _ in range(n_a)]
        sample_b = [threshold_value(*_perturb(values_b[rng.choice(range(n_b))], rng)) for _ in range(n_b)]
        sample_a = [v for v in sample_a if v is not None and 0 < v <= 1]
        sample_b = [v for v in sample_b if v is not None and 0 < v <= 1]
        if sample_a and sample_b:
            diffs.append(median(sample_a) - median(sample_b))
    if len(diffs) < iterations // 2:
        return None
    diffs.sort()

    def percentile(p: float) -> float:
        index = min(len(diffs) - 1, max(0, round(p * (len(diffs) - 1))))
        return diffs[index]

    return {
        "point_diff": stats_a["point_median"] - stats_b["point_median"],
        "ci_low": percentile(0.025),
        "ci_high": percentile(0.975),
        "excludes_zero": percentile(0.025) > 0 or percentile(0.975) < 0,
    }


def _perturb(item: RowValues, rng: random.Random) -> tuple[float, float, float]:
    v_success = rng.gauss(item.v_success, item.v_success_se) if item.v_success_se > 0 else item.v_success
    v_failure = rng.gauss(item.v_failure, item.v_failure_se) if item.v_failure_se > 0 else item.v_failure
    v_no_steal = rng.gauss(item.v_no_steal, item.v_no_steal_se) if item.v_no_steal_se > 0 else item.v_no_steal
    return v_success, v_failure, v_no_steal


GROUP_COLUMNS = [
    ("PowerGroup", "high_ISO", "low_ISO", "power_high_vs_low_ISO"),
    ("PatienceGroup", "high_BB", "low_BB", "patience_high_vs_low_BB"),
    ("OBPGroup", "high_OBP", "low_OBP", "obp_high_vs_low_OBP"),
    ("ContactGroup", "high_1B", "low_1B", "contact_high_vs_low_1B"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--input", type=Path, default=None, help="預設讀 step 4 的 cpbl_decision_with_types_*.csv")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_csv = args.input or Path("outputs") / f"cpbl_decision_with_types_{tag}.csv"
    rng = random.Random(args.seed)

    rows = load_rows(input_csv)
    all_values = extract_values(rows)

    overall = bootstrap_median_ci(all_values, rng, args.iterations)
    print(f"\n{tag}：{overall['n'] if overall else 0}/{len(rows)} 筆決策計入，bootstrap {args.iterations} 次")
    if overall:
        print(
            f"整體門檻中位數：{overall['point_median']*100:.1f}%"
            f"（95% CI {overall['ci_low']*100:.1f}%–{overall['ci_high']*100:.1f}%）"
        )

    lineup_results = []
    print(f"\n{'棒次':>4} | {'N':>5} | {'中位數':>7} | {'95% CI':>15}")
    for slot in range(1, 10):
        slot_values = extract_values([row for row in rows if row.get("HitterLineup") == str(slot)])
        stats = bootstrap_median_ci(slot_values, rng, args.iterations)
        lineup_results.append({"slot": slot, **(stats or {})})
        if stats:
            print(
                f"{slot:>4} | {stats['n']:>5} | {stats['point_median']*100:>6.1f}% |"
                f" [{stats['ci_low']*100:>5.1f}%, {stats['ci_high']*100:>5.1f}%]"
            )
        else:
            print(f"{slot:>4} | {'NA':>5} | {'NA':>7} | {'NA':>15}")

    qualified_rows = [row for row in rows if row.get("BatterTypeQualified") == "True"]
    group_results = []
    print(f"\n{'分組比較':<28} | {'高組中位數':>9} | {'低組中位數':>9} | {'差(pp) 95% CI':>22}")
    for column, high_label, low_label, comparison_name in GROUP_COLUMNS:
        high_values = extract_values([row for row in qualified_rows if row.get(column) == high_label])
        low_values = extract_values([row for row in qualified_rows if row.get(column) == low_label])
        diff_stats = bootstrap_diff_ci(high_values, low_values, rng, args.iterations)
        high_stats = bootstrap_median_ci(high_values, rng, args.iterations)
        low_stats = bootstrap_median_ci(low_values, rng, args.iterations)
        group_results.append(
            {
                "comparison": comparison_name,
                "high": high_stats,
                "low": low_stats,
                "diff": diff_stats,
            }
        )
        if diff_stats and high_stats and low_stats:
            print(
                f"{comparison_name:<28} | {high_stats['point_median']*100:>8.1f}% |"
                f" {low_stats['point_median']*100:>8.1f}% |"
                f" [{diff_stats['ci_low']*100:>+6.2f}, {diff_stats['ci_high']*100:>+6.2f}]"
                f"{' *' if diff_stats['excludes_zero'] else ''}"
            )
        else:
            print(f"{comparison_name:<28} | {'NA':>9} | {'NA':>9} | {'NA':>22}")

    summary = {
        "tag": tag,
        "iterations": args.iterations,
        "seed": args.seed,
        "overall": overall,
        "by_lineup_slot": lineup_results,
        "batter_type_comparisons": group_results,
    }
    output_path = args.output_dir / f"cpbl_bootstrap_ci_{tag}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
