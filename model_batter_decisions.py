"""以打者火力、出局率與打序保留效應模擬三種兩出局盜壘分支。

第一版刻意不估計個別跑者速度。打者使用個人 1B/2B/3B/HR/BB-HBP/
REACH/OUT 機率；壘包推進使用 2026 聯盟逐打席的經驗轉移分布。
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from find_2out_first_base import (
    as_int,
    batting_score,
    half_key,
    occupied,
    remove_administrative_rows,
    split_plate_appearances,
)


OUTCOMES = ("1B", "2B", "3B", "HR", "BB_HBP", "REACH", "OUT")
LEAGUE_PROFILE_ID = "__LEAGUE__"
RUNNER_EVENT_MARKERS = ("盜", "牽制", "暴投", "捕逸", "投手犯規")


@dataclass(frozen=True)
class Transition:
    runs: int
    outs_after: int
    bases_after: int


@dataclass
class PARecord:
    game_sno: int
    inning: int
    batting_side: str
    hitter_id: str
    hitter_name: str
    lineup_slot: int
    start_outs: int
    start_bases: int
    outcome: str
    transition: Transition
    has_runner_event: bool
    is_strikeout: bool


@dataclass
class BranchStats:
    mean: float
    standard_error: float


def bases_mask(row: dict[str, Any]) -> int:
    return (
        (1 if occupied(row.get("FirstBase")) else 0)
        | (2 if occupied(row.get("SecondBase")) else 0)
        | (4 if occupied(row.get("ThirdBase")) else 0)
    )


def classify_outcome(action_name: Any, batting_action_name: Any = "") -> str | None:
    """把 CPBL 的自由文字結果壓成模擬使用的互斥打席結果。"""
    action = str(action_name or "").strip()
    batting_action = str(batting_action_name or "").strip()
    if not action:
        return None  # 通常是盜壘刺結束半局，打席並未完成。
    if action.startswith("一壘安打"):
        return "1B"
    if action.startswith("二壘安打"):
        return "2B"
    if action.startswith("三壘安打"):
        return "3B"
    if "全壘打" in action or batting_action == "內全":
        return "HR"
    if any(
        marker in action
        for marker in ("四壞球", "故意四壞球", "裁定四壞球", "觸身死球", "妨礙打擊")
    ):
        return "BB_HBP"
    if any(
        marker in action
        for marker in (
            "失誤",
            "野手選擇",
            "趁傳",
            "不死三振",
            "雙殺打上壘",
            "犧牲短打上壘",
            "犧牲飛球上壘",
        )
    ):
        return "REACH"
    return "OUT"


def is_strikeout(action_name: Any) -> bool:
    """三振是「被判定三振」這個事件本身，跟後續是否出局無關。

    不死三振（捕手漏接、打者上壘）在 classify_outcome 仍歸類為 REACH（供壘包推進模型使用），
    但官方數據上打者仍記一次三振，這裡的 P_K 是獨立於 OUTCOMES 之外的輔助統計，
    因此不看 classify_outcome 的結果，只看文字是否含「三振」。
    """
    return "三振" in str(action_name or "")


def extract_pa_records(rows: list[dict[str, Any]]) -> list[PARecord]:
    records: list[PARecord] = []
    for indices in split_plate_appearances(rows):
        first_index = indices[0]
        last_index = indices[-1]
        first = rows[first_index]
        last = rows[last_index]
        outcome = classify_outcome(last.get("ActionName"), last.get("BattingActionName"))
        hitter_id = str(first.get("HitterAcnt") or "")
        if outcome is None or not hitter_id:
            continue

        inning, batting_side = half_key(first)
        start_outs = as_int(first.get("OutCnt"), -1)
        if not (0 <= start_outs <= 2):
            continue

        score_before = (
            batting_score(rows[first_index - 1], batting_side)
            if first_index > 0
            else 0
        )
        score_after = batting_score(last, batting_side)
        runs = max(0, score_after - score_before)

        next_index = last_index + 1
        if next_index < len(rows) and half_key(rows[next_index]) == (inning, batting_side):
            following = rows[next_index]
            outs_after = as_int(following.get("OutCnt"), start_outs)
            after_bases = bases_mask(following)
        else:
            # 正常第三出局或再見比賽都代表這個模擬半局在此終止。
            outs_after = 3
            after_bases = 0

        content = " ".join(str(rows[index].get("Content") or "") for index in indices)
        records.append(
            PARecord(
                game_sno=as_int(first.get("GameSno")),
                inning=inning,
                batting_side=batting_side,
                hitter_id=hitter_id,
                hitter_name=str(first.get("HitterName") or ""),
                lineup_slot=as_int(first.get("HitterLineup"), -1),
                start_outs=start_outs,
                start_bases=bases_mask(first),
                outcome=outcome,
                transition=Transition(runs, min(3, outs_after), after_bases),
                has_runner_event=any(marker in content for marker in RUNNER_EVENT_MARKERS),
                is_strikeout=is_strikeout(last.get("ActionName")),
            )
        )
    return records


def load_raw_games(cache_dir: Path) -> dict[int, list[dict[str, Any]]]:
    games: dict[int, list[dict[str, Any]]] = {}
    for path in sorted(cache_dir.glob("game_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("LiveLogJson")
        rows = json.loads(raw) if isinstance(raw, str) and raw else []
        rows = remove_administrative_rows(rows)
        if rows:
            game_sno = as_int(rows[0].get("GameSno"), as_int(path.stem.split("_")[-1]))
            games[game_sno] = rows
    return games


def build_profiles(
    records: Iterable[PARecord], prior_pa: float
) -> tuple[dict[str, tuple[list[float], dict[str, float]]], list[dict[str, Any]]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    strikeout_counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    league = Counter()
    league_strikeouts = 0
    for record in records:
        counts[record.hitter_id][record.outcome] += 1
        league[record.outcome] += 1
        names[record.hitter_id] = record.hitter_name
        if record.is_strikeout:
            strikeout_counts[record.hitter_id] += 1
            league_strikeouts += 1

    league_total = sum(league.values())
    if league_total == 0:
        raise RuntimeError("無法建立打者結果分布：沒有完成打席")
    league_prob = {outcome: league[outcome] / league_total for outcome in OUTCOMES}
    league_k_prob = league_strikeouts / league_total

    samplers: dict[str, tuple[list[float], dict[str, float]]] = {}
    profile_rows: list[dict[str, Any]] = []
    for hitter_id in sorted(counts):
        hitter_counts = counts[hitter_id]
        pa = sum(hitter_counts.values())
        probabilities = {
            outcome: (hitter_counts[outcome] + prior_pa * league_prob[outcome])
            / (pa + prior_pa)
            for outcome in OUTCOMES
        }
        cumulative: list[float] = []
        running = 0.0
        for outcome in OUTCOMES:
            running += probabilities[outcome]
            cumulative.append(running)
        cumulative[-1] = 1.0
        samplers[hitter_id] = (cumulative, probabilities)
        k_count = strikeout_counts.get(hitter_id, 0)
        profile_rows.append(
            {
                "HitterAcnt": hitter_id,
                "HitterName": names[hitter_id],
                "PA": pa,
                "PriorPA": prior_pa,
                **{f"Count_{outcome}": hitter_counts[outcome] for outcome in OUTCOMES},
                **{f"P_{outcome}": probabilities[outcome] for outcome in OUTCOMES},
                "P_HIT": sum(probabilities[outcome] for outcome in ("1B", "2B", "3B", "HR")),
                "P_XBH": sum(probabilities[outcome] for outcome in ("2B", "3B", "HR")),
                "Count_K": k_count,
                "P_K": (k_count + prior_pa * league_k_prob) / (pa + prior_pa),
            }
        )

    cumulative = []
    running = 0.0
    for outcome in OUTCOMES:
        running += league_prob[outcome]
        cumulative.append(running)
    cumulative[-1] = 1.0
    samplers[LEAGUE_PROFILE_ID] = (cumulative, league_prob)
    return samplers, profile_rows


def build_transition_pools(
    records: Iterable[PARecord], max_inning: int = 8
) -> dict[tuple[int, int, str], list[Transition]]:
    pools: dict[tuple[int, int, str], list[Transition]] = defaultdict(list)
    for record in records:
        if record.inning > max_inning or record.has_runner_event:
            continue
        transition = record.transition
        if transition.outs_after < record.start_outs or transition.runs < 0:
            continue
        pools[(record.start_outs, record.start_bases, record.outcome)].append(transition)
    return pools


def fallback_transition(outs: int, bases: int, outcome: str) -> Transition:
    """稀疏格沒有聯盟樣本時使用的保守棒球推進規則。"""
    first = bool(bases & 1)
    second = bool(bases & 2)
    third = bool(bases & 4)
    if outcome == "OUT":
        outs_after = min(3, outs + 1)
        return Transition(0, outs_after, 0 if outs_after == 3 else bases)
    if outcome == "HR":
        return Transition(1 + first + second + third, outs, 0)
    if outcome == "3B":
        return Transition(first + second + third, outs, 4)
    if outcome == "2B":
        return Transition(second + third, outs, 2 | (4 if first else 0))
    if outcome in ("1B", "REACH"):
        return Transition(1 if third else 0, outs, 1 | (2 if first else 0) | (4 if second else 0))
    if outcome == "BB_HBP":
        runs = 1 if first and second and third else 0
        after = 1
        if second or first:
            after |= 2
        if third or (first and second):
            after |= 4
        return Transition(runs, outs, after)
    raise ValueError(f"未知打席結果：{outcome}")


def sample_outcome(
    hitter_id: str,
    samplers: dict[str, tuple[list[float], dict[str, float]]],
    rng: random.Random,
) -> str:
    cumulative, _ = samplers.get(hitter_id, samplers[LEAGUE_PROFILE_ID])
    return OUTCOMES[bisect.bisect_left(cumulative, rng.random())]


def sample_transition(
    outs: int,
    bases: int,
    outcome: str,
    pools: dict[tuple[int, int, str], list[Transition]],
    rng: random.Random,
    minimum_cell: int,
) -> Transition:
    candidates = pools.get((outs, bases, outcome), [])
    if len(candidates) >= minimum_cell:
        return candidates[rng.randrange(len(candidates))]
    return fallback_transition(outs, bases, outcome)


def simulate_half(
    lineup: tuple[str, ...],
    start_slot: int,
    start_outs: int,
    start_bases: int,
    samplers: dict[str, tuple[list[float], dict[str, float]]],
    pools: dict[tuple[int, int, str], list[Transition]],
    rng: random.Random,
    minimum_cell: int,
    max_pa: int = 60,
) -> tuple[int, int]:
    outs = start_outs
    bases = start_bases
    slot = start_slot
    runs = 0
    for _ in range(max_pa):
        outcome = sample_outcome(lineup[slot], samplers, rng)
        transition = sample_transition(outs, bases, outcome, pools, rng, minimum_cell)
        runs += transition.runs
        outs = transition.outs_after
        bases = transition.bases_after
        slot = (slot + 1) % 9  # 所有建模結果都是完成打席；盜壘刺分支另行處理。
        if outs >= 3:
            return runs, slot
    # 極端長局截斷；60 PA 的機率可忽略，仍保留已產生分數避免整批失敗。
    return runs, slot


def branch_stats(values: list[int]) -> BranchStats:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return BranchStats(mean, 0.0)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return BranchStats(mean, math.sqrt(variance / len(values)))


def simulate_context(
    lineup: tuple[str, ...],
    current_slot: int,
    samplers: dict[str, tuple[list[float], dict[str, float]]],
    pools: dict[tuple[int, int, str], list[Transition]],
    simulations: int,
    rng: random.Random,
    minimum_cell: int,
) -> dict[str, BranchStats]:
    success_values: list[int] = []
    failure_values: list[int] = []
    no_steal_values: list[int] = []
    if_out_values: list[int] = []
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

        # 盜壘刺是跑者第三出局，當前打席沒有完成，因此下一局仍從 current_slot 開始。
        runs, _ = simulate_half(
            lineup, current_slot, 0, 0, samplers, pools, rng, minimum_cell
        )
        failure_values.append(runs)

        # 若當前打者出局，打席已消耗，下一局由下一棒開始。
        runs, _ = simulate_half(
            lineup, (current_slot + 1) % 9, 0, 0, samplers, pools, rng, minimum_cell
        )
        if_out_values.append(runs)

    return {
        "success": branch_stats(success_values),
        "failure": branch_stats(failure_values),
        "no_steal": branch_stats(no_steal_values),
        "if_batter_out": branch_stats(if_out_values),
    }


def find_state_index(rows: list[dict[str, Any]], decision: dict[str, str]) -> int | None:
    for index, row in enumerate(rows):
        if (
            as_int(row.get("InningSeq")) == as_int(decision.get("InningSeq"))
            and str(row.get("VisitingHomeType") or "")
            == str(decision.get("VisitingHomeType") or "")
            and as_int(row.get("BattingOrder"))
            == as_int(decision.get("BattingOrderInInning"))
            and as_int(row.get("PitchCnt")) == as_int(decision.get("StatePitchCnt"))
        ):
            return index
    return None


def lineup_at(
    rows: list[dict[str, Any]], state_index: int, batting_side: str
) -> tuple[str, ...]:
    lineup: list[str] = []
    for slot in range(1, 10):
        before = [
            (index, str(row.get("HitterAcnt") or ""))
            for index, row in enumerate(rows[: state_index + 1])
            if str(row.get("VisitingHomeType") or "") == batting_side
            and as_int(row.get("HitterLineup")) == slot
            and row.get("HitterAcnt")
        ]
        if before:
            lineup.append(before[-1][1])
            continue
        after = [
            str(row.get("HitterAcnt") or "")
            for row in rows[state_index + 1 :]
            if str(row.get("VisitingHomeType") or "") == batting_side
            and as_int(row.get("HitterLineup")) == slot
            and row.get("HitterAcnt")
        ]
        lineup.append(after[0] if after else LEAGUE_PROFILE_ID)
    return tuple(lineup)


def threshold_result(v_success: float, v_failure: float, v_no_steal: float) -> tuple[float | None, str]:
    denominator = v_success - v_failure
    if denominator <= 0:
        return None, "success_not_better_than_failure"
    threshold = (v_no_steal - v_failure) / denominator
    if threshold <= 0:
        return threshold, "steal_always_better"
    if threshold > 1:
        return threshold, "not_profitable_at_100pct"
    return threshold, "break_even_in_0_1"


def out_cost_metrics(
    branch_value: float, value_if_out: float, out_probability: float
) -> tuple[float | None, float | None, float | None]:
    """由全分支 EV 反推非出局 EV，並量化一次出局及其機率加權成本。"""
    if out_probability >= 1:
        return None, None, None
    value_if_non_out = (
        branch_value - out_probability * value_if_out
    ) / (1 - out_probability)
    conditional_cost = value_if_non_out - value_if_out
    expected_penalty = out_probability * conditional_cost
    return value_if_non_out, conditional_cost, expected_penalty


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise RuntimeError(f"{path} 沒有資料")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=240)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument(
        "--decision-csv",
        type=Path,
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--prior-pa", type=float, default=50.0)
    parser.add_argument("--minimum-transition-cell", type=int, default=5)
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
    if not decision_csv.exists():
        raise SystemExit(f"找不到決策樣本：{decision_csv}，請先執行 find_2out_first_base.py")

    games = load_raw_games(cache_dir)
    records = [record for rows in games.values() for record in extract_pa_records(rows)]
    samplers, profile_rows = build_profiles(records, args.prior_pa)
    profile_pa_by_id = {row["HitterAcnt"]: row["PA"] for row in profile_rows}
    pools = build_transition_pools(records)
    with decision_csv.open(newline="", encoding="utf-8-sig") as file:
        decisions = list(csv.DictReader(file))

    rng = random.Random(args.seed)
    cache: dict[tuple[tuple[str, ...], int], dict[str, BranchStats]] = {}
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
        lineup = list(lineup_at(rows, state_index, batting_side))
        current_slot = as_int(state.get("HitterLineup"), 1) - 1
        current_slot = min(8, max(0, current_slot))
        hitter_id = str(state.get("HitterAcnt") or LEAGUE_PROFILE_ID)
        lineup[current_slot] = hitter_id
        lineup_tuple = tuple(lineup)
        context_key = (lineup_tuple, current_slot)
        if context_key not in cache:
            cache[context_key] = simulate_context(
                lineup_tuple,
                current_slot,
                samplers,
                pools,
                args.simulations,
                rng,
                args.minimum_transition_cell,
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
        no_non_out, no_out_cost, no_expected_penalty = out_cost_metrics(
            v_no_steal, v_if_out, out_probability
        )
        success_non_out, success_out_cost, success_expected_penalty = out_cost_metrics(
            v_success, v_if_out, out_probability
        )

        model_rows.append(
            {
                **decision,
                "HitterAcnt": hitter_id,
                "ProfilePA": profile_pa_by_id.get(hitter_id, 0),
                **{f"ModelP_{outcome}": probabilities[outcome] for outcome in OUTCOMES},
                "ModelP_HIT": hit_probability,
                "ModelP_XBH": xbh_probability,
                "ModelP_1BAmongHits": probabilities["1B"] / hit_probability,
                "ModelP_XBHAmongHits": xbh_probability / hit_probability,
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
            }
        )
        if position % 100 == 0 or position == len(decisions):
            print(f"已完成 {position}/{len(decisions)} 筆；唯一打序情境 {len(cache)}")

    profile_path = args.output_dir / f"cpbl_batter_profiles_{tag}.csv"
    model_path = args.output_dir / f"cpbl_decision_model_{tag}.csv"
    summary_path = args.output_dir / f"cpbl_decision_model_{tag}_summary.json"
    write_csv(profile_rows, profile_path)
    write_csv(model_rows, model_path)

    valid_thresholds = [
        float(row["BreakEvenSuccessRate"])
        for row in model_rows
        if row["BreakEvenSuccessRate"] is not None
        and 0 <= float(row["BreakEvenSuccessRate"]) <= 1
    ]
    by_lineup: dict[str, dict[str, Any]] = {}
    for slot in range(1, 10):
        slot_rows = [row for row in model_rows if as_int(row["HitterLineup"]) == slot]
        if not slot_rows:
            continue
        thresholds = [
            float(row["BreakEvenSuccessRate"])
            for row in slot_rows
            if row["BreakEvenSuccessRate"] is not None
            and 0 <= float(row["BreakEvenSuccessRate"]) <= 1
        ]
        by_lineup[str(slot)] = {
            "samples": len(slot_rows),
            "mean_v_success": sum(float(row["ModelVSuccess"]) for row in slot_rows)
            / len(slot_rows),
            "mean_v_failure": sum(float(row["ModelVFailure"]) for row in slot_rows)
            / len(slot_rows),
            "mean_v_no_steal": sum(float(row["ModelVNoSteal"]) for row in slot_rows)
            / len(slot_rows),
            "median_break_even_rate_in_0_1": median(thresholds) if thresholds else None,
        }

    summary = {
        "model_version": "batter-outcome-and-lineup-v1",
        "year": args.year,
        "kind_code": args.kind_code,
        "game_sno_start": args.start,
        "game_sno_end": args.end,
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
        "mean_v_success": sum(float(row["ModelVSuccess"]) for row in model_rows)
        / len(model_rows),
        "mean_v_failure": sum(float(row["ModelVFailure"]) for row in model_rows)
        / len(model_rows),
        "mean_v_no_steal": sum(float(row["ModelVNoSteal"]) for row in model_rows)
        / len(model_rows),
        "mean_retention_value": sum(float(row["RetentionValue"]) for row in model_rows)
        / len(model_rows),
        "threshold_status_counts": dict(Counter(row["ThresholdStatus"] for row in model_rows)),
        "median_break_even_rate_in_0_1": median(valid_thresholds) if valid_thresholds else None,
        "direction_diagnostics": {
            "corr_p_1b_vs_success_marginal": correlation(
                [float(row["ModelP_1B"]) for row in model_rows],
                [float(row["SuccessMarginalVsNoSteal"]) for row in model_rows],
            ),
            "corr_p_hr_vs_success_marginal": correlation(
                [float(row["ModelP_HR"]) for row in model_rows],
                [float(row["SuccessMarginalVsNoSteal"]) for row in model_rows],
            ),
            "corr_xbh_share_of_hits_vs_success_marginal": correlation(
                [float(row["ModelP_XBHAmongHits"]) for row in model_rows],
                [float(row["SuccessMarginalVsNoSteal"]) for row in model_rows],
            ),
        },
        "by_hitter_lineup": by_lineup,
        "assumptions": [
            "不考慮個別跑者速度；壘包推進抽樣自聯盟整體相同 base-out state 與打席結果。",
            "三分支共同觀察至球隊下一個進攻半局結束。",
            "盜壘成功後忽略當下球數，使用打者整體結果機率。",
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
