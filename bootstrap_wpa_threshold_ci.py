"""WPA 版損益兩平門檻中位數的 95% bootstrap 信賴區間（整體／逐局／早局vs晚局）。

對應 `bootstrap_threshold_ci.py` 對 RE 版模型做的事，但套在
`model_wpa_decisions.py` 的輸出上，直接回答「第 7–8 局 WPA 門檻明顯低於
RE 門檻」這個結論撐不撐得住抽樣雜訊。

跟 RE 版 bootstrap 用同一套雙重不確定性設計：對決策列做 case resampling，
同時用 `model_wpa_decisions.py` 已經算好的 `WE_VSuccessSE`／`WE_VFailureSE`
（WE 表格子的二項標準誤）／`WE_VNoStealSE`（一步蒙地卡羅的標準誤，已經把
WE 格子雜訊也算進去了）對三個 V 值加常態雜訊，兩種不確定性來源一次涵蓋。
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import median
from typing import Any

from bootstrap_threshold_ci import bootstrap_diff_ci, bootstrap_median_ci, load_rows


class WPARowValues:
    __slots__ = ("v_success", "v_success_se", "v_failure", "v_failure_se", "v_no_steal", "v_no_steal_se")

    def __init__(self, row: dict[str, Any]) -> None:
        self.v_success = float(row["WE_VSuccess"])
        self.v_success_se = float(row["WE_VSuccessSE"] or 0.0)
        self.v_failure = float(row["WE_VFailure"])
        self.v_failure_se = float(row["WE_VFailureSE"] or 0.0)
        self.v_no_steal = float(row["WE_VNoSteal"])
        self.v_no_steal_se = float(row["WE_VNoStealSE"] or 0.0)


def extract_values(rows: list[dict[str, Any]]) -> list[WPARowValues]:
    result = []
    for row in rows:
        raw = row.get("BreakEvenSuccessRate_WPA")
        if raw in (None, ""):
            continue
        value = float(raw)
        if not (0 < value <= 1):
            continue
        try:
            result.append(WPARowValues(row))
        except (TypeError, ValueError):
            continue
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--input", type=Path, help="預設讀 model_wpa_decisions.py 的輸出")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_csv = args.input or Path("outputs") / f"cpbl_wpa_decision_model_{tag}.csv"
    if not input_csv.exists():
        raise SystemExit(f"找不到 {input_csv}，請先執行 model_wpa_decisions.py")
    rng = random.Random(args.seed)

    rows = load_rows(input_csv)
    all_values = extract_values(rows)

    overall = bootstrap_median_ci(all_values, rng, args.iterations)
    print(f"\n{tag}：{overall['n'] if overall else 0}/{len(rows)} 筆決策計入，bootstrap {args.iterations} 次")
    if overall:
        print(
            f"整體 WPA 門檻中位數：{overall['point_median']*100:.1f}%"
            f"（95% CI {overall['ci_low']*100:.1f}%–{overall['ci_high']*100:.1f}%）"
        )

    by_inning_results = []
    print(f"\n{'局':>4} | {'N':>5} | {'中位數':>7} | {'95% CI':>15}")
    for inning in range(1, 9):
        inning_values = extract_values([row for row in rows if row.get("InningSeq") == str(inning)])
        stats = bootstrap_median_ci(inning_values, rng, args.iterations)
        by_inning_results.append({"inning": inning, **(stats or {})})
        if stats:
            print(
                f"{inning:>4} | {stats['n']:>5} | {stats['point_median']*100:>6.1f}% |"
                f" [{stats['ci_low']*100:>5.1f}%, {stats['ci_high']*100:>5.1f}%]"
            )
        else:
            print(f"{inning:>4} | {'NA':>5} | {'NA':>7} | {'NA':>15}")

    early_values = extract_values([row for row in rows if row.get("InningSeq") in ("1", "2", "3", "4", "5", "6")])
    late_values = extract_values([row for row in rows if row.get("InningSeq") in ("7", "8")])
    early_stats = bootstrap_median_ci(early_values, rng, args.iterations)
    late_stats = bootstrap_median_ci(late_values, rng, args.iterations)
    diff_stats = bootstrap_diff_ci(late_values, early_values, rng, args.iterations)
    print("\n早局（1–6）vs 晚局（7–8）WPA 門檻中位數：")
    if early_stats and late_stats:
        print(
            f"  1–6局：{early_stats['point_median']*100:.1f}%"
            f"（95% CI {early_stats['ci_low']*100:.1f}%–{early_stats['ci_high']*100:.1f}%，n={early_stats['n']}）"
        )
        print(
            f"  7–8局：{late_stats['point_median']*100:.1f}%"
            f"（95% CI {late_stats['ci_low']*100:.1f}%–{late_stats['ci_high']*100:.1f}%，n={late_stats['n']}）"
        )
    if diff_stats:
        print(
            f"  差（7-8局 － 1-6局）：{diff_stats['point_diff']*100:+.1f}pp"
            f"（95% CI {diff_stats['ci_low']*100:+.1f}pp – {diff_stats['ci_high']*100:+.1f}pp）"
            f"{'　*不含0，差異顯著' if diff_stats['excludes_zero'] else '　（區間含0，不能排除無差異）'}"
        )

    summary = {
        "tag": tag,
        "iterations": args.iterations,
        "seed": args.seed,
        "overall": overall,
        "by_inning": by_inning_results,
        "early_1_to_6": early_stats,
        "late_7_to_8": late_stats,
        "late_minus_early_diff": diff_stats,
    }
    output_path = args.output_dir / f"cpbl_wpa_bootstrap_ci_{tag}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
