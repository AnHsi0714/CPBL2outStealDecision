"""建立 MLB 版 WE（win expectancy）勝率矩陣，方法與輸出格式對齊 build_win_expectancy_matrix.py。

資料來源是 mlb_find_2out_first_base.py 已快取的 Gumbo JSON，不重新請求。比分與勝負從逐打席
紀錄推回（最後一個 play 的 awayScore/homeScore），不查 boxscore 總分欄位，跟 CPBL 版原則一致。
每個 base-out state 區段記錄「區段起算當下」的分差與整場最終勝負；區段內打席中得分
用事件的 runs 累加。延長賽的 placed runner 由 build_event_stream 處理（第 10 局起二壘有人）。
再見安打的最後半局沒有第 3 個出局，但勝負已定，所以仍計入（MLB 沒有和局）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import json
from pathlib import Path
from typing import Any

from build_win_expectancy_matrix import (
    INNING_BUCKETS,
    SCORE_DIFF_CAP,
    build_matrix,
    inning_bucket,
    score_diff_bucket,
    write_csv,
)
from mlb_build_re24_matrix import base_code
from mlb_find_2out_first_base import build_event_stream, half_key

DEFAULT_SEASONS = [
    "2023-03-15:2023-10-10",
    "2024-03-15:2024-10-10",
    "2025-03-15:2025-10-10",
    "2026-03-15:2026-10-10",
]


def collect_game_segments(feed: dict[str, Any]) -> list[tuple[str, str, int, int, int, float]]:
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not plays:
        return []
    last_result = plays[-1].get("result", {})
    final_away, final_home = last_result.get("awayScore"), last_result.get("homeScore")
    if final_away is None or final_home is None or final_away == final_home:
        return []
    winner_is_away = final_away > final_home

    halves: dict[tuple[int, bool], list[dict[str, Any]]] = {}
    for play in plays:
        halves.setdefault(half_key(play), []).append(play)

    segments: list[tuple[str, str, int, int, int, float]] = []
    previous_play: dict[str, Any] | None = None
    for (inning, is_top), half_plays in halves.items():
        away_score = previous_play["result"].get("awayScore", 0) if previous_play else 0
        home_score = previous_play["result"].get("homeScore", 0) if previous_play else 0
        batting_side = "1" if is_top else "2"
        outcome = 1.0 if winner_is_away == is_top else 0.0
        own = away_score if is_top else home_score
        opp = home_score if is_top else away_score

        previous_state: tuple[int, int] | None = None
        for event in build_event_stream(half_plays):
            if event["outs"] in (0, 1, 2):
                state = (event["outs"], base_code(event))
                if state != previous_state:
                    segments.append((
                        inning_bucket(inning), batting_side, score_diff_bucket(own - opp),
                        state[0], state[1], outcome,
                    ))
                    previous_state = state
            own += event["runs"]
        previous_play = half_plays[-1]
    return segments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS,
                        help="每個球季一組 start_date:end_date，對應 data/raw/mlb/{start}_{end}/")
    parser.add_argument("--cache-root", type=Path, default=Path("data/raw/mlb"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--output-tag", default="2023-2026_R_combined")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_segments: list[tuple[str, str, int, int, int, float]] = []
    games_processed = games_skipped = 0
    season_entries = []
    for spec in args.seasons:
        start, end = spec.split(":")
        paths = sorted((args.cache_root / f"{start}_{end}").glob("game_*.json"))
        if not paths:
            raise SystemExit(f"{args.cache_root / f'{start}_{end}'} 沒有快取場次")
        for path in paths:
            segments = collect_game_segments(json.loads(path.read_text(encoding="utf-8")))
            if segments:
                games_processed += 1
                all_segments.extend(segments)
            else:
                games_skipped += 1
        season_entries.append({"year": start[:4], "kind_code": "R", "start": start, "end": end})
        print(f"[{start}~{end}] 累計 {games_processed} 場、{len(all_segments)} 個區段")

    matrix = build_matrix(all_segments)
    csv_path = args.output_dir / f"mlb_win_expectancy_matrix_{args.output_tag}.csv"
    summary_path = args.output_dir / f"mlb_win_expectancy_matrix_{args.output_tag}_summary.json"
    write_csv(matrix, csv_path)
    summary = {
        "seasons": season_entries,
        "score_diff_cap": SCORE_DIFF_CAP,
        "inning_buckets": INNING_BUCKETS,
        "games_expected": games_processed + games_skipped,
        "games_processed": games_processed,
        "games_skipped_incomplete": games_skipped,
        "games_failed": 0,
        "failures": [],
        "total_state_segments": matrix["totalSegments"],
        "cells": matrix["cells"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{games_processed} 場（略過 {games_skipped}），{matrix['totalSegments']} 個區段")
    print(f"CSV：{csv_path}\n摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
