"""建立 KBO 版 RE24（24 種 base-out state）得分期望值矩陣，方法對齊 build_re24_matrix.py。

資料來源是 kbo_find_2out_first_base.py 解析的文字轉播事件列（data/raw/kbo/{年}/*.html），
不重新請求。壘包與出局數是照敘述句規則重建的狀態機，剩餘得分＝半局總得分－該列之前已發生的得分
（數「홈인／득점」跑者列與「홈런」打者列）。只計入已打完（3 出局）的半局。
輸出格式（CSV、_summary.json）與 CPBL 版相同。
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
from kbo_find_2out_first_base import base_code, half_is_complete, iter_cached_games, row_runs, split_halves


def collect_game_segments(rows: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    segments: list[tuple[int, int, int]] = []
    for half_rows in split_halves(rows).values():
        if not half_is_complete(half_rows):
            continue
        total = sum(row_runs(r) for r in half_rows)
        before = 0
        previous_state = None
        for row in half_rows:
            state = (row["Outs"], base_code(row))
            if row["Outs"] in (0, 1, 2) and state != previous_state:
                segments.append((state[0], state[1], total - before))
                previous_state = state
            before += row_runs(row)
    return segments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cache_dir = args.cache_dir or Path("data/raw/kbo") / args.year
    all_segments: list[tuple[int, int, int]] = []
    games = 0
    for _meta, rows in iter_cached_games(cache_dir):
        games += 1
        all_segments.extend(collect_game_segments(rows))
    matrix = build_matrix(all_segments)
    csv_path = args.output_dir / f"kbo_re24_matrix_{args.year}.csv"
    summary_path = args.output_dir / f"kbo_re24_matrix_{args.year}_summary.json"
    write_csv(matrix, csv_path)
    summary = {
        "year": args.year, "kind_code": "R",
        "game_sno_start": f"{args.year}-03", "game_sno_end": f"{args.year}-10",
        "games_expected": games, "games_processed": games, "games_failed": 0, "failures": [],
        "total_state_segments": matrix["totalSegments"],
        "basic_break_even_threshold_by_outs": matrix["basicBreakEvenThresholdByOuts"],
        "cells": matrix["cells"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{games} 場，{matrix['totalSegments']} 個 state 區段\nCSV：{csv_path}\n摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
