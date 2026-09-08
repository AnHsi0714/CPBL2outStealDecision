"""引擎驗證（第 7–8 週）：模擬引擎能否重現真實 RE24 矩陣。

計畫書 3.1 節明文要求：「模擬引擎若無法重現實際 RE24，代表引擎有誤，不可繼續
往下做」。做法：用 `model_batter_decisions.py` 同一套抽樣引擎（打者機率分布 +
聯盟壘包推進經驗分布），從 24 種 base-out state 各自起跑很多次模擬半局，取平
均剩餘得分，跟 `build_re24_matrix.py` 從真實逐球資料算出的 RE24 矩陣逐格比較。

模擬用的打線是 9 個聯盟平均打者（`LEAGUE_PROFILE_ID`），對應真實 RE24 矩陣
本身也是全聯盟不分打者的平均值，兩邊比較的才是同一件事。
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from model_batter_decisions import (
    LEAGUE_PROFILE_ID,
    build_profiles,
    build_transition_pools,
    correlation,
    extract_pa_records,
    load_raw_games,
    simulate_half,
)


BASE_LABELS = {
    0: "空壘", 1: "一壘", 2: "二壘", 4: "三壘",
    3: "一二壘", 5: "一三壘", 6: "二三壘", 7: "一二三壘",
}


def simulate_re24(
    samplers: dict[str, Any],
    pools: dict[tuple[int, int, str], list[Any]],
    simulations: int,
    rng: random.Random,
    minimum_cell: int,
    max_pa: int,
) -> dict[tuple[int, int], list[int]]:
    """對 24 種 (outs, base_code) state 各自模擬 simulations 次半局剩餘得分。"""
    lineup = tuple(LEAGUE_PROFILE_ID for _ in range(9))
    results: dict[tuple[int, int], list[int]] = {}
    for outs in (0, 1, 2):
        for base_code in range(8):
            values = []
            for _ in range(simulations):
                runs, _ = simulate_half(
                    lineup, 0, outs, base_code, samplers, pools, rng, minimum_cell, max_pa
                )
                values.append(runs)
            results[(outs, base_code)] = values
    return results


def compare_matrices(
    sim_means: dict[tuple[int, int], float],
    real_cells: dict[tuple[int, int], dict[str, Any]],
) -> dict[str, Any]:
    """逐格比較模擬與真實 RE24，回傳每格差異與整體誤差指標。"""
    rows: list[dict[str, Any]] = []
    abs_errors: list[float] = []
    weighted_abs_errors: list[float] = []
    total_n = 0
    sim_series: list[float] = []
    real_series: list[float] = []

    for outs in (0, 1, 2):
        for base_code in range(8):
            sim_mean = sim_means.get((outs, base_code))
            real_cell = real_cells.get((outs, base_code))
            real_mean = real_cell["meanRE"] if real_cell else None
            real_n = real_cell["n"] if real_cell else 0
            diff = (sim_mean - real_mean) if (sim_mean is not None and real_mean is not None) else None
            rel_diff = (diff / real_mean) if (diff is not None and real_mean) else None
            rows.append(
                {
                    "outs": outs,
                    "baseCode": base_code,
                    "baseLabel": BASE_LABELS[base_code],
                    "simMeanRE": round(sim_mean, 4) if sim_mean is not None else None,
                    "realMeanRE": real_mean,
                    "realN": real_n,
                    "diff": round(diff, 4) if diff is not None else None,
                    "relDiff": round(rel_diff, 4) if rel_diff is not None else None,
                }
            )
            if diff is not None:
                abs_errors.append(abs(diff))
                weighted_abs_errors.append(abs(diff) * real_n)
                total_n += real_n
                sim_series.append(sim_mean)
                real_series.append(real_mean)

    return {
        "cells": rows,
        "meanAbsoluteError": round(mean(abs_errors), 4) if abs_errors else None,
        "weightedMeanAbsoluteError": (
            round(sum(weighted_abs_errors) / total_n, 4) if total_n else None
        ),
        "maxAbsoluteError": round(max(abs_errors), 4) if abs_errors else None,
        "correlation": round(correlation(sim_series, real_series), 4)
        if len(sim_series) >= 2
        else None,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    fieldnames = ["outs", "baseCode", "baseLabel", "simMeanRE", "realMeanRE", "realN", "diff", "relDiff"]
    with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--real-summary-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--simulations", type=int, default=3000)
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
    parser.add_argument("--max-pa", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260805)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    real_summary_path = (
        args.real_summary_json
        or Path("outputs") / f"cpbl_re24_matrix_{tag}_summary.json"
    )
    if not real_summary_path.exists():
        raise SystemExit(f"找不到真實 RE24 矩陣：{real_summary_path}，請先執行 build_re24_matrix.py")

    with real_summary_path.open("r", encoding="utf-8-sig") as handle:
        real_summary = json.load(handle)
    real_cells = {(c["outs"], c["baseCode"]): c for c in real_summary["cells"]}

    print(f"讀取快取場次：{cache_dir}")
    games = load_raw_games(cache_dir)
    if not games:
        raise SystemExit(
            f"{cache_dir} 沒有快取場次，請先執行 find_2out_first_base.py 或 build_re24_matrix.py 建立快取"
        )
    records = [record for rows in games.values() for record in extract_pa_records(rows)]
    print(f"已載入 {len(games)} 場、{len(records)} 個完成打席，開始建打者檔與壘包推進池")
    samplers, _ = build_profiles(records, args.prior_pa)
    pools = build_transition_pools(records)

    rng = random.Random(args.seed)
    sim_values = simulate_re24(
        samplers, pools, args.simulations, rng, args.minimum_transition_cell, args.max_pa
    )
    sim_means = {key: mean(values) for key, values in sim_values.items()}

    comparison = compare_matrices(sim_means, real_cells)

    csv_path = args.output_dir / f"cpbl_re24_validation_{tag}.csv"
    summary_path = args.output_dir / f"cpbl_re24_validation_{tag}_summary.json"
    write_csv(comparison["cells"], csv_path)

    summary = {
        "year": args.year,
        "kind_code": args.kind_code,
        "game_sno_start": args.start,
        "game_sno_end": args.end,
        "games_with_raw_data": len(games),
        "completed_pa_for_profiles": len(records),
        "simulations_per_state": args.simulations,
        "prior_pa": args.prior_pa,
        "minimum_transition_cell": args.minimum_transition_cell,
        "seed": args.seed,
        "mean_absolute_error": comparison["meanAbsoluteError"],
        "weighted_mean_absolute_error": comparison["weightedMeanAbsoluteError"],
        "max_absolute_error": comparison["maxAbsoluteError"],
        "correlation": comparison["correlation"],
        "cells": comparison["cells"],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = summary_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(summary_path)

    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    print(
        f"MAE={summary['mean_absolute_error']} 分、"
        f"加權MAE={summary['weighted_mean_absolute_error']} 分、"
        f"最大誤差={summary['max_absolute_error']} 分、"
        f"相關係數 r={summary['correlation']}"
    )
    worst = sorted(
        (row for row in comparison["cells"] if row["diff"] is not None),
        key=lambda row: abs(row["diff"]),
        reverse=True,
    )[:5]
    print("誤差最大的 5 格：")
    for row in worst:
        print(
            f"  {row['outs']}出局 {row['baseLabel']}："
            f"模擬 {row['simMeanRE']} vs 真實 {row['realMeanRE']}"
            f"（差 {row['diff']:+.4f}，n={row['realN']}）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
