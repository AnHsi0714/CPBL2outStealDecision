"""逐棒次量化「保留效應」對損益兩平門檻的貢獻（單位：pp）。

`model_batter_decisions.py` 的「盜壘刺」分支本來就會模擬到「打者的打席被保留、
下一局由同一位打者開局」（`ModelVFailure`）；同一筆決策它也順便算出了另一個沒有
用上的反事實──「若這球是打者正常出局、下一局改由下一棒開局」（`ModelVIfBatterOut`，
`out_cost_metrics` 原本拿它去分解 `ModelVNoSteal`/`ModelVSuccess`）。這兩個值的
唯一差別就是「這個打席有沒有被保留」，所以不必重跑模擬：只要把 `ModelVFailure`
換成 `ModelVIfBatterOut`、用同一個損益兩平公式重算一次門檻，兩個門檻的差就是保留
效應本身對這筆決策門檻的貢獻（pp）。逐棒次取中位數即可得到跟「門檻中位數」同一
套統計口徑的保留貢獻表。

依賴 `model_batter_decisions.py` 產生的 `cpbl_decision_model_*.csv`，不需要重跑
模擬、不需要原始 JSON 快取。
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


def threshold_value(v_success: float, v_failure: float, v_no_steal: float) -> float | None:
    denominator = v_success - v_failure
    if denominator <= 0:
        return None
    return (v_no_steal - v_failure) / denominator


def retention_values(row: dict[str, Any]) -> tuple[float, float, float] | None:
    """回傳 (實際門檻, 拿掉保留效應的反事實門檻, 兩者差的 pp)。"""
    v_success = as_float_or_none(row["ModelVSuccess"])
    v_failure = as_float_or_none(row["ModelVFailure"])
    v_no_steal = as_float_or_none(row["ModelVNoSteal"])
    v_if_out = as_float_or_none(row["ModelVIfBatterOut"])
    if None in (v_success, v_failure, v_no_steal, v_if_out):
        return None
    actual = threshold_value(v_success, v_failure, v_no_steal)
    counterfactual = threshold_value(v_success, v_if_out, v_no_steal)
    if actual is None or counterfactual is None:
        return None
    if not (0 < actual <= 1) or not (0 < counterfactual <= 1):
        return None
    return actual, counterfactual, (actual - counterfactual) * 100


def lineup_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breakdown = []
    for slot in range(1, 10):
        slot_rows = [row for row in rows if row["HitterLineup"] == str(slot)]
        values = [row["_retention"] for row in slot_rows if row["_retention"] is not None]
        excluded = len(slot_rows) - len(values)
        actual_vals = [v[0] for v in values]
        counterfactual_vals = [v[1] for v in values]
        pp_vals = [v[2] for v in values]
        breakdown.append(
            {
                "slot": slot,
                "n": len(values),
                "excluded": excluded,
                "median_actual": median(actual_vals) if actual_vals else None,
                "median_no_retention": median(counterfactual_vals) if counterfactual_vals else None,
                "median_pp": median(pp_vals) if pp_vals else None,
                "mean_pp": sum(pp_vals) / len(pp_vals) if pp_vals else None,
            }
        )
    return breakdown


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--input", type=Path, default=None, help="預設讀 step 2 的決策模型 CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_csv = args.input or Path("outputs") / f"cpbl_decision_model_{tag}.csv"

    rows = load_rows(input_csv)
    for row in rows:
        row["_retention"] = retention_values(row)

    breakdown = lineup_breakdown(rows)

    output_path = args.output_dir / f"cpbl_retention_contribution_{tag}.csv"
    write_csv(
        [
            {
                "LineupSlot": item["slot"],
                "N": item["n"],
                "Excluded": item["excluded"],
                "MedianActualThreshold": item["median_actual"],
                "MedianNoRetentionThreshold": item["median_no_retention"],
                "MedianRetentionPP": item["median_pp"],
                "MeanRetentionPP": item["mean_pp"],
            }
            for item in breakdown
        ],
        output_path,
    )

    all_pp = [row["_retention"][2] for row in rows if row["_retention"] is not None]
    print(f"\n{tag}：{len(all_pp)}/{len(rows)} 筆決策計入（denominator<=0 或門檻落在 (0,1] 之外者已排除）")
    print(f"全樣本保留貢獻中位數：{median(all_pp):+.2f} pp\n")
    print(f"{'棒次':>4} | {'N':>5} | {'排除':>4} | {'實際門檻':>8} | {'無保留門檻':>9} | {'保留貢獻(pp)':>11}")
    for item in breakdown:
        actual_str = f"{item['median_actual']*100:.1f}%" if item["median_actual"] is not None else "NA"
        no_ret_str = f"{item['median_no_retention']*100:.1f}%" if item["median_no_retention"] is not None else "NA"
        pp_str = f"{item['median_pp']:+.2f}" if item["median_pp"] is not None else "NA"
        print(f"{item['slot']:>4} | {item['n']:>5} | {item['excluded']:>4} | {actual_str:>8} | {no_ret_str:>9} | {pp_str:>11}")
    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
