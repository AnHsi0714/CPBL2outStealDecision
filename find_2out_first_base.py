"""抓取並整理 2026 CPBL「兩出局、僅一壘有人」決策樣本。

預設抓例行賽 GameSno 1–240。原始 getlive 回應逐場快取，因此中斷後可以續跑，
也能在不重新請求官網的情況下反覆修正分析邏輯。
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import CPBL_steal_getData
from cpbl_row_filters import is_administrative_only_row, remove_administrative_rows  # noqa: F401 (re-exported)


DEFAULT_YEAR = 2026
DEFAULT_KIND_CODE = "A"
DEFAULT_START = 1
DEFAULT_END = 240


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def occupied(value: Any) -> bool:
    """CPBL 空壘可能是空字串、None、0；有人時通常是局內打者序號字串。"""
    return value not in (None, "", 0, "0", False)


def side(row: dict[str, Any]) -> str:
    return str(row.get("VisitingHomeType") or "")


def half_key(row: dict[str, Any]) -> tuple[int, str]:
    return as_int(row.get("InningSeq")), side(row)


def batting_score(row: dict[str, Any], batting_side: str | None = None) -> int:
    batting_side = batting_side or side(row)
    # CPBL getlive 實際值：1=客隊打擊、2=主隊打擊。
    field = "VisitingScore" if batting_side == "1" else "HomeScore"
    return as_int(row.get(field))


def is_target_state(row: dict[str, Any]) -> bool:
    inning = as_int(row.get("InningSeq"))
    return (
        1 <= inning <= 8
        and as_int(row.get("OutCnt"), -1) == 2
        and occupied(row.get("FirstBase"))
        and not occupied(row.get("SecondBase"))
        and not occupied(row.get("ThirdBase"))
    )


def is_steal_success(content: str) -> bool:
    return (
        "一壘跑者" in content
        and "盜壘" in content
        and "上二壘" in content
        and "雙盜壘" not in content
        and "盜壘刺" not in content
    )


def is_steal_failure(content: str) -> bool:
    return "一壘跑者" in content and "盜壘刺" in content and "出局" in content


def pa_key(row: dict[str, Any]) -> tuple[int, str, int]:
    """BattingOrder 是該半局第幾名打者，可作為半局內打席鍵。"""
    inning, batting_side = half_key(row)
    return inning, batting_side, as_int(row.get("BattingOrder"), -1)


def split_plate_appearances(rows: list[dict[str, Any]]) -> Iterable[list[int]]:
    """回傳連續打席所對應的全場 row index。"""
    if not rows:
        return
    start = 0
    current = pa_key(rows[0])
    for index in range(1, len(rows)):
        key = pa_key(rows[index])
        if key != current:
            yield list(range(start, index))
            start = index
            current = key
    yield list(range(start, len(rows)))


def half_is_complete(
    key: tuple[int, str],
    half_indices: dict[tuple[int, str], list[int]],
    rows: list[dict[str, Any]],
) -> bool:
    indices = half_indices.get(key, [])
    if not indices:
        return False
    last_index = indices[-1]
    # 只要後面還有另一個半局，此半局一定已結束。這也比只依賴自由文字穩定。
    if last_index < len(rows) - 1 and half_key(rows[last_index + 1]) != key:
        return True
    content = str(rows[last_index].get("Content") or "")
    return any(
        marker in content
        for marker in ("3人出局", "3 人出局", "三人出局", "比賽結束")
    )


def event_transition_matches(
    rows: list[dict[str, Any]], event_index: int, outcome: str
) -> bool | None:
    """以事件後一列的壘包／半局變化交叉驗證自由文字。"""
    if event_index + 1 >= len(rows):
        return None
    current = rows[event_index]
    following = rows[event_index + 1]
    if outcome == "steal_success":
        if half_key(following) != half_key(current):
            return False
        # 下一球一壘可能因同一球是四壞而已有新跑者，不能要求一壘必為空；
        # 用原一壘跑者的局內序號是否移到二壘驗證最可靠。
        runner = str(current.get("FirstBase") or "")
        if runner in {
            str(following.get("SecondBase") or ""),
            str(following.get("ThirdBase") or ""),
        }:
            return True
        # 少數紀錄是盜二壘成功後，同一 play 因傳球失誤直接回本壘。
        content = str(current.get("Content") or "")
        return "二壘跑者" in content and "回本壘得分" in content
    if outcome == "steal_failure":
        return half_key(following) != half_key(current)
    return None


def post_steal_base(rows: list[dict[str, Any]], event_index: int) -> str | None:
    """成功盜二壘後可能因傳球失誤同一 play 再上三壘。"""
    if event_index + 1 >= len(rows):
        return None
    current = rows[event_index]
    following = rows[event_index + 1]
    if half_key(following) != half_key(current):
        return None
    runner = str(current.get("FirstBase") or "")
    if str(following.get("SecondBase") or "") == runner:
        return "second"
    if str(following.get("ThirdBase") or "") == runner:
        return "third"
    content = str(current.get("Content") or "")
    if "二壘跑者" in content and "回本壘得分" in content:
        return "home"
    return "unknown"


def analyze_game(game_meta: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    """將單場 getlive 回應轉成一列一個決策機會。"""
    raw = data.get("LiveLogJson")
    if not raw:
        return []
    rows: list[dict[str, Any]] = json.loads(raw) if isinstance(raw, str) else raw
    if not rows:
        return []
    rows = remove_administrative_rows(rows)

    half_indices: dict[tuple[int, str], list[int]] = {}
    for index, row in enumerate(rows):
        half_indices.setdefault(half_key(row), []).append(index)

    half_end_scores = {
        key: max(batting_score(rows[index], key[1]) for index in indices)
        for key, indices in half_indices.items()
    }

    game_date = str(game_meta.get("GameDate") or "")[:10]
    results: list[dict[str, Any]] = []

    for pa_indices in split_plate_appearances(rows):
        target_indices = [index for index in pa_indices if is_target_state(rows[index])]
        if not target_indices:
            continue

        state_index = target_indices[0]
        state_row = rows[state_index]
        inning, batting_side = half_key(state_row)
        current_key = (inning, batting_side)
        next_key = (inning + 1, batting_side)

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

        current_end_score = half_end_scores[current_key]
        # 列上的壘包／出局是事件前狀態，但比分可能已反映該列事件；因此狀態剛形成
        # 時的基準分數取前一列。兩出局狀態不可能是全場第一列。
        before_state_score = (
            batting_score(rows[state_index - 1], batting_side)
            if state_index > 0
            else batting_score(state_row, batting_side)
        )
        current_from_state = current_end_score - before_state_score

        current_after_decision: int | None
        transition_ok: bool | None = None
        if outcome == "steal_success" and event_index is not None:
            # 成功盜壘的事件列比分已即時更新；從該列之後算到半局結束。
            current_after_decision = current_end_score - batting_score(
                rows[event_index], batting_side
            )
            transition_ok = event_transition_matches(rows, event_index, outcome)
        elif outcome == "steal_failure" and event_index is not None:
            current_after_decision = 0
            transition_ok = event_transition_matches(rows, event_index, outcome)
        else:
            # 不跑的決策起點就是兩出局、僅一壘有人狀態形成時。
            current_after_decision = current_from_state

        next_indices = half_indices.get(next_key, [])
        next_complete = half_is_complete(next_key, half_indices, rows) if next_indices else False
        next_half_runs: int | None = None
        next_leadoff_lineup: Any = None
        next_leadoff_name: Any = None
        if next_indices:
            next_first = rows[next_indices[0]]
            next_leadoff_lineup = next_first.get("HitterLineup")
            next_leadoff_name = next_first.get("HitterName")
            if next_complete:
                # 同隊守備時分數不會變，所以下一半局得分＝下一半局結束累積分
                # 減目前半局結束累積分。可涵蓋下一局第一球就得分的情況。
                next_half_runs = half_end_scores[next_key] - current_end_score

        hitter_lineup = state_row.get("HitterLineup")
        retention_matches: bool | None = None
        if outcome == "steal_failure" and next_leadoff_lineup is not None:
            retention_matches = str(hitter_lineup) == str(next_leadoff_lineup)

        requested_re = (
            current_after_decision if outcome == "steal_success" else next_half_runs
        )
        requested_definition = (
            "盜壘成功事件後至當半局結束的剩餘得分"
            if outcome == "steal_success"
            else "同隊下一個半局的得分"
        )

        final_pa_row = rows[pa_indices[-1]]
        event_row = rows[event_index] if event_index is not None else None
        results.append(
            {
                "Year": as_int(game_meta.get("Year"), DEFAULT_YEAR),
                "KindCode": game_meta.get("KindCode", DEFAULT_KIND_CODE),
                "GameSno": as_int(game_meta.get("GameSno")),
                "GameDate": game_date,
                "VisitingTeam": game_meta.get("VisitingTeamName"),
                "HomeTeam": game_meta.get("HomeTeamName"),
                "InningSeq": inning,
                "VisitingHomeType": batting_side,
                "BattingTeam": (
                    game_meta.get("VisitingTeamName")
                    if batting_side == "1"
                    else game_meta.get("HomeTeamName")
                ),
                "BattingOrderInInning": state_row.get("BattingOrder"),
                "HitterLineup": hitter_lineup,
                "HitterAcnt": state_row.get("HitterAcnt"),
                "HitterName": state_row.get("HitterName"),
                "PitcherName": state_row.get("PitcherName"),
                "RunnerOnFirst": state_row.get("FirstBase"),
                "StatePitchCnt": state_row.get("PitchCnt"),
                "StateRowIndex": state_index,
                "EventPitchCnt": event_row.get("PitchCnt") if event_row else None,
                "EventRowIndex": event_index,
                "Outcome": outcome,
                "RequestedRE": requested_re,
                "RequestedREDefinition": requested_definition,
                "CurrentHalfRemainingRunsFromState": current_from_state,
                "CurrentHalfRemainingRunsAfterDecision": current_after_decision,
                "NextHalfRuns": next_half_runs,
                "TwoHalfRunsAfterDecision": (
                    current_after_decision + next_half_runs
                    if current_after_decision is not None and next_half_runs is not None
                    else None
                ),
                "CurrentHalfComplete": half_is_complete(current_key, half_indices, rows),
                "NextHalfExists": bool(next_indices),
                "NextHalfComplete": next_complete,
                "NextHalfLeadoffLineup": next_leadoff_lineup,
                "NextHalfLeadoffName": next_leadoff_name,
                "RetentionMatches": retention_matches,
                "EventTransitionMatches": transition_ok,
                "PostStealBase": (
                    post_steal_base(rows, event_index)
                    if outcome == "steal_success" and event_index is not None
                    else None
                ),
                "FinalPAActionName": final_pa_row.get("ActionName"),
                "EventContent": event_row.get("Content") if event_row else "",
            }
        )

    return results


def load_or_fetch_game(
    game_meta: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
    retries: int,
) -> tuple[dict[str, Any], bool]:
    """回傳 (getlive 資料, 是否真的向官網發出請求)。"""
    game_sno = as_int(game_meta.get("GameSno"))
    cache_file = cache_dir / f"game_{game_sno:04d}.json"
    if cache_file.exists() and not refresh:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if live_log_count(cached) > 0:
            return cached, False
        # 延期或未開打場次可能 Success=True 但逐球陣列為空；不可視為已完成快取。

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            month = as_int(str(game_meta.get("GameDate"))[5:7])
            data = CPBL_steal_getData.get_live_data(
                as_int(game_meta.get("Year"), DEFAULT_YEAR),
                str(game_meta.get("KindCode") or DEFAULT_KIND_CODE),
                game_sno,
                month,
            )
            if not data.get("Success"):
                raise RuntimeError("getlive API 回傳 Success=False")
            if live_log_count(data) == 0:
                raise RuntimeError("getlive API 沒有逐球資料（可能延期、未賽或官網尚未補齊）")
            cache_dir.mkdir(parents=True, exist_ok=True)
            temp_file = cache_file.with_suffix(".json.tmp")
            temp_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_file.replace(cache_file)
            return data, True
        except Exception as error:  # 網站短暫失敗需要重試並保留最後錯誤
            last_error = error
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"GameSno={game_sno} 抓取失敗：{last_error}") from last_error


def live_log_count(data: dict[str, Any]) -> int:
    raw = data.get("LiveLogJson")
    if not raw:
        return 0
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return 0
    return len(rows) if isinstance(rows, list) else 0


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError("沒有符合條件的樣本，不寫出空 CSV")
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def write_summary(
    path: Path,
    args: argparse.Namespace,
    games_expected: int,
    games_processed: int,
    failures: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    counts = Counter(str(row["Outcome"]) for row in rows)

    def re_is_missing(row: dict[str, Any]) -> bool:
        return row["RequestedRE"] is None or row["RequestedRE"] == ""

    re_by_outcome: dict[str, dict[str, Any]] = {}
    for outcome in sorted(counts):
        outcome_rows = [row for row in rows if row["Outcome"] == outcome]
        values = [
            as_int(row["RequestedRE"])
            for row in outcome_rows
            if row["RequestedRE"] is not None and row["RequestedRE"] != ""
        ]
        re_by_outcome[outcome] = {
            "samples_total": len(outcome_rows),
            "samples_with_re": len(values),
            "samples_missing_re": len(outcome_rows) - len(values),
            "mean_requested_re": sum(values) / len(values) if values else None,
            "run_distribution": dict(sorted(Counter(values).items())),
        }

    summary = {
        "year": args.year,
        "kind_code": args.kind_code,
        "game_sno_start": args.start,
        "game_sno_end": args.end,
        "games_expected": games_expected,
        "games_processed": games_processed,
        "games_failed": len(failures),
        "failures": failures,
        "decision_samples": len(rows),
        "outcome_counts": dict(sorted(counts.items())),
        "requested_re_by_outcome": re_by_outcome,
        "missing_requested_re": sum(re_is_missing(row) for row in rows),
        "missing_requested_re_reasons": {
            "no_next_half": sum(
                re_is_missing(row)
                and row["NextHalfExists"] in (False, "False", "", None)
                for row in rows
            ),
            "next_half_incomplete": sum(
                re_is_missing(row)
                and row["NextHalfExists"] in (True, "True")
                and row["NextHalfComplete"] in (False, "False", "", None)
                for row in rows
            ),
        },
        "post_steal_base_counts": dict(
            sorted(
                Counter(
                    str(row["PostStealBase"])
                    for row in rows
                    if row["Outcome"] == "steal_success"
                ).items()
            )
        ),
        "steal_transition_mismatches": sum(
            row["EventTransitionMatches"] is False for row in rows
        ),
        "failed_steal_retention_mismatches": sum(
            row["RetentionMatches"] is False for row in rows
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(path)


def deduplicate_schedule(games: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """延期場次會以相同 GameSno 留下舊列；選擇官網標記為目前版本的列。"""

    def priority(game: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            as_int(game.get("PresentStatus")),
            1 if str(game.get("GameResult")) == "0" else 0,
            1 if game.get("GameDateTimeE") else 0,
            str(game.get("GameDateTimeS") or game.get("GameDate") or ""),
        )

    selected: dict[int, dict[str, Any]] = {}
    for game in games:
        game_sno = as_int(game.get("GameSno"), -1)
        previous = selected.get(game_sno)
        if previous is None or priority(game) > priority(previous):
            selected[game_sno] = game
    return [selected[game_sno] for game_sno in sorted(selected)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--kind-code", default=DEFAULT_KIND_CODE)
    parser.add_argument("--start", type=int, default=DEFAULT_START)
    parser.add_argument("--end", type=int, default=DEFAULT_END)
    parser.add_argument("--delay", type=float, default=2.0, help="每次成功請求後至少等待秒數")
    parser.add_argument("--jitter", type=float, default=1.5, help="額外隨機等待秒數上限")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true", help="忽略快取並重新抓取")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/cpbl"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start < 1 or args.end < args.start:
        raise SystemExit("場次範圍錯誤：需滿足 1 <= start <= end")

    schedule = CPBL_steal_getData.get_schedule(args.year, args.kind_code)
    games = deduplicate_schedule(
        game
        for game in schedule
        if args.start <= as_int(game.get("GameSno")) <= args.end
    )
    expected = args.end - args.start + 1
    found_numbers = {as_int(game.get("GameSno")) for game in games}
    missing_schedule = sorted(set(range(args.start, args.end + 1)) - found_numbers)
    if missing_schedule:
        print(f"警告：賽程缺少 {len(missing_schedule)} 個 GameSno：{missing_schedule}")
    print(f"賽程找到 {len(games)}/{expected} 場，開始抓取；已有快取的場次不等待。")

    cache_dir = args.cache_dir / f"{args.year}_{args.kind_code}"
    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    processed = 0

    for position, game in enumerate(games, 1):
        game_sno = as_int(game.get("GameSno"))
        label = f"[{position}/{len(games)}] GameSno={game_sno}"
        try:
            data, fetched = load_or_fetch_game(
                game, cache_dir, args.refresh, max(1, args.retries)
            )
            samples = analyze_game(game, data)
            all_rows.extend(samples)
            processed += 1
            source = "官網" if fetched else "快取"
            print(f"{label}：{source}，符合 {len(samples)} 筆")
            if fetched and position < len(games):
                time.sleep(max(0.0, args.delay) + random.uniform(0, max(0.0, args.jitter)))
        except Exception as error:
            print(f"{label}：失敗：{error}")
            failures.append({"GameSno": game_sno, "error": str(error)})

    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    csv_path = args.output_dir / f"cpbl_2out_first_base_{tag}.csv"
    summary_path = args.output_dir / f"cpbl_2out_first_base_{tag}_summary.json"
    write_csv(all_rows, csv_path)
    write_summary(summary_path, args, len(games), processed, failures, all_rows)

    print(f"完成：{processed}/{len(games)} 場，{len(all_rows)} 筆決策樣本")
    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    if failures:
        print("仍有失敗場次；重跑同一指令會沿用成功場次快取並重試失敗場次。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
