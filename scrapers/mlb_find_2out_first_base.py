"""抓取並整理 MLB「兩出局、僅一壘有人」決策樣本，欄位對齊 find_2out_first_base.py（CPBL 版）。

資料來源是官方 Gumbo 逐局 API（feed/live），不是 Baseball Savant 的 /gf：/gf 沒有逐打席累積
比分欄位，RE 計算需要的「事件當下比分」只有 Gumbo 有。Gumbo 的 playEvents 沒有直接給壘包
狀態，是從每個 play 的 runners[] 移動紀錄（含打者自己）逐一重建的，細節見 build_event_stream。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

import MLB_steal_getData

DEFAULT_START_DATE = "2025-04-01"
DEFAULT_END_DATE = "2025-04-07"

STEAL_EVENT_NAMES = ("Stolen Base", "Caught Stealing")


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def half_key(play: dict[str, Any]) -> tuple[int, bool]:
    about = play.get("about", {})
    return as_int(about.get("inning")), bool(about.get("isTopInning"))


def build_event_stream(half_plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把一個半局的 plays 拆成逐事件清單，每個事件對應一次會改變壘包或出局數的
    playEvent。base 狀態靠 runners[] 的移動紀錄重建（Gumbo 沒有逐球壘包欄位）；
    outs 同樣靠 runners[] 裡 isOut 的移動逐事件累加，不用 playEvent 的 count.outs：
    投球事件的 count.outs 是事件前的出局數，但「牽制盜壘出局」這類非投球事件的 count.outs
    是事件後的出局數，直接用會把 1 出局的牽制盜壘失敗誤歸到 2 出局。累加結果與每個
    play 結尾的 count.outs 逐 play 比對過完全一致。"""
    base: dict[int, Any] = {1: None, 2: None, 3: None}
    events: list[dict[str, Any]] = []
    outs_so_far = 0
    # 延長賽（第 10 局起）每個半局開始時二壘有人（placed runner），Gumbo 不會單獨給一個事件，
    # 只會在該跑者第一次移動時出現 start=="2B"。用佔位符先放上去，跑者移動時才能對得上。
    if half_plays and as_int(half_plays[0].get("about", {}).get("inning")) >= 10:
        base[2] = "placed"

    for play in half_plays:
        batter = play.get("matchup", {}).get("batter", {})
        by_index: dict[int | None, list[dict[str, Any]]] = {}
        for runner in play.get("runners", []):
            idx = runner.get("details", {}).get("playIndex")
            by_index.setdefault(idx, []).append(runner)

        applied_indices: set[int | None] = set()

        def apply(movements: list[dict[str, Any]]) -> None:
            for runner in movements:
                move = runner.get("movement", {})
                runner_id = runner.get("details", {}).get("runner", {}).get("id")
                start = move.get("start")
                end = move.get("end")
                if start in ("1B", "2B", "3B"):
                    slot = int(start[0])
                    if base.get(slot) == runner_id or base.get(slot) == "placed":
                        base[slot] = None
                if not move.get("isOut") and end in ("1B", "2B", "3B"):
                    base[int(end[0])] = runner_id

        for pe in play.get("playEvents", []):
            idx = pe.get("index")
            movements_here = by_index.get(idx, [])
            details = pe.get("details", {})
            event_name = details.get("event") or ""
            # 盜壘發生在投球事件上時（例如對方暴傳前的盜壘、三振同時盜壘），playEvent 自己沒有
            # event 名稱，盜壘標記只出現在 runners[] 的 details.event，所以兩邊都要看。
            steal_names = [
                (m.get("details", {}).get("event") or "") for m in movements_here
                if any(name in (m.get("details", {}).get("event") or "") for name in STEAL_EVENT_NAMES)
            ]
            events.append({
                "outs": outs_so_far,
                "on1b": base[1] is not None,
                "on2b": base[2] is not None,
                "on3b": base[3] is not None,
                "runnerOnFirstId": base[1],
                "batterId": batter.get("id"),
                "batterName": batter.get("fullName"),
                "eventText": details.get("description") or event_name or (steal_names[0] if steal_names else ""),
                "hasStealMention": bool(steal_names) or any(name in event_name for name in STEAL_EVENT_NAMES),
                "movements": movements_here,
                "afterScore": play.get("result", {}).get("awayScore"),
                "afterScoreHome": play.get("result", {}).get("homeScore"),
                "isPlayComplete": pe is play.get("playEvents", [])[-1],
                "runs": sum(1 for m in movements_here if m.get("movement", {}).get("end") == "score"),
            })
            apply(movements_here)
            outs_so_far += sum(1 for m in movements_here if m.get("movement", {}).get("isOut"))
            applied_indices.add(idx)

        leftover = [m for key, ms in by_index.items() if key not in applied_indices for m in ms]
        if leftover:
            apply(leftover)
            outs_so_far += sum(1 for m in leftover if m.get("movement", {}).get("isOut"))

    return events


OUTCOME_BY_EVENT_TYPE = {
    "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
    "walk": "BB_HBP", "intent_walk": "BB_HBP", "hit_by_pitch": "BB_HBP",
    "field_error": "REACH", "fielders_choice": "REACH", "fielders_choice_out": "REACH",
    "catcher_interf": "REACH", "batter_interference": "REACH",
}


def classify_outcome(event_type: str) -> str:
    """result.eventType 已經是結構化分類，比 CPBL 的自由文字判讀乾淨很多。
    沒對到上面任何一種的（field_out/force_out/strikeout/double_play/sac_fly/... 等）一律算 OUT，
    跟 CPBL 版一致：MLB 的 sac_fly/sac_bunt 定義上打者必定出局（因失誤上壘會另外編碼成 field_error）。"""
    return OUTCOME_BY_EVENT_TYPE.get(event_type, "OUT")


def build_pa_records(feed: dict[str, Any]) -> list[dict[str, Any]]:
    """把整場的每個 play（= 一個完整打席）拆成模擬用的紀錄：打席前狀態、結果、打席後狀態。
    跟 mlb_model_batter_decisions.py 共用，place 在這裡是因為半局壘包重建（build_event_stream）
    已經在這支檔案。"""
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    halves: dict[tuple[int, bool], list[dict[str, Any]]] = {}
    for play in plays:
        halves.setdefault(half_key(play), []).append(play)

    records: list[dict[str, Any]] = []
    for (inning, is_top), half_plays in halves.items():
        events = build_event_stream(half_plays)
        # 每個 play 對應到它自己 playEvents 裡的第一個事件，即為打席開始前的狀態快照。
        pe_cursor = 0
        for play_index, play in enumerate(half_plays):
            n_events = len(play.get("playEvents", []))
            if n_events == 0:
                continue
            pre_state = events[pe_cursor]
            result = play.get("result", {})
            event_type = result.get("eventType", "")
            outcome = classify_outcome(event_type)
            is_strikeout = event_type in ("strikeout", "strikeout_double_play")
            has_runner_event = any(e["hasStealMention"] for e in events[pe_cursor:pe_cursor + n_events])

            # 打席後狀態 = 下一個打席開始前的狀態快照；半局最後一個打席固定是 3 出局、空壘。
            # 以前用 next_play.count.outs 取出局數，但 play.count 是「該 play 結束時」的計數，
            # 會誤取到下一個打席結束後的出局數，所以改用 build_event_stream 累加的出局數。
            next_pre = events[pe_cursor + n_events] if pe_cursor + n_events < len(events) else None
            if next_pre is not None:
                outs_after = next_pre["outs"]
                bases_after = (
                    (1 if next_pre["on1b"] else 0)
                    | (2 if next_pre["on2b"] else 0)
                    | (4 if next_pre["on3b"] else 0)
                )
            else:
                outs_after, bases_after = 3, 0

            batter = play.get("matchup", {}).get("batter", {})
            # 得分數直接數 runners[] 裡 end=="score" 的移動。以前用「本 play 結束比分－前一個 play
            # 結束比分」，但半局第一個打席沒有前一個 play，被當成 0，結果等於該隊累積總分
            # （例如第 5 局第一個打席被算成 3 分），會污染兩出局以外所有「空壘」起點的推進池。
            play_runs = sum(
                1 for runner in play.get("runners", [])
                if runner.get("movement", {}).get("end") == "score"
            )

            records.append({
                "inning": inning,
                "is_top": is_top,
                "batter_id": batter.get("id"),
                "batter_name": batter.get("fullName"),
                "lineup_slot": None,  # 由呼叫端用 boxscore battingOrder 補上
                "start_outs": pre_state["outs"],
                "start_bases": (1 if pre_state["on1b"] else 0) | (2 if pre_state["on2b"] else 0) | (4 if pre_state["on3b"] else 0),
                "outcome": outcome,
                "runs": play_runs,
                "outs_after": min(3, outs_after),
                "bases_after": bases_after,
                "has_runner_event": has_runner_event,
                "is_strikeout": is_strikeout,
            })
            pe_cursor += n_events
    return records


def batting_order_slots(feed: dict[str, Any]) -> dict[int, int]:
    """player_id -> 1-9 棒次。battingOrder 欄位格式「棒次(1碼)+替補序(2碼)」，如 601=第6棒代打。"""
    slots: dict[int, int] = {}
    for side in ("home", "away"):
        players = feed.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {}).get("players", {})
        for p in players.values():
            order = p.get("battingOrder")
            if order:
                slots[p["person"]["id"]] = int(order) // 100
    return slots


def is_target_state(event: dict[str, Any], inning: int) -> bool:
    return (
        1 <= inning <= 8
        and event["outs"] == 2
        and event["on1b"] and not event["on2b"] and not event["on3b"]
    )


def team_score_for(play: dict[str, Any], is_away_batting: bool) -> int:
    result = play.get("result", {})
    return as_int(result.get("awayScore") if is_away_batting else result.get("homeScore"))


def analyze_game(game_meta: dict[str, Any], feed: dict[str, Any]) -> list[dict[str, Any]]:
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not plays:
        return []

    game_data = feed.get("gameData", {})
    away_team = game_data.get("teams", {}).get("away", {}).get("name", game_meta.get("AwayTeam"))
    home_team = game_data.get("teams", {}).get("home", {}).get("name", game_meta.get("HomeTeam"))

    halves: dict[tuple[int, bool], list[dict[str, Any]]] = {}
    for play in plays:
        halves.setdefault(half_key(play), []).append(play)

    half_end_scores: dict[tuple[int, bool], int] = {}
    for key, half_plays in halves.items():
        is_away_batting = key[1]
        half_end_scores[key] = team_score_for(half_plays[-1], is_away_batting)

    results: list[dict[str, Any]] = []

    for key, half_plays in halves.items():
        inning, is_top = key
        is_away_batting = is_top
        batting_team = away_team if is_away_batting else home_team
        events = build_event_stream(half_plays)

        target = [e for e in events if is_target_state(e, inning)]
        if not target:
            continue

        state_event = target[0]
        # 狀態形成前的比分基準 = 這一隊上一個進攻半局結束的累積比分 + 本半局在狀態形成前已發生的得分。
        # half_end_scores 是整場累積比分，不是單一半局得分，所以不能把基準當 0。
        prev_own_end_score = half_end_scores.get((inning - 1, is_top), 0)
        state_position = next(i for i, e in enumerate(events) if e is state_event)
        before_state_score = prev_own_end_score + sum(e["runs"] for e in events[:state_position])

        outcome = "no_steal"
        event_index_in_target: int | None = None
        for i, event in enumerate(target):
            if not event["hasStealMention"]:
                continue
            steal_move = next(
                (m for m in event["movements"]
                 if m.get("movement", {}).get("start") == "1B"
                 and "Stolen Base" in (m.get("details", {}).get("event") or "")
                 or (m.get("movement", {}).get("start") == "1B"
                     and "Caught Stealing" in (m.get("details", {}).get("event") or ""))),
                None,
            )
            if not steal_move:
                continue
            move = steal_move.get("movement", {})
            if move.get("isOut"):
                outcome = "steal_failure"
            else:
                outcome = "steal_success"
            event_index_in_target = i
            break

        current_end_score = half_end_scores[key]
        current_from_state = current_end_score - before_state_score

        if outcome == "steal_success":
            steal_position = next(i for i, e in enumerate(events) if e is target[event_index_in_target])
            score_after_steal = prev_own_end_score + sum(e["runs"] for e in events[:steal_position + 1])
            current_after_decision = current_end_score - score_after_steal
        elif outcome == "steal_failure":
            current_after_decision = 0
        else:
            current_after_decision = current_from_state

        next_key = (inning + 1, is_top)
        next_plays = halves.get(next_key, [])
        next_half_runs = None
        next_leadoff_id = None
        next_leadoff_name = None
        if next_plays:
            next_leadoff_id = next_plays[0].get("matchup", {}).get("batter", {}).get("id")
            next_leadoff_name = next_plays[0].get("matchup", {}).get("batter", {}).get("fullName")
            next_half_end = half_end_scores[next_key]
            next_half_runs = next_half_end - current_end_score

        state_batter_id = state_event["batterId"]
        retention_matches = None
        if outcome == "steal_failure" and next_leadoff_id is not None:
            retention_matches = state_batter_id == next_leadoff_id

        requested_re = current_after_decision if outcome == "steal_success" else next_half_runs
        requested_definition = (
            "盜壘成功事件後至當半局結束的剩餘得分"
            if outcome == "steal_success"
            else "同隊下一個半局的得分"
        )

        event_row = target[event_index_in_target] if event_index_in_target is not None else None
        results.append({
            "Season": game_meta.get("Season"),
            "GamePk": game_meta.get("GamePk"),
            # 與 CPBL 版欄位對齊：GameSno／StateRowIndex 是 compare_wpa_groups 等跨腳本 join 用的主鍵。
            # 每個半局最多一筆決策，所以 (GamePk, 半局序號) 就能唯一識別。
            "GameSno": game_meta.get("GamePk"),
            "StateRowIndex": inning * 2 + (0 if is_top else 1),
            "GameDate": game_meta.get("GameDate"),
            "AwayTeam": away_team,
            "HomeTeam": home_team,
            "InningSeq": inning,
            "IsTopInning": is_top,
            "BattingTeam": batting_team,
            "BatterId": state_batter_id,
            "BatterName": state_event["batterName"],
            "RunnerOnFirstId": state_event["runnerOnFirstId"],
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
            "NextHalfExists": bool(next_plays),
            "NextHalfLeadoffId": next_leadoff_id,
            "NextHalfLeadoffName": next_leadoff_name,
            "RetentionMatches": retention_matches,
            "EventText": event_row["eventText"] if event_row else "",
        })

    return results


def load_or_fetch_game(
    game_pk: int, cache_dir: Path, refresh: bool, retries: int,
) -> tuple[dict[str, Any], bool]:
    cache_file = cache_dir / f"game_{game_pk}.json"
    if cache_file.exists() and not refresh:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("liveData", {}).get("plays", {}).get("allPlays"):
            return cached, False

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            data = MLB_steal_getData.get_live_feed(game_pk)
            if not data.get("liveData", {}).get("plays", {}).get("allPlays"):
                raise RuntimeError("live feed 沒有逐打席資料（可能延期或未開打）")
            cache_dir.mkdir(parents=True, exist_ok=True)
            temp_file = cache_file.with_suffix(".json.tmp")
            temp_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temp_file.replace(cache_file)
            return data, True
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GamePk={game_pk} 抓取失敗：{last_error}") from last_error


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


def write_summary(path: Path, args: argparse.Namespace, games_processed: int,
                   failures: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    counts = Counter(str(row["Outcome"]) for row in rows)
    summary = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "games_processed": games_processed,
        "games_failed": len(failures),
        "failures": failures,
        "decision_samples": len(rows),
        "outcome_counts": dict(sorted(counts.items())),
        "missing_requested_re": sum(row["RequestedRE"] is None for row in rows),
        "failed_steal_retention_mismatches": sum(row["RetentionMatches"] is False for row in rows),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--game-type", default="R", help="MLB gameType，預設 R 只取例行賽；傳空字串則不篩選")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--jitter", type=float, default=1.5)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/mlb"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    games = MLB_steal_getData.get_schedule(args.start_date, args.end_date, args.game_type or None)
    print(f"賽程找到 {len(games)} 場，開始抓取。")

    cache_dir = args.cache_dir / f"{args.start_date}_{args.end_date}"
    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    processed = 0

    for position, game in enumerate(games, 1):
        game_pk = game["GamePk"]
        label = f"[{position}/{len(games)}] GamePk={game_pk} {game['AwayTeam']} @ {game['HomeTeam']}"
        try:
            data, fetched = load_or_fetch_game(game_pk, cache_dir, args.refresh, max(1, args.retries))
            game_meta = {**game, "Season": str(game["GameDate"])[:4]}
            samples = analyze_game(game_meta, data)
            all_rows.extend(samples)
            processed += 1
            source = "官網" if fetched else "快取"
            print(f"{label}：{source}，符合 {len(samples)} 筆")
            if fetched and position < len(games):
                time.sleep(max(0.0, args.delay) + random.uniform(0, max(0.0, args.jitter)))
        except Exception as error:
            print(f"{label}：失敗：{error}")
            failures.append({"GamePk": game_pk, "error": str(error)})

    tag = f"{args.start_date}_{args.end_date}"
    csv_path = args.output_dir / f"mlb_2out_first_base_{tag}.csv"
    summary_path = args.output_dir / f"mlb_2out_first_base_{tag}_summary.json"
    write_csv(all_rows, csv_path)
    write_summary(summary_path, args, processed, failures, all_rows)

    print(f"完成：{processed}/{len(games)} 場，{len(all_rows)} 筆決策樣本")
    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
