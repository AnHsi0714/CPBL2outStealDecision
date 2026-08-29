"""建立中職專屬 RE24（24 種 base-out state）得分期望值矩陣。

對齊計畫書 3.0／3.1 節的方法論：分析單位是「事件發生當下」，不是整個
半局或整個打席。做法：

1. 把每個半局的逐球紀錄切成連續的 base-out state 區段（出局數 × 8 種壘包
   組合），只要壘包或出局數一變就是新區段（涵蓋打席內盜壘造成的狀態切換）。
2. 每個區段的「起算比分」＝進入該區段前一刻（區段第一球事件發生前）的
   累積比分：區段內第一顆球取上一個區段最後一列的比分，半局第一個區段
   取該隊上一個半局結束時的比分。
3. 區段的「剩餘得分」＝該半局結束時的累積比分－起算比分。
4. 只計入 `half_is_complete` 判定為已打完的半局，排除雨天中止等不完整
   半局，避免低估得分期望值。
5. 依 (出局數, 壘包組合) 取平均，得到 24 格 RE24 矩陣。

沿用 `find_2out_first_base.py` 已驗證過的壘包/比分/半局完整性判定邏輯，
不重新發明一套規則。
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import CPBL_steal_getData
from find_2out_first_base import (
    DEFAULT_END,
    DEFAULT_KIND_CODE,
    DEFAULT_START,
    DEFAULT_YEAR,
    as_int,
    batting_score,
    deduplicate_schedule,
    half_is_complete,
    half_key,
    load_or_fetch_game,
    occupied,
    remove_administrative_rows,
)


BASE_STATE_LABELS = [
    "空壘",
    "一壘",
    "二壘",
    "一二壘",
    "三壘",
    "一三壘",
    "二三壘",
    "一二三壘",
]


def base_state_code(row: dict[str, Any]) -> int:
    """壘包組合編碼：bit0=一壘、bit1=二壘、bit2=三壘。"""
    first = 1 if occupied(row.get("FirstBase")) else 0
    second = 1 if occupied(row.get("SecondBase")) else 0
    third = 1 if occupied(row.get("ThirdBase")) else 0
    return first | (second << 1) | (third << 2)


def collect_state_segments(rows: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    """回傳這場比賽所有 (出局數, 壘包編碼, 該區段剩餘得分) 的觀測值。"""
    if not rows:
        return []

    half_indices: dict[tuple[int, str], list[int]] = {}
    for index, live_row in enumerate(rows):
        half_indices.setdefault(half_key(live_row), []).append(index)

    half_end_scores = {
        key: max(batting_score(rows[index], key[1]) for index in indices)
        for key, indices in half_indices.items()
    }

    segments: list[tuple[int, int, int]] = []
    for key, indices in half_indices.items():
        if not half_is_complete(key, half_indices, rows):
            continue
        inning, batting_side = key
        end_score = half_end_scores[key]
        prev_half_final_score = half_end_scores.get((inning - 1, batting_side), 0)

        prev_state: tuple[int, int] | None = None
        for position, row_index in enumerate(indices):
            live_row = rows[row_index]
            outs = as_int(live_row.get("OutCnt"), -1)
            if outs not in (0, 1, 2):
                continue
            state = (outs, base_state_code(live_row))
            if state == prev_state:
                continue
            baseline = (
                prev_half_final_score
                if position == 0
                else batting_score(rows[indices[position - 1]], batting_side)
            )
            segments.append((state[0], state[1], end_score - baseline))
            prev_state = state

    return segments


def build_matrix(segments: list[tuple[int, int, int]]) -> dict[str, Any]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for outs, base_code, remaining_runs in segments:
        buckets[(outs, base_code)].append(remaining_runs)

    cells = []
    for outs in (0, 1, 2):
        for base_code in range(8):
            values = buckets.get((outs, base_code), [])
            cells.append(
                {
                    "outs": outs,
                    "baseCode": base_code,
                    "baseLabel": BASE_STATE_LABELS[base_code],
                    "n": len(values),
                    "meanRE": round(mean(values), 4) if values else None,
                    "stdRE": round(pstdev(values), 4) if len(values) > 1 else None,
                }
            )

    def cell_mean(outs: int, base_code: int) -> float | None:
        values = buckets.get((outs, base_code))
        return mean(values) if values else None

    # 層次二的基礎損益兩平門檻，直接由本矩陣算出，作為與模擬結果交叉核對用。
    basic_thresholds: dict[str, float | None] = {}
    for outs in (0, 1, 2):
        re_first = cell_mean(outs, 1)  # 一壘有人
        re_second = cell_mean(outs, 2)  # 二壘有人
        basic_thresholds[str(outs)] = (
            round(re_first / re_second, 4)
            if re_first is not None and re_second not in (None, 0)
            else None
        )

    return {
        "cells": cells,
        "totalSegments": len(segments),
        "basicBreakEvenThresholdByOuts": basic_thresholds,
    }


def write_csv(matrix: dict[str, Any], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["Outs", "BaseCode", "BaseLabel", "N", "MeanRE", "StdRE"],
        )
        writer.writeheader()
        for cell in matrix["cells"]:
            writer.writerow(
                {
                    "Outs": cell["outs"],
                    "BaseCode": cell["baseCode"],
                    "BaseLabel": cell["baseLabel"],
                    "N": cell["n"],
                    "MeanRE": cell["meanRE"],
                    "StdRE": cell["stdRE"],
                }
            )
    temp_path.replace(path)


def write_summary(
    path: Path,
    args: argparse.Namespace,
    games_expected: int,
    games_processed: int,
    failures: list[dict[str, Any]],
    matrix: dict[str, Any],
) -> None:
    summary = {
        "year": args.year,
        "kind_code": args.kind_code,
        "game_sno_start": args.start,
        "game_sno_end": args.end,
        "games_expected": games_expected,
        "games_processed": games_processed,
        "games_failed": len(failures),
        "failures": failures,
        "total_state_segments": matrix["totalSegments"],
        "basic_break_even_threshold_by_outs": matrix["basicBreakEvenThresholdByOuts"],
        "cells": matrix["cells"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(path)


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
    all_segments: list[tuple[int, int, int]] = []
    failures: list[dict[str, Any]] = []
    processed = 0

    for position, game in enumerate(games, 1):
        game_sno = as_int(game.get("GameSno"))
        label = f"[{position}/{len(games)}] GameSno={game_sno}"
        try:
            data, fetched = load_or_fetch_game(
                game, cache_dir, args.refresh, max(1, args.retries)
            )
            raw = data.get("LiveLogJson")
            rows = (json.loads(raw) if isinstance(raw, str) else raw) if raw else []
            rows = remove_administrative_rows(rows)
            segments = collect_state_segments(rows)
            all_segments.extend(segments)
            processed += 1
            source = "官網" if fetched else "快取"
            print(f"{label}：{source}，{len(segments)} 個 state 區段")
            if fetched and position < len(games):
                time.sleep(max(0.0, args.delay) + random.uniform(0, max(0.0, args.jitter)))
        except Exception as error:
            print(f"{label}：失敗：{error}")
            failures.append({"GameSno": game_sno, "error": str(error)})

    matrix = build_matrix(all_segments)

    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    csv_path = args.output_dir / f"cpbl_re24_matrix_{tag}.csv"
    summary_path = args.output_dir / f"cpbl_re24_matrix_{tag}_summary.json"
    write_csv(matrix, csv_path)
    write_summary(summary_path, args, len(games), processed, failures, matrix)

    print(f"完成：{processed}/{len(games)} 場，{matrix['totalSegments']} 個 state 區段")
    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    if failures:
        print("仍有失敗場次；重跑同一指令會沿用成功場次快取並重試失敗場次。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
