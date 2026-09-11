"""用勝率矩陣（WE）取代得分期望值，算出每筆決策的 WPA 版損益兩平門檻。

對齊計畫書第 213 項待辦：第 7–8 局應改以勝率增加（WPA）而非得分期望值為
判準。`build_win_expectancy_matrix.py` 已經建好「狀態 → 進攻方最終獲勝機
率」的經驗查表；這裡把它接回 `model_batter_decisions.py` 的三分支架構。

跟 RE 版模型的關鍵差異：RE 版的「失敗」「不跑後出局」分支都只模擬「這支球
隊自己下一次進攻」的期望得分，完全不管對手怎麼打——這在比較「同一支球隊
兩種選擇何者得分較多」時沒問題，但勝率本質上一定要看對手，不能只看自己
這一隊。所以這裡改用 WE 矩陣本身當「一步之後的終局價值」：

- **V成功**：盜壘成功不影響比分、出局數不變，跑者直接站上二壘——這個狀態
  本身查表就是答案（`WE(局數,攻守方,分差,2出局,二壘)`），因為 WE 矩陣的
  每一格本來就是「從這個狀態到比賽結束」的經驗值，不需要再模擬下去。
- **V失敗**：跑者被封殺是第三出局，這個半局立刻結束、比分不變，換對手
  進攻——查對手視角的 WE 再取 `1 - 對方勝率`。
- **V不跑**：打者還要打完這個打席，結果不確定，所以這裡用
  `model_batter_decisions.py` 已經有的 `sample_outcome`／`sample_transition`
  （該打者個人機率分布＋聯盟壘包推進經驗分布）做「一步」蒙地卡羅：抽一次
  打席結果與推進結果，得到新狀態後再查 WE 表（出局或半局結束則同樣換算
  對手視角）。只需要模擬一步（不是模擬到比賽結束），因為 WE 表本身已經
  把「接下來會發生什麼」都積分進去了——這比 RE 版模擬整個半局＋下個半局
  便宜很多。

WE 矩陣格子數（2112 格）遠比實際觀測到的決策情境組合稀疏，目標情境裡約
三分之一格子 n < 20（見 `validate_win_expectancy_matrix.py`）。查表時若命
中格子樣本數不足，退而求其次用「忽略局數桶、只看攻守方/分差/出局/壘包」
的合併值（樣本數以千計，稀疏問題可忽略），並在輸出標記是否用了退化值。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import median, pstdev
from typing import Any

from build_win_expectancy_matrix import inning_bucket, score_diff_bucket
from find_2out_first_base import as_int
from model_batter_decisions import (
    LEAGUE_PROFILE_ID,
    build_profiles,
    build_transition_pools,
    extract_pa_records,
    find_state_index,
    load_raw_games,
    sample_outcome,
    sample_transition,
    threshold_result,
)
from analyze_score_diff_steal_rate import score_diff_at_state


def binomial_se(p: float, n: int) -> float:
    """勝率是二項比例，樣本數 n 已知時的標準誤——WE 表本身沒有存 SE，用這個回推。"""
    if n <= 0:
        return 0.0
    return math.sqrt(max(0.0, p * (1 - p)) / n)


class WinExpectancyTable:
    """狀態 -> 進攻方最終獲勝機率，樣本不足時退化成忽略局數桶的合併值。"""

    def __init__(self, cells: list[dict[str, Any]], min_n: int):
        self.min_n = min_n
        self.exact: dict[tuple[str, str, int, int, int], tuple[float, int]] = {}
        pooled_sum: dict[tuple[str, int, int, int], float] = defaultdict(float)
        pooled_n: dict[tuple[str, int, int, int], int] = defaultdict(int)
        for cell in cells:
            if cell["winRate"] is None:
                continue
            key = (
                cell["inningBucket"], cell["battingSide"], cell["scoreDiffBucket"],
                cell["outs"], cell["baseCode"],
            )
            self.exact[key] = (cell["winRate"], cell["n"])
            pooled_key = (cell["battingSide"], cell["scoreDiffBucket"], cell["outs"], cell["baseCode"])
            pooled_sum[pooled_key] += cell["winRate"] * cell["n"]
            pooled_n[pooled_key] += cell["n"]
        self.pooled = {key: total / pooled_n[key] for key, total in pooled_sum.items() if pooled_n[key] > 0}
        self.pooled_n = dict(pooled_n)

    def lookup(self, inning: int, side: str, diff: int, outs: int, base: int) -> tuple[float, int, bool]:
        """回傳 (勝率, 用來估這個勝率的樣本數, 是否用了退化值)。"""
        key = (inning_bucket(inning), side, score_diff_bucket(diff), outs, base)
        exact = self.exact.get(key)
        if exact is not None and exact[1] >= self.min_n:
            return exact[0], exact[1], False
        pooled_key = (side, score_diff_bucket(diff), outs, base)
        pooled = self.pooled.get(pooled_key)
        if pooled is not None:
            return pooled, self.pooled_n[pooled_key], True
        if exact is not None:
            return exact[0], exact[1], True
        raise KeyError(f"WE 矩陣沒有這個狀態的任何樣本：inning={inning} side={side} diff={diff} outs={outs} base={base}")


def advance_half(inning: int, batting_side: str) -> tuple[int, str]:
    """客隊進攻(1)結束後換主隊進攻同一局；主隊進攻(2)結束後換下一局客隊進攻。"""
    if batting_side == "1":
        return inning, "2"
    return inning + 1, "1"


def opponent_side(batting_side: str) -> str:
    return "2" if batting_side == "1" else "1"


def win_value_after_half_ends(
    we: WinExpectancyTable, inning: int, batting_side: str, diff: int
) -> tuple[float, int, bool]:
    next_inning, next_side = advance_half(inning, batting_side)
    opp_win, n, fallback = we.lookup(next_inning, next_side, -diff, 0, 0)
    # SE(1-p) = SE(p)，n 直接沿用對手那一格的樣本數。
    return 1.0 - opp_win, n, fallback


def simulate_no_steal_wpa(
    inning: int,
    batting_side: str,
    diff: int,
    hitter_id: str,
    we: WinExpectancyTable,
    samplers: dict[str, Any],
    pools: dict[tuple[int, int, str], list[Any]],
    rng: random.Random,
    minimum_cell: int,
    simulations: int,
) -> tuple[float, float, float]:
    """打者在 2 出局、一壘有人繼續打完這個打席，一步之後查 WE 表當終局價值。

    每次抽樣都拿該次查到的 WE 格子本身的二項標準誤加一次高斯雜訊
    （而不是直接用格子的點估計），讓最後算出來的樣本變異數同時涵蓋兩種
    不確定性來源：打者打席結果的抽樣，以及 WE 表本身每格的估計誤差
    （尤其是稀疏格子）——這樣輸出的標準誤才能直接餵給下游的 bootstrap
    信賴區間，不會漏掉 WE 表本身的雜訊。

    回傳 (平均勝率, 平均值的標準誤, 退化格佔抽樣次數比例)。
    """
    draws: list[float] = []
    fallback_count = 0
    for _ in range(simulations):
        outcome = sample_outcome(hitter_id, samplers, rng)
        transition = sample_transition(2, 1, outcome, pools, rng, minimum_cell)
        new_diff = diff + transition.runs
        if transition.outs_after >= 3:
            point, n, fallback = win_value_after_half_ends(we, inning, batting_side, new_diff)
        else:
            point, n, fallback = we.lookup(
                inning, batting_side, new_diff, transition.outs_after, transition.bases_after
            )
        se = binomial_se(point, n)
        draws.append(rng.gauss(point, se) if se > 0 else point)
        fallback_count += fallback
    mean = sum(draws) / simulations
    se_of_mean = (pstdev(draws) / math.sqrt(simulations)) if simulations > 1 else 0.0
    return mean, se_of_mean, fallback_count / simulations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path, help="預設讀 step 1 的決策 CSV")
    parser.add_argument("--re-model-csv", type=Path, help="預設讀 step 2 的 RE 版決策模型 CSV，用來對照")
    parser.add_argument(
        "--we-summary-json",
        type=Path,
        default=Path("outputs/cpbl_win_expectancy_matrix_2023-2026_A_combined_summary.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--simulations", type=int, default=4000, help="V不跑一步蒙地卡羅的抽樣次數")
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
    parser.add_argument("--min-we-n", type=int, default=20, help="WE 格子樣本數低於此值時退化成合併局數桶的值")
    parser.add_argument("--seed", type=int, default=20260805)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.simulations < 1 or args.prior_pa < 0 or args.minimum_transition_cell < 1:
        raise SystemExit("simulations/minimum-transition-cell 必須 >= 1，prior-pa 必須 >= 0")
    if args.start < 1 or args.end < args.start:
        raise SystemExit("場次範圍錯誤：需滿足 1 <= start <= end")
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    decision_csv = args.decision_csv or Path("outputs") / f"cpbl_2out_first_base_{tag}.csv"
    re_model_csv = args.re_model_csv or Path("outputs") / f"cpbl_decision_model_{tag}.csv"
    if not decision_csv.exists():
        raise SystemExit(f"找不到決策樣本：{decision_csv}，請先執行 find_2out_first_base.py")
    if not args.we_summary_json.exists():
        raise SystemExit(f"找不到 WE 矩陣摘要：{args.we_summary_json}，請先執行 build_win_expectancy_matrix.py")

    with args.we_summary_json.open("r", encoding="utf-8-sig") as handle:
        we_summary = json.load(handle)
    we = WinExpectancyTable(we_summary["cells"], args.min_we_n)

    games = load_raw_games(cache_dir)
    records = [record for rows in games.values() for record in extract_pa_records(rows)]
    samplers, _ = build_profiles(records, args.prior_pa)
    pools = build_transition_pools(records)

    with decision_csv.open(newline="", encoding="utf-8-sig") as file:
        decisions = list(csv.DictReader(file))

    re_thresholds: dict[tuple[int, int], float | None] = {}
    if re_model_csv.exists():
        with re_model_csv.open(newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                key = (as_int(row.get("GameSno")), as_int(row.get("StateRowIndex")))
                raw = row.get("BreakEvenSuccessRate")
                re_thresholds[key] = float(raw) if raw not in (None, "") else None
    else:
        print(f"提醒：找不到 {re_model_csv}，輸出將不含 RE 版門檻對照欄位（先跑 model_batter_decisions.py 可補上）")

    rng = random.Random(args.seed)
    model_rows: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for position, decision in enumerate(decisions, 1):
        game_sno = as_int(decision.get("GameSno"))
        rows = games.get(game_sno)
        if not rows:
            unmatched.append({"GameSno": game_sno, "reason": "raw game missing"})
            continue
        state_index = find_state_index(rows, decision)
        if state_index is None:
            unmatched.append({"GameSno": game_sno, "reason": "state row missing"})
            continue
        state = rows[state_index]
        batting_side = str(state.get("VisitingHomeType") or "")
        inning = as_int(state.get("InningSeq"))
        hitter_id = str(state.get("HitterAcnt") or LEAGUE_PROFILE_ID)
        diff = score_diff_at_state(rows, state_index, batting_side)
        if diff is None:
            unmatched.append({"GameSno": game_sno, "reason": "score diff unavailable"})
            continue

        try:
            v_success, n_success, fb_success = we.lookup(inning, batting_side, diff, 2, 2)
            v_failure, n_failure, fb_failure = win_value_after_half_ends(we, inning, batting_side, diff)
            v_no_steal, se_no_steal, fb_no_steal_share = simulate_no_steal_wpa(
                inning, batting_side, diff, hitter_id, we, samplers, pools,
                rng, args.minimum_transition_cell, args.simulations,
            )
        except KeyError as error:
            unmatched.append({"GameSno": game_sno, "reason": str(error)})
            continue

        threshold, status = threshold_result(v_success, v_failure, v_no_steal)
        re_threshold = re_thresholds.get((game_sno, as_int(decision.get("StateRowIndex"))))

        model_rows.append(
            {
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
            }
        )
        if position % 200 == 0 or position == len(decisions):
            print(f"已完成 {position}/{len(decisions)} 筆")

    output_path = args.output_dir / f"cpbl_wpa_decision_model_{tag}.csv"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if model_rows:
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(model_rows[0].keys()))
            writer.writeheader()
            writer.writerows(model_rows)
        temp_path.replace(output_path)

    def valid_thresholds(rows: list[dict[str, Any]], key: str) -> list[float]:
        return [
            float(row[key]) for row in rows
            if row.get(key) is not None and 0 <= float(row[key]) <= 1
        ]

    by_inning: dict[str, dict[str, Any]] = {}
    for inning_number in range(1, 9):
        slot_rows = [row for row in model_rows if as_int(row.get("InningSeq")) == inning_number]
        if not slot_rows:
            continue
        wpa_values = valid_thresholds(slot_rows, "BreakEvenSuccessRate_WPA")
        re_values = valid_thresholds(slot_rows, "BreakEvenSuccessRate_RE")
        slot_status_counts: dict[str, int] = defaultdict(int)
        for row in slot_rows:
            slot_status_counts[row["ThresholdStatus_WPA"]] += 1
        by_inning[str(inning_number)] = {
            "samples": len(slot_rows),
            "wpa_status_counts": dict(slot_status_counts),
            "median_threshold_wpa": round(median(wpa_values), 4) if wpa_values else None,
            "median_threshold_re": round(median(re_values), 4) if re_values else None,
            "median_diff_pp": (
                round((median(wpa_values) - median(re_values)) * 100, 2)
                if wpa_values and re_values else None
            ),
            "success_lookup_fallback_rate": round(
                sum(1 for row in slot_rows if row.get("WE_Fallback_VSuccess")) / len(slot_rows), 4
            ),
            "failure_lookup_fallback_rate": round(
                sum(1 for row in slot_rows if row.get("WE_Fallback_VFailure")) / len(slot_rows), 4
            ),
            "mean_no_steal_fallback_share": round(
                sum(float(row.get("WE_Fallback_VNoStealShare", 0)) for row in slot_rows) / len(slot_rows), 4
            ),
        }

    overall_wpa = valid_thresholds(model_rows, "BreakEvenSuccessRate_WPA")
    overall_re = valid_thresholds(model_rows, "BreakEvenSuccessRate_RE")
    status_counts: dict[str, int] = defaultdict(int)
    for row in model_rows:
        status_counts[row["ThresholdStatus_WPA"]] += 1
    summary = {
        "year": args.year,
        "kind_code": args.kind_code,
        "game_sno_start": args.start,
        "game_sno_end": args.end,
        "decisions_total": len(decisions),
        "decisions_modeled": len(model_rows),
        "decisions_unmatched": len(unmatched),
        "unmatched_reasons": unmatched[:20],
        "min_we_n": args.min_we_n,
        "simulations_per_decision": args.simulations,
        "overall_median_threshold_wpa": round(median(overall_wpa), 4) if overall_wpa else None,
        "overall_median_threshold_re": round(median(overall_re), 4) if overall_re else None,
        "wpa_status_counts": dict(status_counts),
        "by_inning": by_inning,
    }
    summary_path = args.output_dir / f"cpbl_wpa_decision_model_{tag}_summary.json"
    temp_summary = summary_path.with_suffix(".json.tmp")
    temp_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_summary.replace(summary_path)

    print(f"完成：{len(model_rows)}/{len(decisions)} 筆決策已建模（{len(unmatched)} 筆未匹配）")
    print(f"CSV：{output_path}")
    print(f"摘要：{summary_path}")
    print(f"整體門檻中位數：WPA={summary['overall_median_threshold_wpa']}　RE={summary['overall_median_threshold_re']}")
    print("逐局門檻中位數（WPA vs RE，pp 差）：")
    for inning_number in range(1, 9):
        stats = by_inning.get(str(inning_number))
        if not stats:
            continue
        print(
            f"  第{inning_number}局：WPA={stats['median_threshold_wpa']}　RE={stats['median_threshold_re']}"
            f"　差={stats['median_diff_pp']}pp　(n={stats['samples']}，"
            f"V成功退化={stats['success_lookup_fallback_rate']}　V失敗退化={stats['failure_lookup_fallback_rate']}"
            f"　V不跑平均退化比例={stats['mean_no_steal_fallback_share']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
