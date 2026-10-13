"""KBO 版 WPA 損益兩平門檻，做法同 model_wpa_decisions.py：用 WE 矩陣取代得分期望值。

共用 model_wpa_decisions.py 的 WE 查表、V失敗換算對手視角、V不跑一步蒙地卡羅；KBO 特有的只有打席資料
來源（kbo_model_batter_decisions.load_records_and_games）與決策當下分差（kbo_find_2out_first_base
已把 ScoreDiffAtState 寫進決策 CSV，數事件得到）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from build_win_expectancy_matrix import inning_bucket, score_diff_bucket
from model_batter_decisions import LEAGUE_PROFILE_ID, build_profiles, build_transition_pools, threshold_result
from model_wpa_decisions import (
    WinExpectancyTable,
    binomial_se,
    simulate_no_steal_wpa,
    win_value_after_half_ends,
)
from kbo_model_batter_decisions import as_int, load_records_and_games


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--re-model-csv", type=Path)
    parser.add_argument("--we-summary-json", type=Path,
                        default=Path("outputs/kbo_win_expectancy_matrix_2023-2026_R_combined_summary.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--simulations", type=int, default=4000)
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
    parser.add_argument("--min-we-n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260805)
    return parser.parse_args()


def valid_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) not in (None, "") and 0 <= float(r[key]) <= 1]


def main() -> int:
    args = parse_args()
    tag = args.year
    cache_dir = args.cache_dir or Path("data/raw/kbo") / tag
    decision_csv = args.decision_csv or Path("outputs") / f"kbo_2out_first_base_{tag}.csv"
    re_model_csv = args.re_model_csv or Path("outputs") / f"kbo_decision_model_{tag}.csv"
    if not decision_csv.exists():
        raise SystemExit(f"找不到決策樣本：{decision_csv}")
    if not args.we_summary_json.exists():
        raise SystemExit(f"找不到 WE 矩陣摘要：{args.we_summary_json}，請先執行 kbo_build_win_expectancy_matrix.py")
    we = WinExpectancyTable(json.loads(args.we_summary_json.read_text(encoding="utf-8-sig"))["cells"], args.min_we_n)

    records, games = load_records_and_games(cache_dir)
    samplers, _ = build_profiles(records, args.prior_pa)
    pools = build_transition_pools(records)

    with decision_csv.open(newline="", encoding="utf-8-sig") as file:
        decisions = list(csv.DictReader(file))

    re_thresholds: dict[tuple[str, str, str], float | None] = {}
    if re_model_csv.exists():
        with re_model_csv.open(newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                raw = row.get("BreakEvenSuccessRate")
                re_thresholds[(row["GamePk"], row["InningSeq"], row["IsTopInning"])] = (
                    float(raw) if raw not in (None, "") else None
                )
    else:
        print(f"提醒：找不到 {re_model_csv}，輸出不含 RE 版門檻對照欄位")

    rng = random.Random(args.seed)
    model_rows: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for position, decision in enumerate(decisions, 1):
        game_pk = str(decision["GamePk"])
        if game_pk not in games:
            unmatched.append({"GamePk": game_pk, "reason": "raw game missing"})
            continue
        inning = as_int(decision["InningSeq"])
        is_top = decision["IsTopInning"] == "True"
        batter_id = decision["BatterId"]
        diff = as_int(decision["ScoreDiffAtState"])
        batting_side = "1" if is_top else "2"
        hitter_id = batter_id or LEAGUE_PROFILE_ID

        try:
            v_success, n_success, fb_success = we.lookup(inning, batting_side, diff, 2, 2)
            v_failure, n_failure, fb_failure = win_value_after_half_ends(we, inning, batting_side, diff)
            v_no_steal, se_no_steal, fb_no_steal_share = simulate_no_steal_wpa(
                inning, batting_side, diff, hitter_id, we, samplers, pools,
                rng, args.minimum_transition_cell, args.simulations,
            )
        except KeyError as error:
            unmatched.append({"GamePk": game_pk, "reason": str(error)})
            continue

        threshold, status = threshold_result(v_success, v_failure, v_no_steal)
        re_threshold = re_thresholds.get((game_pk, decision["InningSeq"], decision["IsTopInning"]))
        model_rows.append({
            **decision,
            "HitterAcnt": hitter_id,
            "ScoreDiffAtState": diff,
            "InningBucket": inning_bucket(inning),
            "ScoreDiffBucket": score_diff_bucket(diff),
            "WE_VSuccess": round(v_success, 4),
            "WE_VSuccessSE": round(binomial_se(v_success, n_success), 4),
            "WE_VFailure": round(v_failure, 4),
            "WE_VFailureSE": round(binomial_se(v_failure, n_failure), 4),
            "WE_VNoSteal": round(v_no_steal, 4),
            "WE_VNoStealSE": round(se_no_steal, 4),
            "WE_Fallback_VSuccess": fb_success,
            "WE_Fallback_VFailure": fb_failure,
            "WE_Fallback_VNoStealShare": round(fb_no_steal_share, 4),
            "BreakEvenSuccessRate_WPA": threshold,
            "ThresholdStatus_WPA": status,
            "BreakEvenSuccessRate_RE": re_threshold,
            "Simulations": args.simulations,
        })
        if position % 500 == 0 or position == len(decisions):
            print(f"已完成 {position}/{len(decisions)} 筆")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"kbo_wpa_decision_model_{tag}.csv"
    if model_rows:
        with output_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(model_rows[0].keys()))
            writer.writeheader()
            writer.writerows(model_rows)

    by_inning: dict[str, dict[str, Any]] = {}
    for inning_number in range(1, 9):
        slot_rows = [r for r in model_rows if as_int(r.get("InningSeq")) == inning_number]
        if not slot_rows:
            continue
        wpa_values = valid_values(slot_rows, "BreakEvenSuccessRate_WPA")
        re_values = valid_values(slot_rows, "BreakEvenSuccessRate_RE")
        status_counts: dict[str, int] = defaultdict(int)
        for r in slot_rows:
            status_counts[r["ThresholdStatus_WPA"]] += 1
        by_inning[str(inning_number)] = {
            "samples": len(slot_rows),
            "wpa_status_counts": dict(status_counts),
            "median_threshold_wpa": round(median(wpa_values), 4) if wpa_values else None,
            "median_threshold_re": round(median(re_values), 4) if re_values else None,
            "median_diff_pp": (
                round((median(wpa_values) - median(re_values)) * 100, 2) if wpa_values and re_values else None
            ),
            "success_lookup_fallback_rate": round(
                sum(1 for r in slot_rows if r.get("WE_Fallback_VSuccess")) / len(slot_rows), 4),
            "failure_lookup_fallback_rate": round(
                sum(1 for r in slot_rows if r.get("WE_Fallback_VFailure")) / len(slot_rows), 4),
            "mean_no_steal_fallback_share": round(
                sum(float(r.get("WE_Fallback_VNoStealShare", 0)) for r in slot_rows) / len(slot_rows), 4),
        }

    overall_wpa = valid_values(model_rows, "BreakEvenSuccessRate_WPA")
    overall_re = valid_values(model_rows, "BreakEvenSuccessRate_RE")
    overall_status: dict[str, int] = defaultdict(int)
    for r in model_rows:
        overall_status[r["ThresholdStatus_WPA"]] += 1
    summary = {
        "year": args.year,
        "kind_code": "R",
        "game_sno_start": f"{args.year}-03",
        "game_sno_end": f"{args.year}-10",
        "decisions_total": len(decisions),
        "decisions_modeled": len(model_rows),
        "decisions_unmatched": len(unmatched),
        "unmatched_reasons": unmatched[:20],
        "min_we_n": args.min_we_n,
        "simulations_per_decision": args.simulations,
        "overall_median_threshold_wpa": round(median(overall_wpa), 4) if overall_wpa else None,
        "overall_median_threshold_re": round(median(overall_re), 4) if overall_re else None,
        "wpa_status_counts": dict(overall_status),
        "by_inning": by_inning,
    }
    summary_path = args.output_dir / f"kbo_wpa_decision_model_{tag}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{len(model_rows)}/{len(decisions)} 筆已建模（{len(unmatched)} 筆未匹配）")
    print(f"整體門檻中位數：WPA={summary['overall_median_threshold_wpa']}　RE={summary['overall_median_threshold_re']}")
    for inning_number in range(1, 9):
        s = by_inning.get(str(inning_number))
        if s:
            print(f"  第{inning_number}局：WPA={s['median_threshold_wpa']}　RE={s['median_threshold_re']}"
                  f"　差={s['median_diff_pp']}pp　(n={s['samples']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
