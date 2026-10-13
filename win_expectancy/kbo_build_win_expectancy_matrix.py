"""建立 KBO 版 WE（win expectancy）勝率矩陣，方法與輸出格式對齊 build_win_expectancy_matrix.py。

資料來源是 kbo_find_2out_first_base.py 解析的文字轉播事件列（data/raw/kbo/{年}/*.html）。KBO 沒有
累積比分欄位，得分一律數事件（跑者列「홈인／득점」、打者列「홈런」），比分與勝負都由此推回；
同分算和局（0.5，跟 CPBL 版一致，KBO 例行賽有 12 局後的和局）。每個 base-out state 區段記錄
「區段起算當下」的分差與整場勝負。預設合併 2023–2026 四季。
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
from kbo_find_2out_first_base import base_code, iter_cached_games, row_runs

DEFAULT_SEASONS = ["2023", "2024", "2025", "2026"]


def collect_game_segments(rows: list[dict[str, Any]]) -> list[tuple[str, str, int, int, int, float]]:
    totals = {"top": 0, "bottom": 0}
    for row in rows:
        totals[row["HalfInning"]] += row_runs(row)
    if totals["top"] == totals["bottom"]:
        winner = None
    else:
        winner = "top" if totals["top"] > totals["bottom"] else "bottom"

    segments: list[tuple[str, str, int, int, int, float]] = []
    cumulative = {"top": 0, "bottom": 0}
    previous_half: tuple[int, str] | None = None
    previous_state: tuple[int, int] | None = None
    for row in rows:
        half_key = (row["Inning"], row["HalfInning"])
        if half_key != previous_half:
            previous_half, previous_state = half_key, None
        own = row["HalfInning"]
        opp = "bottom" if own == "top" else "top"
        if row["Outs"] in (0, 1, 2):
            state = (row["Outs"], base_code(row))
            if state != previous_state:
                outcome = 0.5 if winner is None else (1.0 if winner == own else 0.0)
                segments.append((
                    inning_bucket(row["Inning"]), "1" if own == "top" else "2",
                    score_diff_bucket(cumulative[own] - cumulative[opp]), state[0], state[1], outcome,
                ))
                previous_state = state
        cumulative[own] += row_runs(row)
    return segments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS, help="球季年份，對應 data/raw/kbo/{年}/")
    parser.add_argument("--cache-root", type=Path, default=Path("data/raw/kbo"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--output-tag", default="2023-2026_R_combined")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_segments: list[tuple[str, str, int, int, int, float]] = []
    games_processed = 0
    season_entries = []
    for year in args.seasons:
        cache_dir = args.cache_root / year
        if not cache_dir.exists():
            raise SystemExit(f"{cache_dir} 不存在")
        for _meta, rows in iter_cached_games(cache_dir):
            all_segments.extend(collect_game_segments(rows))
            games_processed += 1
        season_entries.append({"year": year, "kind_code": "R", "start": f"{year}-03", "end": f"{year}-10"})
        print(f"[{year}] 累計 {games_processed} 場、{len(all_segments)} 個區段")

    matrix = build_matrix(all_segments)
    csv_path = args.output_dir / f"kbo_win_expectancy_matrix_{args.output_tag}.csv"
    summary_path = args.output_dir / f"kbo_win_expectancy_matrix_{args.output_tag}_summary.json"
    write_csv(matrix, csv_path)
    summary = {
        "seasons": season_entries,
        "score_diff_cap": SCORE_DIFF_CAP,
        "inning_buckets": INNING_BUCKETS,
        "games_expected": games_processed,
        "games_processed": games_processed,
        "games_skipped_incomplete": 0,
        "games_failed": 0,
        "failures": [],
        "total_state_segments": matrix["totalSegments"],
        "cells": matrix["cells"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{games_processed} 場，{matrix['totalSegments']} 個區段")
    print(f"CSV：{csv_path}\n摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
