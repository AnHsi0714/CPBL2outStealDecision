"""跟 model_batter_decisions.py 同一套蒙地卡羅模擬引擎，資料來源換成 KBO 官網文字轉播。

共用的模擬數學直接從 model_batter_decisions.py 匯入；本檔案只處理 KBO 特有的三塊：打席結果分類與
打席群組（kbo_find_2out_first_base.build_pa_records，從敘述句規則重建）、球員主鍵（`球隊:姓名`，
KBO 文字轉播沒有球員 ID）、打序重建（文字轉播的「N번타자」直接給棒次）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from model_batter_decisions import (
    LEAGUE_PROFILE_ID,
    OUTCOMES,
    PARecord,
    Transition,
    branch_stats,  # noqa: F401 (re-exported for parity / possible reuse elsewhere)
    build_profiles,
    build_transition_pools,
    correlation,
    out_cost_metrics,
    simulate_context,
    threshold_result,
    write_csv,
)
from kbo_find_2out_first_base import build_pa_records, iter_cached_games

import random


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_records_and_games(cache_dir: Path) -> tuple[list[PARecord], dict[str, list[dict[str, Any]]]]:
    """回傳 (全部打席紀錄, {GameSno: 該場打席紀錄清單（時間順序）})。"""
    records: list[PARecord] = []
    games: dict[str, list[dict[str, Any]]] = {}
    for meta, rows in iter_cached_games(cache_dir):
        game_records = build_pa_records(rows)
        games[str(meta["GameSno"])] = game_records
        for r in game_records:
            if r["outcome"] == "NONE":
                continue
            records.append(PARecord(
                game_sno=meta["GameSno"],
                inning=r["inning"],
                batting_side="away" if r["is_top"] else "home",
                hitter_id=r["batter_id"],
                hitter_name=r["batter_name"] or "",
                lineup_slot=r["lineup_slot"] or -1,
                start_outs=r["start_outs"],
                start_bases=r["start_bases"],
                outcome=r["outcome"],
                transition=Transition(r["runs"], r["outs_after"], r["bases_after"]),
                has_runner_event=r["has_runner_event"],
                is_strikeout=r["is_strikeout"],
            ))
    return records, games


def find_play_index(game_records: list[dict[str, Any]], inning: int, is_top: bool, batter_id: str) -> int | None:
    for index, record in enumerate(game_records):
        if record["inning"] == inning and record["is_top"] == is_top and record["batter_id"] == batter_id:
            return index
    return None


def lineup_at(game_records: list[dict[str, Any]], decision_index: int, is_away_batting: bool) -> tuple[str, ...]:
    """每個棒次取決策當下（含）之前最近一位打者；還沒出現過的棒次取之後第一位，都沒有就用聯盟平均。"""
    lineup: list[str] = []
    for slot in range(1, 10):
        before: str | None = None
        after: str | None = None
        for index, record in enumerate(game_records):
            if record["is_top"] != is_away_batting or record["lineup_slot"] != slot:
                continue
            if index <= decision_index:
                before = record["batter_id"]
            elif after is None:
                after = record["batter_id"]
        lineup.append(before or after or LEAGUE_PROFILE_ID)
    return tuple(lineup)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260805)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = args.year
    cache_dir = args.cache_dir or Path("data/raw/kbo") / tag
    decision_csv = args.decision_csv or Path("outputs") / f"kbo_2out_first_base_{tag}.csv"
    if not decision_csv.exists():
        raise SystemExit(f"找不到決策樣本：{decision_csv}，請先執行 kbo_find_2out_first_base.py")

    records, games = load_records_and_games(cache_dir)
    samplers, profile_rows = build_profiles(records, args.prior_pa)
    profile_pa_by_id = {row["HitterAcnt"]: row["PA"] for row in profile_rows}
    pools = build_transition_pools(records)
    with decision_csv.open(newline="", encoding="utf-8-sig") as file:
        decisions = list(csv.DictReader(file))

    rng = random.Random(args.seed)
    cache: dict[tuple[tuple[str, ...], int], dict[str, Any]] = {}
    model_rows: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for position, decision in enumerate(decisions, 1):
        game_pk = str(decision.get("GamePk"))
        game_records = games.get(game_pk)
        if game_records is None:
            unmatched.append({"GamePk": game_pk, "reason": "raw game missing"})
            continue
        inning = as_int(decision.get("InningSeq"))
        is_top = decision.get("IsTopInning") == "True"
        batter_id = decision.get("BatterId") or ""
        play_index = find_play_index(game_records, inning, is_top, batter_id)
        if play_index is None:
            unmatched.append({"GamePk": game_pk, "reason": "play index missing"})
            continue

        lineup = list(lineup_at(game_records, play_index, is_top))
        current_slot = as_int(game_records[play_index]["lineup_slot"], 1) - 1
        current_slot = min(8, max(0, current_slot))
        hitter_id = batter_id or LEAGUE_PROFILE_ID
        lineup[current_slot] = hitter_id
        lineup_tuple = tuple(lineup)
        context_key = (lineup_tuple, current_slot)
        if context_key not in cache:
            cache[context_key] = simulate_context(
                lineup_tuple, current_slot, samplers, pools,
                args.simulations, rng, args.minimum_transition_cell,
            )
        stats = cache[context_key]
        v_success = stats["success"].mean
        v_failure = stats["failure"].mean
        v_no_steal = stats["no_steal"].mean
        v_if_out = stats["if_batter_out"].mean
        threshold, status = threshold_result(v_success, v_failure, v_no_steal)
        probabilities = samplers.get(hitter_id, samplers[LEAGUE_PROFILE_ID])[1]
        hit_probability = sum(probabilities[o] for o in ("1B", "2B", "3B", "HR"))
        xbh_probability = sum(probabilities[o] for o in ("2B", "3B", "HR"))
        out_probability = probabilities["OUT"]
        no_non_out, no_out_cost, no_expected_penalty = out_cost_metrics(v_no_steal, v_if_out, out_probability)
        success_non_out, success_out_cost, success_expected_penalty = out_cost_metrics(v_success, v_if_out, out_probability)

        model_rows.append({
            **decision,
            "HitterAcnt": hitter_id,
            "HitterLineup": current_slot + 1,
            "ProfilePA": profile_pa_by_id.get(hitter_id, 0),
            **{f"ModelP_{o}": probabilities[o] for o in OUTCOMES},
            "ModelP_HIT": hit_probability,
            "ModelP_XBH": xbh_probability,
            "ModelP_1BAmongHits": probabilities["1B"] / hit_probability if hit_probability else None,
            "ModelP_XBHAmongHits": xbh_probability / hit_probability if hit_probability else None,
            "ModelVSuccess": v_success,
            "ModelVSuccessSE": stats["success"].standard_error,
            "ModelVFailure": v_failure,
            "ModelVFailureSE": stats["failure"].standard_error,
            "ModelVNoSteal": v_no_steal,
            "ModelVNoStealSE": stats["no_steal"].standard_error,
            "ModelVIfBatterOut": v_if_out,
            "ModelVIfBatterOutSE": stats["if_batter_out"].standard_error,
            "RetentionValue": v_failure - v_if_out,
            "OutDamageNoSteal": v_no_steal - v_if_out,
            "OutDamageSuccess": v_success - v_if_out,
            "ModelVNoStealIfNonOut": no_non_out,
            "ConditionalOutCostNoSteal": no_out_cost,
            "ExpectedOutPenaltyNoSteal": no_expected_penalty,
            "ModelVSuccessIfNonOut": success_non_out,
            "ConditionalOutCostSuccess": success_out_cost,
            "ExpectedOutPenaltySuccess": success_expected_penalty,
            "SuccessMarginalVsNoSteal": v_success - v_no_steal,
            "BreakEvenSuccessRate": threshold,
            "ThresholdStatus": status,
            "Simulations": args.simulations,
        })
        if position % 100 == 0 or position == len(decisions):
            print(f"已完成 {position}/{len(decisions)} 筆；唯一打序情境 {len(cache)}")

    profile_path = args.output_dir / f"kbo_batter_profiles_{tag}.csv"
    model_path = args.output_dir / f"kbo_decision_model_{tag}.csv"
    summary_path = args.output_dir / f"kbo_decision_model_{tag}_summary.json"
    write_csv(profile_rows, profile_path)
    write_csv(model_rows, model_path)

    valid_thresholds = [
        float(row["BreakEvenSuccessRate"]) for row in model_rows
        if row["BreakEvenSuccessRate"] is not None and 0 <= float(row["BreakEvenSuccessRate"]) <= 1
    ]
    by_lineup: dict[str, dict[str, Any]] = {}
    for slot in range(1, 10):
        slot_rows = [row for row in model_rows if as_int(row["HitterLineup"]) == slot]
        if not slot_rows:
            continue
        thresholds = [
            float(row["BreakEvenSuccessRate"]) for row in slot_rows
            if row["BreakEvenSuccessRate"] is not None and 0 <= float(row["BreakEvenSuccessRate"]) <= 1
        ]
        by_lineup[str(slot)] = {
            "samples": len(slot_rows),
            "mean_v_success": sum(float(row["ModelVSuccess"]) for row in slot_rows) / len(slot_rows),
            "mean_v_failure": sum(float(row["ModelVFailure"]) for row in slot_rows) / len(slot_rows),
            "mean_v_no_steal": sum(float(row["ModelVNoSteal"]) for row in slot_rows) / len(slot_rows),
            "median_break_even_rate_in_0_1": median(thresholds) if thresholds else None,
        }

    summary = {
        "model_version": "kbo-batter-outcome-and-lineup-v1",
        "year": args.year,
        "games_with_raw_data": len(games),
        "completed_pa_for_profiles": len(records),
        "batter_profiles": len(profile_rows),
        "decision_samples_input": len(decisions),
        "decision_samples_modeled": len(model_rows),
        "unmatched": unmatched,
        "unique_lineup_contexts": len(cache),
        "simulations_per_context": args.simulations,
        "prior_pa": args.prior_pa,
        "minimum_transition_cell": args.minimum_transition_cell,
        "seed": args.seed,
        "mean_v_success": sum(float(r["ModelVSuccess"]) for r in model_rows) / len(model_rows),
        "mean_v_failure": sum(float(r["ModelVFailure"]) for r in model_rows) / len(model_rows),
        "mean_v_no_steal": sum(float(r["ModelVNoSteal"]) for r in model_rows) / len(model_rows),
        "mean_retention_value": sum(float(r["RetentionValue"]) for r in model_rows) / len(model_rows),
        "threshold_status_counts": dict(Counter(r["ThresholdStatus"] for r in model_rows)),
        "median_break_even_rate_in_0_1": median(valid_thresholds) if valid_thresholds else None,
        "direction_diagnostics": {
            "corr_p_1b_vs_success_marginal": correlation(
                [float(r["ModelP_1B"]) for r in model_rows],
                [float(r["SuccessMarginalVsNoSteal"]) for r in model_rows],
            ),
            "corr_p_hr_vs_success_marginal": correlation(
                [float(r["ModelP_HR"]) for r in model_rows],
                [float(r["SuccessMarginalVsNoSteal"]) for r in model_rows],
            ),
        },
        "by_hitter_lineup": by_lineup,
        "assumptions": [
            "不考慮個別跑者速度；壘包推進抽樣自聯盟整體相同 base-out state 與打席結果。",
            "三分支共同觀察至球隊下一個進攻半局結束。",
            "打者機率以聯盟分布作 prior-pa 強度的平滑。",
            "未模擬投手、捕手、比分、球場與比賽後段代打代跑。",
        ],
    }
    temp = summary_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(summary_path)
    print(f"打者檔：{profile_path}")
    print(f"決策模型：{model_path}")
    print(f"摘要：{summary_path}")
    return 0 if not unmatched else 1


if __name__ == "__main__":
    raise SystemExit(main())
