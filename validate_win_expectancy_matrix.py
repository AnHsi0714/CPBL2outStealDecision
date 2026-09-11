"""檢驗 `build_win_expectancy_matrix.py` 產生的勝率矩陣是否可信。

WE 矩陣是從真實比賽逐球資料直接算出的經驗值（不像 RE24 驗證那樣有一套獨立
的模擬引擎可以拿來對照），所以這裡做的是兩類檢查：

1. **單調性**：固定 (局數 bucket, 攻守方, 出局數, 壘包組合)，勝率理應隨分差
   遞增（分差對進攻方愈有利，最終獲勝機率愈高）。只比較兩格 n 都 >=
   `--min-n-for-monotonicity` 的相鄰分差，否則小樣本雜訊會製造假警報。
2. **涵蓋度**：本研究真正關心的格子——2 出局、一壘或二壘有人、第 7–8
   局——每一格的樣本數是否足夠（`--min-n-for-coverage`），格子數遠多於
   RE24 的 24 格，稀疏是主要風險（見計畫書第 213 項）。

額外印出「平手時攻守方勝率」當粗略的主場優勢檢查：主隊進攻（下半局）在
平手時的勝率理論上應高於客隊進攻（上半局），因為多了「再見」優勢。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_win_expectancy_matrix import (
    BATTING_SIDE_LABELS,
    INNING_BUCKETS,
    SCORE_DIFF_CAP,
)
from build_re24_matrix import BASE_STATE_LABELS


def check_monotonicity(cells: dict[tuple, dict[str, Any]], min_n: int) -> list[dict[str, Any]]:
    violations = []
    for inning_bucket in INNING_BUCKETS:
        for batting_side in ("1", "2"):
            for outs in (0, 1, 2):
                for base_code in range(8):
                    prev_cell = None
                    for diff in range(-SCORE_DIFF_CAP, SCORE_DIFF_CAP + 1):
                        cell = cells.get((inning_bucket, batting_side, diff, outs, base_code))
                        if cell is None or cell["winRate"] is None:
                            continue
                        if (
                            prev_cell is not None
                            and prev_cell["n"] >= min_n
                            and cell["n"] >= min_n
                            and cell["winRate"] < prev_cell["winRate"]
                        ):
                            violations.append(
                                {
                                    "inningBucket": inning_bucket,
                                    "battingSideLabel": BATTING_SIDE_LABELS[batting_side],
                                    "outs": outs,
                                    "baseLabel": BASE_STATE_LABELS[base_code],
                                    "fromDiff": prev_cell["scoreDiffBucket"],
                                    "fromWinRate": prev_cell["winRate"],
                                    "fromN": prev_cell["n"],
                                    "toDiff": cell["scoreDiffBucket"],
                                    "toWinRate": cell["winRate"],
                                    "toN": cell["n"],
                                    "drop": round(prev_cell["winRate"] - cell["winRate"], 4),
                                }
                            )
                        prev_cell = cell
    return violations


def coverage_report(
    cells: dict[tuple, dict[str, Any]], min_n: int
) -> list[dict[str, Any]]:
    """本研究實際會用到的格子：2 出局、一壘或二壘有人、第 7–8 局，所有分差與攻守方。"""
    rows = []
    for inning_bucket in ("7", "8"):
        for batting_side in ("1", "2"):
            for base_code in (1, 2):
                for diff in range(-SCORE_DIFF_CAP, SCORE_DIFF_CAP + 1):
                    cell = cells.get((inning_bucket, batting_side, diff, 2, base_code))
                    n = cell["n"] if cell else 0
                    rows.append(
                        {
                            "inningBucket": inning_bucket,
                            "battingSideLabel": BATTING_SIDE_LABELS[batting_side],
                            "baseLabel": BASE_STATE_LABELS[base_code],
                            "scoreDiffBucket": diff,
                            "n": n,
                            "winRate": cell["winRate"] if cell else None,
                            "belowMinN": n < min_n,
                        }
                    )
    return rows


def tied_game_split(cells: dict[tuple, dict[str, Any]]) -> dict[str, Any]:
    """平手時攻守方勝率（粗略主場優勢檢查）：合併所有局數/出局/壘包的分母。"""
    totals = {"1": [0.0, 0], "2": [0.0, 0]}
    for (inning_bucket, batting_side, diff, outs, base_code), cell in cells.items():
        if diff != 0 or cell["winRate"] is None:
            continue
        totals[batting_side][0] += cell["winRate"] * cell["n"]
        totals[batting_side][1] += cell["n"]
    return {
        BATTING_SIDE_LABELS[side]: {
            "n": count,
            "winRate": round(total / count, 4) if count else None,
        }
        for side, (total, count) in totals.items()
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("outputs/cpbl_win_expectancy_matrix_2023-2026_A_combined_summary.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--output-tag", default="2023-2026_A_combined")
    parser.add_argument("--min-n-for-monotonicity", type=int, default=15)
    parser.add_argument("--min-n-for-coverage", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.summary_json.exists():
        raise SystemExit(f"找不到 WE 矩陣摘要：{args.summary_json}，請先執行 build_win_expectancy_matrix.py")

    with args.summary_json.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)

    cells = {
        (c["inningBucket"], c["battingSide"], c["scoreDiffBucket"], c["outs"], c["baseCode"]): c
        for c in summary["cells"]
    }

    violations = check_monotonicity(cells, args.min_n_for_monotonicity)
    coverage = coverage_report(cells, args.min_n_for_coverage)
    tied_split = tied_game_split(cells)

    low_coverage = [row for row in coverage if row["belowMinN"]]

    result = {
        "source_summary_json": str(args.summary_json),
        "min_n_for_monotonicity": args.min_n_for_monotonicity,
        "min_n_for_coverage": args.min_n_for_coverage,
        "monotonicity_violations": violations,
        "monotonicity_violation_count": len(violations),
        "coverage_target_cells": coverage,
        "coverage_target_cell_count": len(coverage),
        "coverage_below_min_n_count": len(low_coverage),
        "tied_game_win_rate_by_batting_side": tied_split,
    }

    output_json = args.output_dir / f"cpbl_win_expectancy_validation_{args.output_tag}_summary.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    temp_path = output_json.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(output_json)

    print(f"單調性違反：{len(violations)} 處（n>={args.min_n_for_monotonicity} 的相鄰分差對）")
    for row in violations[:10]:
        print(
            f"  {row['inningBucket']}局 {row['battingSideLabel']} {row['outs']}出局 {row['baseLabel']}："
            f"分差 {row['fromDiff']:+d}→{row['toDiff']:+d}，勝率 {row['fromWinRate']}→{row['toWinRate']}"
            f"（降 {row['drop']}，n={row['fromN']}/{row['toN']}）"
        )
    if len(violations) > 10:
        print(f"  ...其餘 {len(violations) - 10} 處見 {output_json}")

    print(
        f"目標情境（2出局、一/二壘有人、第7-8局）涵蓋度：{len(coverage)} 格，"
        f"其中 {len(low_coverage)} 格 n < {args.min_n_for_coverage}"
    )
    for row in low_coverage[:10]:
        print(
            f"  低樣本：{row['inningBucket']}局 {row['battingSideLabel']} {row['baseLabel']} "
            f"分差{row['scoreDiffBucket']:+d}：n={row['n']}"
        )
    if len(low_coverage) > 10:
        print(f"  ...其餘 {len(low_coverage) - 10} 格見 {output_json}")

    print("平手時勝率（粗略主場優勢檢查，理論上主隊進攻應略高於客隊進攻）：")
    for label, stats in tied_split.items():
        print(f"  {label}：n={stats['n']}，勝率={stats['winRate']}")

    print(f"摘要：{output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
