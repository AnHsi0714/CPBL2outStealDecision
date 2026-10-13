"""抓取並整理 KBO「兩出局、僅一壘有人」決策樣本，欄位對齊 mlb_find_2out_first_base.py／find_2out_first_base.py。

資料來源是 KBO 官網文字轉播（KBO_crawl_seasons.py 已快取的 HTML：data/raw/kbo/{年}/{GameId}.html），
經 KBO_steal_getData.parse_game 重建成逐事件列（出局數、壘包是照敘述句規則重建的狀態機）。
跟 CPBL／MLB 的結構差異，也是移植時必須處理的三件事：

1. 沒有累積比分欄位。得分數直接數：跑者列「홈인／득점」各 1 分、打者列「홈런」1 分（同一支全壘打
   其他跑者各有自己的「홈인」列）。所以剩餘得分都是「數事件」得到，不是比分相減。
2. 沒有球員 ID，只有姓名。球員主鍵一律用 `{球隊}:{姓名}`，同一球隊同名同姓的情況視為同一人。
3. 沒有逐球結構化的打席邊界。同一個半局內連續同名的打者列、跑者列合成一個「打席群組」：
   群組內任何一列的狀態是事件前狀態，群組起點狀態＝打席前狀態，打席後狀態＝下一個群組的起點狀態
   （半局最後一個群組＝3 出局、空壘）。群組內的盜壘、暴投等跑者事件算同一個打席的一部分。

盜壘只計「一壘跑者盜二壘」：「도루로 2루까지 진루」成功、「도루실패아웃」失敗；雙盜壘、三重盜壘、
無關心盜壘（무관심도루）不屬於本研究範圍。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import KBO_steal_getData as kbo

STEAL_SECOND_SUCCESS_RE = re.compile(r"^1루주자 \S+ : 도루로 2루까지 진루")
STEAL_SECOND_ERROR_RE = re.compile(r"^1루주자 \S+ : 도루실패 기록하며 2루까지 진루")
STEAL_SECOND_FAILURE_RE = re.compile(r"^1루주자 \S+ : 도루실패아웃")

OUTCOME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("HR", re.compile(r"홈런")),
    ("3B", re.compile(r"3루타")),
    ("2B", re.compile(r"2루타")),
    ("1B", re.compile(r"1루타|내야안타|번트안타|안타")),
    ("BB_HBP", re.compile(r"볼넷|몸에 맞는 볼|고의4구")),
]
DROPPED_THIRD_STRIKE_RE = re.compile(r"낫\s?아웃\s*(폭투|포일|다른주자)")


def base_code(row: dict[str, Any]) -> int:
    return (1 if row["On1B"] else 0) | (2 if row["On2B"] else 0) | (4 if row["On3B"] else 0)


def truthy(value: Any) -> bool:
    return value is True or str(value) == "True"


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "Inning": int(row["Inning"]),
        "Outs": int(row["Outs"]),
        "On1B": truthy(row["On1B"]), "On2B": truthy(row["On2B"]), "On3B": truthy(row["On3B"]),
        "BatterSlot": int(row["BatterSlot"]) if row.get("BatterSlot") not in (None, "", "None") else None,
    }


def row_runs(row: dict[str, Any]) -> int:
    text = row["RawText"]
    if row["EventType"] == "runner_movement":
        result = text.split(" : ", 1)[-1]
        return 1 if ("홈인" in result or "득점" in result) else 0
    return 1 if "홈런" in text.split(" : ", 1)[-1] else 0


def classify_batter_outcome(text: str) -> tuple[str, bool]:
    """回傳 (OUTCOMES 之一, 是否三振)。沿用 CPBL／MLB 版的七類：1B/2B/3B/HR/BB_HBP/REACH/OUT。"""
    result = text.split(" : ", 1)[-1]
    for name, pattern in OUTCOME_PATTERNS:
        if pattern.search(result):
            return name, False
    is_strikeout = "삼진" in result or "스트라이크 낫" in result
    if DROPPED_THIRD_STRIKE_RE.search(result) or "출루" in result:
        return "REACH", is_strikeout
    return "OUT", is_strikeout


def steal_second_kind(row: dict[str, Any]) -> str | None:
    if row["EventType"] != "runner_movement":
        return None
    text = row["RawText"]
    if STEAL_SECOND_FAILURE_RE.match(text):
        return "failure"
    if STEAL_SECOND_SUCCESS_RE.match(text) or STEAL_SECOND_ERROR_RE.match(text):
        return "success"
    return None


def parse_html(game_id: str, html: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date = f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}"
    meta = {"GameId": game_id, "GameDate": date, "AwayTeam": "", "HomeTeam": ""}
    rows = [normalize_row(r) for r in kbo.parse_game(meta, html)]
    rows = [r for r in rows if r["BatterName"] and not r["RawText"].startswith("무승부")]
    for row in rows:
        if not meta["AwayTeam"] and row["HalfInning"] == "top":
            meta["AwayTeam"] = row["BattingTeam"]
        if not meta["HomeTeam"] and row["HalfInning"] == "bottom":
            meta["HomeTeam"] = row["BattingTeam"]
    return meta, rows


def iter_cached_games(cache_dir: Path) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """依 GameId 排序逐場回傳 (meta, rows)；GameSno 是日期 * 100 + 當天第幾場，保證跨賽季唯一的整數。"""
    per_day: Counter[str] = Counter()
    for path in sorted(cache_dir.glob("*.html")):
        game_id = path.stem
        meta, rows = parse_html(game_id, path.read_text(encoding="utf-8"))
        if not rows:
            continue
        per_day[game_id[:8]] += 1
        meta["GameSno"] = int(game_id[:8]) * 100 + per_day[game_id[:8]]
        yield meta, rows


def split_halves(rows: list[dict[str, Any]]) -> dict[tuple[int, str], list[dict[str, Any]]]:
    halves: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        halves.setdefault((row["Inning"], row["HalfInning"]), []).append(row)
    return halves


def group_by_batter(half_rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for row in half_rows:
        if groups and groups[-1][0]["BatterName"] == row["BatterName"]:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def half_is_complete(half_rows: list[dict[str, Any]]) -> bool:
    """最後一列事件發生後出局數達 3，才算打完的半局（再見安打等未完半局排除）。"""
    last = half_rows[-1]
    text = last["RawText"].split(" : ", 1)[-1]
    out_added = 1 if ("아웃" in text and not DROPPED_THIRD_STRIKE_RE.search(text)) else 0
    return last["Outs"] + out_added >= 3


def hitter_id(row: dict[str, Any]) -> str:
    return f"{row['BattingTeam']}:{row['BatterName']}"


def build_pa_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每個打席群組一筆：打席前狀態、結果、打席後狀態。沒有打者結果列的群組 outcome 為 "NONE"。"""
    records: list[dict[str, Any]] = []
    for (inning, half), half_rows in split_halves(rows).items():
        complete = half_is_complete(half_rows)
        groups = group_by_batter(half_rows)
        for index, group in enumerate(groups):
            outcome_rows = [r for r in group if r["EventType"] == "batter_outcome"]
            start = group[0]
            if index + 1 < len(groups):
                nxt = groups[index + 1][0]
                outs_after, bases_after = nxt["Outs"], base_code(nxt)
            elif complete:
                outs_after, bases_after = 3, 0
            else:
                continue
            # 打席中途半局就結束（例如盜壘失敗成為第三出局）的群組沒有打者結果列，標成 "NONE"，
            # 不能進打者機率分布，但仍要留在序列裡，打序重建與決策定位才找得到這位打者。
            outcome, is_strikeout = (
                classify_batter_outcome(outcome_rows[0]["RawText"]) if outcome_rows else ("NONE", False)
            )
            slot = next((r["BatterSlot"] for r in group if r["BatterSlot"]), None)
            records.append({
                "inning": inning,
                "is_top": half == "top",
                "batter_id": hitter_id(start),
                "batter_name": start["BatterName"],
                "lineup_slot": slot,
                "start_outs": start["Outs"],
                "start_bases": base_code(start),
                "outcome": outcome,
                "runs": sum(row_runs(r) for r in group),
                "outs_after": min(3, outs_after),
                "bases_after": bases_after,
                "has_runner_event": any("도루" in r["RawText"] for r in group),
                "is_strikeout": is_strikeout,
            })
    return records


def post_outcome_indices(half_rows: list[dict[str, Any]]) -> set[int]:
    """同一位打者的打者結果列「之後」的跑者列，是這個打席結果的後續（安打推進、守備阻殺等），
    不是跑者自己選擇要不要開跑的決策點。最典型的是三振同時阻殺（「삼진 아웃」之後接
    「도루실패아웃」）：實際上是 1 出局時跑者起跑、同一球三振，文字轉播把打者出局排在前面，
    狀態機看起來就變成「2 出局、一壘有人時盜壘失敗」，會把這種雙殺誤判成決策樣本。"""
    skipped: set[int] = set()
    seen_outcome_for: str | None = None
    previous_name: str | None = None
    for index, row in enumerate(half_rows):
        if row["BatterName"] != previous_name:
            seen_outcome_for = None
            previous_name = row["BatterName"]
        if row["EventType"] == "batter_outcome":
            seen_outcome_for = row["BatterName"]
        elif seen_outcome_for == row["BatterName"]:
            skipped.add(index)
    return skipped


def is_target_row(row: dict[str, Any]) -> bool:
    return (
        1 <= row["Inning"] <= 8 and row["Outs"] == 2
        and row["On1B"] and not row["On2B"] and not row["On3B"]
    )


def analyze_game(meta: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    halves = split_halves(rows)
    half_runs = {key: sum(row_runs(r) for r in half_rows) for key, half_rows in halves.items()}
    results: list[dict[str, Any]] = []

    for (inning, half), half_rows in halves.items():
        skipped = post_outcome_indices(half_rows)
        target_indices = [i for i, r in enumerate(half_rows) if is_target_row(r) and i not in skipped]
        if not target_indices:
            continue
        state_index = target_indices[0]
        state_row = half_rows[state_index]

        outcome, event_index = "no_steal", None
        for i in target_indices:
            kind = steal_second_kind(half_rows[i])
            if kind:
                outcome, event_index = f"steal_{kind}", i
                break

        # 決策當下的分差（進攻方－防守方）：雙方此前各半局得分加總，加上本半局狀態形成前已發生的得分。
        opposite = "bottom" if half == "top" else "top"
        own_before = sum(v for (n, h), v in half_runs.items() if h == half and n < inning)
        opp_before = sum(v for (n, h), v in half_runs.items() if h == opposite and (n < inning or (n == inning and half == "bottom")))
        total_runs = half_runs[(inning, half)]
        before_state = sum(row_runs(r) for r in half_rows[:state_index])
        current_from_state = total_runs - before_state
        if outcome == "steal_success":
            current_after = total_runs - sum(row_runs(r) for r in half_rows[:event_index + 1])
        elif outcome == "steal_failure":
            current_after = 0
        else:
            current_after = current_from_state

        next_key = (inning + 1, half)
        next_rows = halves.get(next_key, [])
        next_runs = half_runs.get(next_key) if next_rows else None
        next_leadoff = next_rows[0] if next_rows else None
        state_slot = state_row["BatterSlot"]
        retention_matches = None
        if outcome == "steal_failure" and next_leadoff is not None and next_leadoff["BatterSlot"] is not None:
            retention_matches = state_slot == next_leadoff["BatterSlot"]

        requested_re = current_after if outcome == "steal_success" else next_runs
        results.append({
            "Season": meta["GameDate"][:4],
            "GamePk": meta["GameSno"],
            "GameSno": meta["GameSno"],
            "StateRowIndex": inning * 2 + (0 if half == "top" else 1),
            "ScoreDiffAtState": own_before + sum(row_runs(r) for r in half_rows[:state_index]) - opp_before,
            "GameId": meta["GameId"],
            "GameDate": meta["GameDate"],
            "AwayTeam": meta["AwayTeam"],
            "HomeTeam": meta["HomeTeam"],
            "InningSeq": inning,
            "IsTopInning": half == "top",
            "BattingTeam": state_row["BattingTeam"],
            "BatterId": hitter_id(state_row),
            "BatterName": state_row["BatterName"],
            "BatterSlot": state_slot,
            "RunnerOnFirstId": "",
            "Outcome": outcome,
            "RequestedRE": requested_re,
            "RequestedREDefinition": (
                "盜壘成功事件後至當半局結束的剩餘得分" if outcome == "steal_success" else "同隊下一個半局的得分"
            ),
            "CurrentHalfRemainingRunsFromState": current_from_state,
            "CurrentHalfRemainingRunsAfterDecision": current_after,
            "NextHalfRuns": next_runs,
            "TwoHalfRunsAfterDecision": current_after + next_runs if next_runs is not None else None,
            "NextHalfExists": bool(next_rows),
            "NextHalfLeadoffId": hitter_id(next_leadoff) if next_leadoff else None,
            "NextHalfLeadoffName": next_leadoff["BatterName"] if next_leadoff else None,
            "RetentionMatches": retention_matches,
            "EventText": half_rows[event_index]["RawText"] if event_index is not None else "",
        })
    return results


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise RuntimeError("沒有符合條件的樣本，不寫出空 CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cache_dir = args.cache_dir or Path("data/raw/kbo") / args.year
    rows_out: list[dict[str, Any]] = []
    games = 0
    for meta, rows in iter_cached_games(cache_dir):
        games += 1
        rows_out.extend(analyze_game(meta, rows))
    counts = Counter(r["Outcome"] for r in rows_out)
    mismatches = sum(r["RetentionMatches"] is False for r in rows_out)
    csv_path = args.output_dir / f"kbo_2out_first_base_{args.year}.csv"
    summary_path = args.output_dir / f"kbo_2out_first_base_{args.year}_summary.json"
    write_csv(rows_out, csv_path)
    summary = {
        "year": args.year,
        "games_processed": games,
        "decision_samples": len(rows_out),
        "outcome_counts": dict(sorted(counts.items())),
        "missing_requested_re": sum(r["RequestedRE"] is None for r in rows_out),
        "failed_steal_retention_mismatches": mismatches,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
