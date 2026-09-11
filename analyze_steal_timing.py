"""分析「兩出局、一壘有人」盜壘發動時機，檢驗兩個非互斥的假設：

1. 球數層次——原始假說是「教練偏好在兩好球（打者快被三振）時發動盜壘保護打
   者」，但逐格檢視後（見 README／簡報大綱）站不住：滿球數（2 好 3 壞）盜壘
   嘗試掛零（下一球必定保送或三振，跑者要嘛被迫上壘要嘛半局已結束，跑不跑沒
   有邊際效益），且 1 好 0 壞這種根本不到三振風險的球數嘗試率一樣偏高。改用
   「球數落後（好球數－壞球數，數值越大代表打者越落後）」這個更廣的假說重新
   檢驗：是不是只要打者球數落後，不分是不是快三振，盜壘嘗試率就偏高——並拆
   成各隊、供跨隊/跨年份比對，排除是單一隊戰術偏好把全聯盟平均拉高的可能。
2. 棒次層次——盜壘嘗試率是否隨當下打者棒次呈現「後段棒次較少盜壘」的樣態，
   對照 `analyze_retention_contribution.py` 算出的保留效應（第 6 棒起轉正、
   第 8 棒最嚴重），檢驗教練實際盜壘頻率是否已經隱含迴避保留效應代價，還是
   反過來在代價最高的棒次盜壘更兇。

兩者是各自獨立的行為佐證，不是同一件事的兩種互斥解釋。

只讀本機已快取的原始逐球 JSON（`data/raw/cpbl/{year}_{kind_code}/game_*.json`），
不重爬、也不需要 `find_2out_first_base.py` 的決策 CSV——直接用跟該腳本相同的
狀態/打席判定邏輯（`is_target_state`／`split_plate_appearances`／
`is_steal_success`／`is_steal_failure`）在原始列上重算，確保跟主管線口徑一致；
球隊名稱直接讀同一份快取 JSON 的 `GameDetailJson`（VisitingTeamName／
HomeTeamName），不依賴 step 1 的決策 CSV。

球數採「發動盜壘那一球投出前」的球數（沿用 `analyze_score_diff_steal_rate.py`
分差取前一列的同一慣例：事件列的 StrikeCnt/BallCnt 是該球投完後的累積值，
跑者實際上是看著「前一列」的球數決定要不要開跑）。分母是「這個球數（或球數
落後程度）出現過幾次投球機會」（同一情境下的所有球，不限是否發動盜壘），藉
此把「盜壘剛好常發生在某球數」跟「該球數本來就常見」分開。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from find_2out_first_base import (
    as_int,
    is_steal_failure,
    is_steal_success,
    is_target_state,
    side,
    split_plate_appearances,
)


def pre_pitch_count(rows: list[dict[str, Any]], pa_indices: list[int], index: int) -> tuple[int, int]:
    """回傳 rows[index] 這球投出前的球數；PA 內第一球視為 0 好 0 壞。"""
    if index > 0 and (index - 1) in pa_indices:
        prior = rows[index - 1]
        return as_int(prior.get("StrikeCnt")), as_int(prior.get("BallCnt"))
    return 0, 0


def count_diff_label(diff: int) -> str:
    if diff > 0:
        return f"落後{diff}"
    if diff < 0:
        return f"領先{-diff}"
    return "平球數"


def load_games_with_teams(
    cache_dir: Path,
) -> dict[int, tuple[list[dict[str, Any]], str, str]]:
    """跟 model_batter_decisions.load_raw_games 一樣過濾公告列，額外帶出隊名。"""
    from cpbl_row_filters import remove_administrative_rows

    games: dict[int, tuple[list[dict[str, Any]], str, str]] = {}
    for path in sorted(cache_dir.glob("game_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("LiveLogJson")
        rows = json.loads(raw) if isinstance(raw, str) and raw else []
        rows = remove_administrative_rows(rows)
        if not rows:
            continue
        detail = data.get("GameDetailJson")
        detail = json.loads(detail) if isinstance(detail, str) else detail
        detail_row = detail[0] if isinstance(detail, list) and detail else {}
        visiting_name = str(detail_row.get("VisitingTeamName") or "客隊")
        home_name = str(detail_row.get("HomeTeamName") or "主隊")
        game_sno = as_int(rows[0].get("GameSno"), as_int(path.stem.split("_")[-1]))
        games[game_sno] = (rows, visiting_name, home_name)
    return games


def analyze_game(
    rows: list[dict[str, Any]], visiting_name: str, home_name: str
) -> dict[str, Counter]:
    result = {
        "pitch_grid": Counter(),
        "attempt_grid": Counter(),
        "pitch_diff": Counter(),
        "attempt_diff": Counter(),
        "team_pitch_diff": Counter(),
        "team_attempt_diff": Counter(),
        "lineup_decisions": Counter(),
        "lineup_attempts": Counter(),
        "team_lineup_decisions": Counter(),
        "team_lineup_attempts": Counter(),
    }

    for pa_indices in split_plate_appearances(rows):
        target_indices = [index for index in pa_indices if is_target_state(rows[index])]
        if not target_indices:
            continue

        state_row = rows[target_indices[0]]
        lineup = as_int(state_row.get("HitterLineup"), -1)
        team = visiting_name if side(state_row) == "1" else home_name

        event_index: int | None = None
        outcome = "no_steal"
        for index in target_indices:
            content = str(rows[index].get("Content") or "")
            if is_steal_failure(content):
                event_index = index
                outcome = "steal_failure"
                break
            if is_steal_success(content):
                event_index = index
                outcome = "steal_success"
                break

        for index in target_indices:
            strike, ball = pre_pitch_count(rows, pa_indices, index)
            diff = strike - ball
            result["pitch_grid"][(strike, ball)] += 1
            result["pitch_diff"][diff] += 1
            result["team_pitch_diff"][(team, diff)] += 1

        result["lineup_decisions"][lineup] += 1
        result["team_lineup_decisions"][(team, lineup)] += 1

        if outcome in ("steal_success", "steal_failure") and event_index is not None:
            strike, ball = pre_pitch_count(rows, pa_indices, event_index)
            diff = strike - ball
            result["attempt_grid"][(strike, ball)] += 1
            result["attempt_diff"][diff] += 1
            result["team_attempt_diff"][(team, diff)] += 1
            result["lineup_attempts"][lineup] += 1
            result["team_lineup_attempts"][(team, lineup)] += 1

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"

    games = load_games_with_teams(cache_dir)

    totals = {
        "pitch_grid": Counter(),
        "attempt_grid": Counter(),
        "pitch_diff": Counter(),
        "attempt_diff": Counter(),
        "team_pitch_diff": Counter(),
        "team_attempt_diff": Counter(),
        "lineup_decisions": Counter(),
        "lineup_attempts": Counter(),
        "team_lineup_decisions": Counter(),
        "team_lineup_attempts": Counter(),
    }

    for rows, visiting_name, home_name in games.values():
        game_result = analyze_game(rows, visiting_name, home_name)
        for key, counter in game_result.items():
            totals[key].update(counter)

    total_decisions = sum(totals["lineup_decisions"].values())
    total_attempts = sum(totals["lineup_attempts"].values())
    print(f"\n{tag}：{total_decisions} 個決策機會、{total_attempts} 次盜壘嘗試計入分析\n")

    print("== 球數落後程度（好球數－壞球數）：全聯盟 ==")
    print(f"{'球數落後':>8} | {'投球機會':>8} | {'盜壘嘗試':>8} | {'每球盜壘率':>9}")
    diff_rows: list[dict[str, Any]] = []
    for diff in sorted(totals["pitch_diff"], reverse=True):
        pitches = totals["pitch_diff"][diff]
        attempts = totals["attempt_diff"].get(diff, 0)
        rate = attempts / pitches if pitches else 0.0
        print(f"{count_diff_label(diff):>8} | {pitches:>8} | {attempts:>8} | {rate:>8.2%}")
        diff_rows.append(
            {
                "CountDiff": diff,
                "Label": count_diff_label(diff),
                "PitchOpportunities": pitches,
                "StealAttempts": attempts,
                "AttemptRatePerPitch": rate,
            }
        )

    print("\n== 球數落後程度：逐隊拆解 ==")
    teams = sorted({team for team, _diff in totals["team_pitch_diff"]})
    team_diff_rows: list[dict[str, Any]] = []
    for team in teams:
        print(f"-- {team} --")
        print(f"{'球數落後':>8} | {'投球機會':>8} | {'盜壘嘗試':>8} | {'每球盜壘率':>9}")
        for diff in sorted(
            {d for (t, d) in totals["team_pitch_diff"] if t == team}, reverse=True
        ):
            pitches = totals["team_pitch_diff"][(team, diff)]
            attempts = totals["team_attempt_diff"].get((team, diff), 0)
            rate = attempts / pitches if pitches else 0.0
            print(f"{count_diff_label(diff):>8} | {pitches:>8} | {attempts:>8} | {rate:>8.2%}")
            team_diff_rows.append(
                {
                    "Team": team,
                    "CountDiff": diff,
                    "Label": count_diff_label(diff),
                    "PitchOpportunities": pitches,
                    "StealAttempts": attempts,
                    "AttemptRatePerPitch": rate,
                }
            )

    print("\n== 棒次層次：全聯盟 ==")
    print(f"{'棒次':>4} | {'決策機會':>8} | {'盜壘嘗試':>8} | {'嘗試率':>7}")
    lineup_rows: list[dict[str, Any]] = []
    for lineup in sorted(totals["lineup_decisions"]):
        decisions = totals["lineup_decisions"][lineup]
        attempts = totals["lineup_attempts"].get(lineup, 0)
        rate = attempts / decisions if decisions else 0.0
        print(f"{lineup:>4} | {decisions:>8} | {attempts:>8} | {rate:>6.1%}")
        lineup_rows.append(
            {
                "HitterLineup": lineup,
                "Decisions": decisions,
                "StealAttempts": attempts,
                "AttemptRate": rate,
            }
        )

    print("\n== 棒次層次：逐隊拆解（僅列決策機會 >= 15 的棒次）==")
    team_lineup_rows: list[dict[str, Any]] = []
    for team in teams:
        print(f"-- {team} --")
        print(f"{'棒次':>4} | {'決策機會':>8} | {'盜壘嘗試':>8} | {'嘗試率':>7}")
        for lineup in sorted(
            {l for (t, l) in totals["team_lineup_decisions"] if t == team}
        ):
            decisions = totals["team_lineup_decisions"][(team, lineup)]
            attempts = totals["team_lineup_attempts"].get((team, lineup), 0)
            rate = attempts / decisions if decisions else 0.0
            team_lineup_rows.append(
                {
                    "Team": team,
                    "HitterLineup": lineup,
                    "Decisions": decisions,
                    "StealAttempts": attempts,
                    "AttemptRate": rate,
                }
            )
            if decisions >= 15:
                print(f"{lineup:>4} | {decisions:>8} | {attempts:>8} | {rate:>6.1%}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        f"cpbl_steal_count_diff_{tag}.csv": diff_rows,
        f"cpbl_steal_count_diff_by_team_{tag}.csv": team_diff_rows,
        f"cpbl_steal_lineup_rate_{tag}.csv": lineup_rows,
        f"cpbl_steal_lineup_rate_by_team_{tag}.csv": team_lineup_rows,
    }
    for name, data_rows in outputs.items():
        path = args.output_dir / name
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(data_rows[0].keys()))
            writer.writeheader()
            writer.writerows(data_rows)
        print(f"\n明細已寫出：{path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
