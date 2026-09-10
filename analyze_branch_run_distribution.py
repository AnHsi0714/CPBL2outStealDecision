"""比較盜壘成功／失敗／不跑三分支的得分「機率分布」，不只是期望值。

`model_batter_decisions.py` 算出的 `ModelVSuccess`/`ModelVFailure`/`ModelVNoSteal`
都只是 2000 次蒙地卡羅模擬的平均得分，原始的每次模擬結果算完平均就丟了，看不
出分布形狀。這裡重跑同一套模擬引擎（打者機率分布＋聯盟壘包推進經驗分布），
改成保留每次模擬的得分桶（0／1／2／3+分），回答「兩情境是否都有機會得分，
但其中一種傾向拿到更多分（大局），另一種只是比較穩地拿到一分」這類問題。

只比較三分支本身的分布，不分比分情境；若這裡看出有意義的差異，且想進一步檢
查落後大局時取捨是否不同，才需要疊上 `analyze_score_diff_steal_rate.py` 的
分差欄位（屬於另一步，這裡不做）。

依 (lineup, current_slot) 情境快取模擬結果，跟 `model_batter_decisions.py`
main() 的做法一致——同一個打線組合＋棒次在不同決策列重複出現時不必重跑。
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any

from find_2out_first_base import as_int
from model_batter_decisions import (
    LEAGUE_PROFILE_ID,
    build_profiles,
    build_transition_pools,
    extract_pa_records,
    find_state_index,
    lineup_at,
    load_raw_games,
    simulate_half,
)


RUN_CAP = 3  # 3 代表「3 分以上」，其餘桶為實際分數


def bucket_counts(values: list[int]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for value in values:
        counts[value if value < RUN_CAP else RUN_CAP] += 1
    return counts


def simulate_branch_distributions(
    lineup: tuple[str, ...],
    current_slot: int,
    samplers: dict[str, Any],
    pools: dict[tuple[int, int, str], list[Any]],
    simulations: int,
    rng: random.Random,
    minimum_cell: int,
) -> dict[str, list[int]]:
    """跟 `model_batter_decisions.simulate_context` 同一套模擬邏輯，但保留原始得分序列。"""
    success_values: list[int] = []
    failure_values: list[int] = []
    no_steal_values: list[int] = []
    for _ in range(simulations):
        current_runs, next_slot = simulate_half(
            lineup, current_slot, 2, 2, samplers, pools, rng, minimum_cell
        )
        next_runs, _ = simulate_half(
            lineup, next_slot, 0, 0, samplers, pools, rng, minimum_cell
        )
        success_values.append(current_runs + next_runs)

        current_runs, next_slot = simulate_half(
            lineup, current_slot, 2, 1, samplers, pools, rng, minimum_cell
        )
        next_runs, _ = simulate_half(
            lineup, next_slot, 0, 0, samplers, pools, rng, minimum_cell
        )
        no_steal_values.append(current_runs + next_runs)

        runs, _ = simulate_half(
            lineup, current_slot, 0, 0, samplers, pools, rng, minimum_cell
        )
        failure_values.append(runs)

    return {"success": success_values, "no_steal": no_steal_values, "failure": failure_values}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    decision_csv = args.decision_csv or Path("outputs") / f"cpbl_2out_first_base_{tag}.csv"
    if not decision_csv.exists():
        raise SystemExit(f"找不到決策樣本：{decision_csv}，請先執行 find_2out_first_base.py")

    games = load_raw_games(cache_dir)
    records = [record for rows in games.values() for record in extract_pa_records(rows)]
    samplers, _ = build_profiles(records, args.prior_pa)
    pools = build_transition_pools(records)
    with decision_csv.open(newline="", encoding="utf-8-sig") as file:
        decisions = list(csv.DictReader(file))

    rng = random.Random(args.seed)
    cache: dict[tuple[tuple[str, ...], int], dict[str, Counter[int]]] = {}
    totals: dict[str, Counter[int]] = {
        "success": Counter(), "no_steal": Counter(), "failure": Counter()
    }
    unmatched = 0

    for decision in decisions:
        game_sno = as_int(decision.get("GameSno"))
        rows = games.get(game_sno)
        if not rows:
            unmatched += 1
            continue
        state_index = find_state_index(rows, decision)
        if state_index is None:
            unmatched += 1
            continue
        state = rows[state_index]
        batting_side = str(state.get("VisitingHomeType") or "")
        lineup = list(lineup_at(rows, state_index, batting_side))
        current_slot = as_int(state.get("HitterLineup"), 1) - 1
        current_slot = min(8, max(0, current_slot))
        hitter_id = str(state.get("HitterAcnt") or LEAGUE_PROFILE_ID)
        lineup[current_slot] = hitter_id
        lineup_tuple = tuple(lineup)
        context_key = (lineup_tuple, current_slot)
        if context_key not in cache:
            branch_values = simulate_branch_distributions(
                lineup_tuple, current_slot, samplers, pools,
                args.simulations, rng, args.minimum_transition_cell,
            )
            cache[context_key] = {
                branch: bucket_counts(values) for branch, values in branch_values.items()
            }
        for branch, counts in cache[context_key].items():
            totals[branch].update(counts)

    if unmatched:
        print(f"警告：{unmatched} 筆決策找不到對應原始資料，已略過")

    print(f"\n{tag}：{len(decisions) - unmatched} 筆決策計入、{len(cache)} 個不重複(打線,棒次)情境\n")
    header = f"{'分支':>8} | {'0分':>7} | {'1分':>7} | {'2分':>7} | {'3分+':>7} | {'≥1分':>7} | {'≥2分':>7}"
    print(header)
    rows_out: list[dict[str, Any]] = []
    for branch in ("success", "no_steal", "failure"):
        counts = totals[branch]
        total_n = sum(counts.values())
        p0 = counts[0] / total_n
        p1 = counts[1] / total_n
        p2 = counts[2] / total_n
        p3plus = counts[RUN_CAP] / total_n
        p_ge1 = 1 - p0
        p_ge2 = p2 + p3plus
        print(
            f"{branch:>8} | {p0:>6.1%} | {p1:>6.1%} | {p2:>6.1%} | {p3plus:>6.1%}"
            f" | {p_ge1:>6.1%} | {p_ge2:>6.1%}"
        )
        rows_out.append(
            {
                "Branch": branch,
                "N": total_n,
                "P_Runs0": p0,
                "P_Runs1": p1,
                "P_Runs2": p2,
                "P_Runs3Plus": p3plus,
                "P_RunsGE1": p_ge1,
                "P_RunsGE2": p_ge2,
            }
        )

    output_path = args.output_dir / f"cpbl_branch_run_distribution_{tag}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"\n明細已寫出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
