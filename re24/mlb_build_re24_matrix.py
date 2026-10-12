"""建立 MLB 版 RE24（24 種 base-out state）得分期望值矩陣，方法對齊 build_re24_matrix.py。

資料來源是 mlb_find_2out_first_base.py 已快取的 Gumbo JSON（data/raw/mlb/{start}_{end}/），
不重新請求。壘包與出局數沿用 build_event_stream 的逐事件重建，剩餘得分＝半局總得分－
該事件之前已發生的得分（runners[] 裡 end=="score" 的移動），所以涵蓋打席內的盜壘、暴投等
狀態切換。只算第 1–9 局：延長賽自 2020 起有「placed runner」，Gumbo 的半局起始壘包不是
事件造成的，會讓 RE 起算點錯位。只計入已打完（3 出局）的半局，排除再見安打的未完半局。

輸出格式（CSV、_summary.json）與 CPBL 版相同，re24 報告產生器可直接讀。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import json
from pathlib import Path
from typing import Any

from build_re24_matrix import build_matrix, write_csv
from mlb_find_2out_first_base import build_event_stream, half_key

MAX_INNING = 9


def base_code(event: dict[str, Any]) -> int:
    return (1 if event["on1b"] else 0) | (2 if event["on2b"] else 0) | (4 if event["on3b"] else 0)


def collect_game_segments(feed: dict[str, Any]) -> list[tuple[int, int, int]]:
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    halves: dict[tuple[int, bool], list[dict[str, Any]]] = {}
    for play in plays:
        halves.setdefault(half_key(play), []).append(play)

    segments: list[tuple[int, int, int]] = []
    for (inning, _is_top), half_plays in halves.items():
        if inning > MAX_INNING or int(half_plays[-1].get("count", {}).get("outs", 0)) != 3:
            continue
        events = build_event_stream(half_plays)
        total_runs = sum(
            1 for play in half_plays for runner in play.get("runners", [])
            if runner.get("movement", {}).get("end") == "score"
        )
        runs_before = 0
        previous_state: tuple[int, int] | None = None
        for event in events:
            if event["outs"] in (0, 1, 2):
                state = (event["outs"], base_code(event))
                if state != previous_state:
                    segments.append((state[0], state[1], total_runs - runs_before))
                    previous_state = state
            runs_before += event["runs"]
    return segments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.start_date}_{args.end_date}"
    cache_dir = args.cache_dir or Path("data/raw/mlb") / tag
    paths = sorted(cache_dir.glob("game_*.json"))
    if not paths:
        raise SystemExit(f"{cache_dir} 沒有快取場次，請先執行 mlb_find_2out_first_base.py")

    all_segments: list[tuple[int, int, int]] = []
    for path in paths:
        all_segments.extend(collect_game_segments(json.loads(path.read_text(encoding="utf-8"))))

    matrix = build_matrix(all_segments)
    csv_path = args.output_dir / f"mlb_re24_matrix_{tag}.csv"
    summary_path = args.output_dir / f"mlb_re24_matrix_{tag}_summary.json"
    write_csv(matrix, csv_path)
    summary = {
        "year": args.start_date[:4],
        "kind_code": "R",
        "game_sno_start": args.start_date,
        "game_sno_end": args.end_date,
        "games_expected": len(paths),
        "games_processed": len(paths),
        "games_failed": 0,
        "failures": [],
        "total_state_segments": matrix["totalSegments"],
        "basic_break_even_threshold_by_outs": matrix["basicBreakEvenThresholdByOuts"],
        "cells": matrix["cells"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{len(paths)} 場，{matrix['totalSegments']} 個 state 區段")
    print(f"CSV：{csv_path}\n摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
