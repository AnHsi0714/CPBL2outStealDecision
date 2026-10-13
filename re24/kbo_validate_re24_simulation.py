"""引擎驗證：KBO 版，做法同 validate_re24_simulation.py。

用 kbo_model_batter_decisions.py 同一套抽樣引擎（聯盟平均打者 + KBO 壘包推進經驗分布）
從 24 種 base-out state 各自模擬很多個半局，跟 kbo_build_re24_matrix.py 算出的真實 RE24
逐格比對。引擎若無法重現真實 RE24，後面的門檻結果就不可信。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import json
import random
from pathlib import Path
from statistics import mean

from model_batter_decisions import build_profiles, build_transition_pools
from kbo_model_batter_decisions import load_records_and_games
from validate_re24_simulation import compare_matrices, simulate_re24, write_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
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
    tag = args.year
    cache_dir = args.cache_dir or Path("data/raw/kbo") / tag
    real_path = args.real_summary_json or Path("outputs") / f"kbo_re24_matrix_{tag}_summary.json"
    if not real_path.exists():
        raise SystemExit(f"找不到真實 RE24 矩陣：{real_path}，請先執行 kbo_build_re24_matrix.py")
    real_summary = json.loads(real_path.read_text(encoding="utf-8-sig"))
    real_cells = {(c["outs"], c["baseCode"]): c for c in real_summary["cells"]}

    records, games = load_records_and_games(cache_dir)
    print(f"已載入 {len(games)} 場、{len(records)} 個完成打席")
    samplers, _ = build_profiles(records, args.prior_pa)
    pools = build_transition_pools(records)

    rng = random.Random(args.seed)
    sim_values = simulate_re24(
        samplers, pools, args.simulations, rng, args.minimum_transition_cell, args.max_pa,
    )
    comparison = compare_matrices({k: mean(v) for k, v in sim_values.items()}, real_cells)

    csv_path = args.output_dir / f"kbo_re24_validation_{tag}.csv"
    summary_path = args.output_dir / f"kbo_re24_validation_{tag}_summary.json"
    write_csv(comparison["cells"], csv_path)
    summary = {
        "year": args.year,
        "kind_code": "R",
        "game_sno_start": f"{args.year}-03",
        "game_sno_end": f"{args.year}-10",
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
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MAE={summary['mean_absolute_error']} 分、加權MAE={summary['weighted_mean_absolute_error']} 分、"
          f"最大誤差={summary['max_absolute_error']} 分、r={summary['correlation']}")
    print(f"CSV：{csv_path}\n摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
