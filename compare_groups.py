"""第 3 步：比較棒次分組與打者類型分組的損益兩平門檻（BreakEvenSuccessRate）。

只納入門檻落在 (0, 1] 的情境（跟報告頁「情境損益兩平中位數」用同一個篩選條件），
排除「盜壘怎麼樣都不會比失敗好」（success_not_better_than_failure）等無意義門檻。
打者類型分組只用 BatterTypeQualified=True（PA >= 100）的列，棒次分組則用全部有效門檻的列。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import mannwhitneyu


def as_float_or_none(value: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    return number


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def valid_threshold(row: dict[str, Any]) -> float | None:
    value = as_float_or_none(row["BreakEvenSuccessRate"])
    if value is None or not (0 < value <= 1):
        return None
    return value


def group_stats(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "median": median(values) if values else None,
        "mean": sum(values) / len(values) if values else None,
    }


def compare_two_groups(
    label: str, group_a_name: str, values_a: list[float], group_b_name: str, values_b: list[float]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "comparison": label,
        group_a_name: group_stats(values_a),
        group_b_name: group_stats(values_b),
    }
    if len(values_a) >= 2 and len(values_b) >= 2:
        stat, p_value = mannwhitneyu(values_a, values_b, alternative="two-sided")
        result["mann_whitney_u"] = float(stat)
        result["p_value"] = float(p_value)
    else:
        result["mann_whitney_u"] = None
        result["p_value"] = None
    return result


def substitution_stats(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """統計每筆決策當下，該棒次是先發還是代打／換人後（需先跑過 flag_lineup_substitutions.py）。"""
    if not rows or "IsStarterInSlot" not in rows[0]:
        return None
    total = len(rows)
    starters = sum(1 for row in rows if row["IsStarterInSlot"] == "True")
    by_slot = {}
    for slot in range(1, 10):
        slot_rows = [row for row in rows if row["HitterLineup"] == str(slot)]
        slot_starters = sum(1 for row in slot_rows if row["IsStarterInSlot"] == "True")
        by_slot[str(slot)] = {
            "n": len(slot_rows),
            "starters": slot_starters,
            "starterRate": slot_starters / len(slot_rows) if slot_rows else None,
        }
    return {
        "totalDecisions": total,
        "starterDecisions": starters,
        "substituteDecisions": total - starters,
        "starterRate": starters / total if total else None,
        "bySlot": by_slot,
    }


def mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [as_float_or_none(row[key]) for row in rows]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def lineup_slot_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐棒次門檻中位數，並拆出 V不跑/V失敗/V成功，方便解讀門檻為何隨棒次起伏：
    分子 = V不跑-V失敗（不跑但打席繼續 vs 盜壘刺後保留該打者的差距）
    分母 = V成功-V失敗（盜壘成功能省下多少，這個值在各棒次幾乎不變）
    """
    breakdown = []
    for slot in range(1, 10):
        slot_rows = [row for row in rows if row["HitterLineup"] == str(slot)]
        values = [row["_threshold"] for row in slot_rows]
        stats = group_stats(values)
        mean_no_steal = mean_of(slot_rows, "ModelVNoSteal")
        mean_failure = mean_of(slot_rows, "ModelVFailure")
        mean_success = mean_of(slot_rows, "ModelVSuccess")
        numerator = (
            mean_no_steal - mean_failure
            if mean_no_steal is not None and mean_failure is not None
            else None
        )
        denominator = (
            mean_success - mean_failure
            if mean_success is not None and mean_failure is not None
            else None
        )
        breakdown.append(
            {
                "slot": slot,
                **stats,
                "meanVNoSteal": mean_no_steal,
                "meanVFailure": mean_failure,
                "meanVSuccess": mean_success,
                "numerator": numerator,
                "denominator": denominator,
            }
        )
    return breakdown


def cross_table(
    rows: list[dict[str, Any]], row_key: str, col_key: str
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    row_values = sorted({r[row_key] for r in rows if r[row_key]})
    col_values = sorted({r[col_key] for r in rows if r[col_key]})
    for row_value in row_values:
        table[row_value] = {}
        for col_value in col_values:
            cell = [
                r["_threshold"]
                for r in rows
                if r[row_key] == row_value and r[col_key] == col_value
            ]
            table[row_value][col_value] = group_stats(cell)
    return table


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


def batter_type_correlations(qualified_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """相關係數要以「每位打者一筆」計算，不能直接用決策列（同一打者會重複出現多次）。"""
    unique_batters = {row["HitterAcnt"]: row for row in qualified_rows}.values()
    iso = [float(row["ISO_proxy"]) for row in unique_batters]
    bb = [float(row["BBpct_proxy"]) for row in unique_batters]
    obp = [float(row["OBP_proxy"]) for row in unique_batters]
    single = [float(row["SingleRate_proxy"]) for row in unique_batters]
    return {
        "iso_vs_bb": pearson_correlation(iso, bb),
        "iso_vs_obp": pearson_correlation(iso, obp),
        "iso_vs_single": pearson_correlation(iso, single),
        "batters": len(iso),
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
    input_csv = args.input or Path("outputs") / f"cpbl_decision_with_types_{tag}.csv"
    output_json = args.output or Path("outputs") / f"cpbl_group_comparison_{tag}.json"

    rows = load_rows(input_csv)
    for row in rows:
        row["_threshold"] = valid_threshold(row)

    valid_rows = [row for row in rows if row["_threshold"] is not None]
    qualified_rows = [row for row in valid_rows if row["BatterTypeQualified"] == "True"]

    front = [row["_threshold"] for row in valid_rows if row["LineupGroup"] == "front_1_5"]
    back = [row["_threshold"] for row in valid_rows if row["LineupGroup"] == "back_6_9"]

    high_iso = [row["_threshold"] for row in qualified_rows if row["PowerGroup"] == "high_ISO"]
    low_iso = [row["_threshold"] for row in qualified_rows if row["PowerGroup"] == "low_ISO"]

    high_bb = [row["_threshold"] for row in qualified_rows if row["PatienceGroup"] == "high_BB"]
    low_bb = [row["_threshold"] for row in qualified_rows if row["PatienceGroup"] == "low_BB"]

    high_obp = [row["_threshold"] for row in qualified_rows if row["OBPGroup"] == "high_OBP"]
    low_obp = [row["_threshold"] for row in qualified_rows if row["OBPGroup"] == "low_OBP"]

    high_contact = [row["_threshold"] for row in qualified_rows if row["ContactGroup"] == "high_1B"]
    low_contact = [row["_threshold"] for row in qualified_rows if row["ContactGroup"] == "low_1B"]

    summary = {
        "input_rows": len(rows),
        "valid_threshold_rows": len(valid_rows),
        "batter_type_qualified_rows": len(qualified_rows),
        "batter_type_correlations": batter_type_correlations(qualified_rows),
        "comparisons": [
            compare_two_groups("lineup_front_vs_back", "front_1_5", front, "back_6_9", back),
            compare_two_groups("power_high_vs_low_ISO", "high_ISO", high_iso, "low_ISO", low_iso),
            compare_two_groups("patience_high_vs_low_BB", "high_BB", high_bb, "low_BB", low_bb),
            compare_two_groups("obp_high_vs_low_OBP", "high_OBP", high_obp, "low_OBP", low_obp),
            compare_two_groups("contact_high_vs_low_1B", "high_1B", high_contact, "low_1B", low_contact),
        ],
        "cross_table_lineup_x_power": cross_table(qualified_rows, "LineupGroup", "PowerGroup"),
        "cross_table_lineup_x_patience": cross_table(qualified_rows, "LineupGroup", "PatienceGroup"),
        "cross_table_lineup_x_obp": cross_table(qualified_rows, "LineupGroup", "OBPGroup"),
        "cross_table_lineup_x_contact": cross_table(qualified_rows, "LineupGroup", "ContactGroup"),
        "lineup_slot_breakdown": lineup_slot_breakdown(valid_rows),
        "lineup_substitution": substitution_stats(rows),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for comparison in summary["comparisons"]:
        print(f"\n=== {comparison['comparison']} ===")
        for key, stats in comparison.items():
            if isinstance(stats, dict) and "median" in stats:
                print(f"  {key}: n={stats['n']}, median={stats['median']}, mean={stats['mean']}")
        print(f"  Mann-Whitney U={comparison['mann_whitney_u']}, p={comparison['p_value']}")

    print(f"\n輸出：{output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
