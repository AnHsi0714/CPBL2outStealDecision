"""棒次分組與打者類型分組的 RE 版結論，換成 WPA 判準還成不成立。

`compare_groups.py` 的既有結論（低點在 1、2 棒；高點在第 4 棒；8、9 棒因保留
效應再度墊高；高長打／高選球打者門檻都比對照組高）全部用全部局數（1–8 局）
的決策算出來。README「WPA 版損益兩平門檻」一節已確認 WPA 門檻的點估計只有
第 4 局起才穩定（第 1–3 局中位數落在自己的 bootstrap 信賴區間之外）；因此
這裡只用第 4–8 局的決策重算一次，RE 版也用同一個子集重算（不是直接套用
`compare_groups.py` 用全部局數算出的舊數字），兩邊才是同一批樣本、只有價值
函數不同，比較才公平。

讀 `cpbl_decision_with_types_{tag}.csv`（棒次與打者類型分組，RE 版門檻）和
`cpbl_wpa_decision_model_{tag}.csv`（WPA 版門檻），用 (GameSno, StateRowIndex)
對齊同一筆決策。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import mannwhitneyu

from compare_groups import group_stats
from find_2out_first_base import as_int


RELIABLE_INNINGS = {4, 5, 6, 7, 8}


def as_float_or_none(value: str) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def valid_threshold(value: str | None) -> float | None:
    number = as_float_or_none(value) if value is not None else None
    if number is None or not (0 < number <= 1):
        return None
    return number


def load_wpa_thresholds(path: Path) -> dict[tuple[int, int], float | None]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return {
        (as_int(row["GameSno"]), as_int(row["StateRowIndex"])): valid_threshold(
            row.get("BreakEvenSuccessRate_WPA")
        )
        for row in rows
    }


def load_joined_rows(types_csv: Path, wpa_csv: Path) -> list[dict[str, Any]]:
    wpa_thresholds = load_wpa_thresholds(wpa_csv)
    with types_csv.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    joined = []
    for row in rows:
        if as_int(row["InningSeq"]) not in RELIABLE_INNINGS:
            continue
        key = (as_int(row["GameSno"]), as_int(row["StateRowIndex"]))
        if key not in wpa_thresholds:
            continue
        row["_threshold_re"] = valid_threshold(row.get("BreakEvenSuccessRate"))
        row["_threshold_wpa"] = wpa_thresholds[key]
        joined.append(row)
    return joined


def lineup_slot_medians(rows: list[dict[str, Any]], threshold_key: str) -> dict[int, dict[str, Any]]:
    result = {}
    for slot in range(1, 10):
        values = [row[threshold_key] for row in rows if row["HitterLineup"] == str(slot) and row[threshold_key] is not None]
        result[slot] = group_stats(values)
    return result


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


GROUP_AXES = [
    ("power_high_vs_low_ISO", "PowerGroup", "high_ISO", "low_ISO"),
    ("patience_high_vs_low_BB", "PatienceGroup", "high_BB", "low_BB"),
    ("obp_high_vs_low_OBP", "OBPGroup", "high_OBP", "low_OBP"),
    ("contact_high_vs_low_1B", "ContactGroup", "high_1B", "low_1B"),
    ("tto_high_vs_low_TTO", "TTOGroup", "high_TTO", "low_TTO"),
]


def build_group_comparisons(rows: list[dict[str, Any]], threshold_key: str) -> list[dict[str, Any]]:
    qualified = [row for row in rows if row["BatterTypeQualified"] == "True" and row[threshold_key] is not None]
    comparisons = []
    for label, column, high_label, low_label in GROUP_AXES:
        high_values = [row[threshold_key] for row in qualified if row[column] == high_label]
        low_values = [row[threshold_key] for row in qualified if row[column] == low_label]
        comparisons.append(compare_two_groups(label, high_label, high_values, low_label, low_values))
    return comparisons


def direction_label(comparison: dict[str, Any]) -> str:
    keys = [k for k in comparison if k not in ("comparison", "mann_whitney_u", "p_value")]
    a_key, b_key = keys
    a_median = comparison[a_key]["median"]
    b_median = comparison[b_key]["median"]
    if a_median is None or b_median is None:
        return "NA"
    if a_median > b_median:
        return f"{a_key}>{b_key}"
    if a_median < b_median:
        return f"{a_key}<{b_key}"
    return "="


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--types-csv", type=Path, help="預設讀 join_decision_batter_types.py 的輸出")
    parser.add_argument("--wpa-csv", type=Path, help="預設讀 model_wpa_decisions.py 的輸出")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    types_csv = args.types_csv or Path("outputs") / f"cpbl_decision_with_types_{tag}.csv"
    wpa_csv = args.wpa_csv or Path("outputs") / f"cpbl_wpa_decision_model_{tag}.csv"
    if not types_csv.exists():
        raise SystemExit(f"找不到 {types_csv}，請先執行 join_decision_batter_types.py")
    if not wpa_csv.exists():
        raise SystemExit(f"找不到 {wpa_csv}，請先執行 model_wpa_decisions.py")

    rows = load_joined_rows(types_csv, wpa_csv)

    re_lineup = lineup_slot_medians(rows, "_threshold_re")
    wpa_lineup = lineup_slot_medians(rows, "_threshold_wpa")
    re_groups = build_group_comparisons(rows, "_threshold_re")
    wpa_groups = build_group_comparisons(rows, "_threshold_wpa")

    summary = {
        "tag": tag,
        "reliable_innings": sorted(RELIABLE_INNINGS),
        "joined_rows": len(rows),
        "lineup_slot_re": re_lineup,
        "lineup_slot_wpa": wpa_lineup,
        "group_comparisons_re": re_groups,
        "group_comparisons_wpa": wpa_groups,
    }
    output_path = args.output_dir / f"cpbl_wpa_group_comparison_{tag}.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output_path)

    print(f"{tag}：第 4-8 局共 {len(rows)} 筆決策同時有 RE 與 WPA 門檻")
    print("\n逐棒次門檻中位數（第 4-8 局子集）：")
    print(f"{'棒次':>4} | {'RE':>7} | {'WPA':>7} | {'n':>4}")
    for slot in range(1, 10):
        re_stat = re_lineup[slot]
        wpa_stat = wpa_lineup[slot]
        re_text = f"{re_stat['median']*100:.1f}%" if re_stat["median"] is not None else "NA"
        wpa_text = f"{wpa_stat['median']*100:.1f}%" if wpa_stat["median"] is not None else "NA"
        print(f"{slot:>4} | {re_text:>7} | {wpa_text:>7} | {wpa_stat['n']:>4}")

    print("\n打者類型分組（高組 vs 低組，方向是否一致）：")
    for re_cmp, wpa_cmp in zip(re_groups, wpa_groups):
        re_dir = direction_label(re_cmp)
        wpa_dir = direction_label(wpa_cmp)
        if "NA" in (re_dir, wpa_dir) or "=" in (re_dir, wpa_dir):
            same = "無法比較"
        else:
            same = "同方向" if (">" in re_dir) == (">" in wpa_dir) else "方向不同"
        p_re = f"{re_cmp['p_value']:.3f}" if re_cmp["p_value"] is not None else "NA"
        p_wpa = f"{wpa_cmp['p_value']:.3f}" if wpa_cmp["p_value"] is not None else "NA"
        print(f"  {re_cmp['comparison']}：RE={re_dir}(p={p_re})　WPA={wpa_dir}(p={p_wpa})　{same}")

    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
