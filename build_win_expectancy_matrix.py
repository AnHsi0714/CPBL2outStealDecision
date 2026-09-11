"""建立中職專屬 WE（win expectancy）勝率矩陣：狀態 -> 進攻方最終獲勝機率。

對齊計畫書第 213 項待辦：第 7–8 局盜壘決策應改以勝率增值（WPA）而非得分期望值
（RE24）為判準，因為 RE 不看比分／局數情境，沒辦法回答「落後 2 分的第 8 局」
跟「平手的第 3 局」該不該用同一套門檻。做法比照 `build_re24_matrix.py`：

1. 沿用同一套「半局切成連續 base-out state 區段」邏輯（壘包或出局數一變就是
   新區段）。
2. 每個區段額外記錄「當下分差」（進攻方分數－守備方分數，用區段起算那一刻
   的比分，跟 RE24 算剩餘得分的起算點一致）與「這個半局最終是誰贏」。
3. 依 (局數 bucket, 攻守方, 分差 bucket, 出局數, 壘包組合) 取平均勝負結果
   （勝=1、和=0.5、負=0），得到勝率矩陣。

比分與勝負判定**完全從 LiveLogJson 逐球紀錄推回，不查 GameDetailJson 的
box score 總分欄位**——跟 CLAUDE.md「得分歸屬起算點」的既有原則一致（一律
用逐球紀錄，不用聚合過的比分欄位）。CPBL 例行賽有極少數比賽因局數上限規則
戰成和局，記為 0.5；只有偵測到最後一個半局確實打完（沿用 `half_is_complete`
的完整性判定）的比賽，才會被計入勝負樣本，避免收錄到還在進行中或擷取中斷
的場次。

跟 RE24 矩陣不同，WE 需要盡量多樣本才撐得住格子數（5 局數桶 × 2 攻守方 ×
11 分差桶 × 3 出局數 × 8 壘包組合 = 2640 格，遠多於 RE24 的 24 格），因此
預設一次合併四個已快取球季（2023–2026），用 `--seasons` 可覆寫或縮小範圍。
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
from build_re24_matrix import BASE_STATE_LABELS, base_state_code
from find_2out_first_base import (
    as_int,
    batting_score,
    deduplicate_schedule,
    half_is_complete,
    half_key,
    load_or_fetch_game,
    remove_administrative_rows,
)


DEFAULT_SEASONS = [
    "2023:A:1:300",
    "2024:A:1:360",
    "2025:A:1:360",
    "2026:A:1:240",
]

SCORE_DIFF_CAP = 5
INNING_BUCKETS = ["1-6", "7", "8", "9+"]
BATTING_SIDE_LABELS = {"1": "客隊進攻", "2": "主隊進攻"}


def inning_bucket(inning: int) -> str:
    if inning <= 6:
        return "1-6"
    if inning == 7:
        return "7"
    if inning == 8:
        return "8"
    return "9+"


def score_diff_bucket(diff: int) -> int:
    return max(-SCORE_DIFF_CAP, min(SCORE_DIFF_CAP, diff))


def score_diff_label(bucket: int) -> str:
    if bucket <= -SCORE_DIFF_CAP:
        return f"落後{SCORE_DIFF_CAP}+"
    if bucket < 0:
        return f"落後{-bucket}"
    if bucket == 0:
        return "平手"
    if bucket < SCORE_DIFF_CAP:
        return f"領先{bucket}"
    return f"領先{SCORE_DIFF_CAP}+"


class SeasonSpec:
    __slots__ = ("year", "kind_code", "start", "end")

    def __init__(self, year: int, kind_code: str, start: int, end: int) -> None:
        self.year = year
        self.kind_code = kind_code
        self.start = start
        self.end = end

    @property
    def tag(self) -> str:
        return f"{self.year}_{self.kind_code}_{self.start}-{self.end}"


def parse_season_spec(spec: str) -> SeasonSpec:
    parts = spec.split(":")
    if len(parts) != 4:
        raise SystemExit(f"--seasons 格式須為 year:kind_code:start:end，收到：{spec}")
    year_text, kind_code, start_text, end_text = parts
    try:
        return SeasonSpec(int(year_text), kind_code, int(start_text), int(end_text))
    except ValueError as error:
        raise SystemExit(f"--seasons 解析失敗：{spec}（{error}）") from error


def game_final_scores(rows: list[dict[str, Any]]) -> tuple[int, int] | None:
    """從最後一列逐球紀錄回推最終比分；沒有資料回傳 None。"""
    if not rows:
        return None
    last_row = rows[-1]
    return as_int(last_row.get("VisitingScore")), as_int(last_row.get("HomeScore"))


def collect_state_segments(
    rows: list[dict[str, Any]],
) -> list[tuple[str, str, int, int, int, float]]:
    """回傳這場比賽所有 (局數bucket, 攻守方, 分差bucket, 出局數, 壘包編碼, 勝負結果) 觀測值。"""
    if not rows:
        return []

    half_indices: dict[tuple[int, str], list[int]] = {}
    for index, live_row in enumerate(rows):
        half_indices.setdefault(half_key(live_row), []).append(index)

    last_key = half_key(rows[-1])
    if not half_is_complete(last_key, half_indices, rows):
        # 整場比賽最後一個半局沒打完：擷取中斷或比賽仍在進行，無法判定勝負。
        return []

    final_scores = game_final_scores(rows)
    if final_scores is None:
        return []
    final_visiting, final_home = final_scores
    if final_visiting > final_home:
        winner_side = "1"
    elif final_home > final_visiting:
        winner_side = "2"
    else:
        winner_side = None  # 和局

    half_end_scores = {
        key: max(batting_score(rows[index], key[1]) for index in indices)
        for key, indices in half_indices.items()
    }

    segments: list[tuple[str, str, int, int, int, float]] = []
    for key, indices in half_indices.items():
        if not half_is_complete(key, half_indices, rows):
            continue
        inning, batting_side = key
        fielding_side = "2" if batting_side == "1" else "1"
        prev_half_final_score = half_end_scores.get((inning - 1, batting_side), 0)
        outcome = 0.5 if winner_side is None else (1.0 if winner_side == batting_side else 0.0)

        prev_state: tuple[int, int] | None = None
        for position, row_index in enumerate(indices):
            live_row = rows[row_index]
            outs = as_int(live_row.get("OutCnt"), -1)
            if outs not in (0, 1, 2):
                continue
            state = (outs, base_state_code(live_row))
            if state == prev_state:
                continue
            own_baseline = (
                prev_half_final_score
                if position == 0
                else batting_score(rows[indices[position - 1]], batting_side)
            )
            opp_score = as_int(
                live_row.get("HomeScore" if fielding_side == "2" else "VisitingScore")
            )
            diff = own_baseline - opp_score
            segments.append(
                (
                    inning_bucket(inning),
                    batting_side,
                    score_diff_bucket(diff),
                    state[0],
                    state[1],
                    outcome,
                )
            )
            prev_state = state

    return segments


def build_matrix(
    segments: list[tuple[str, str, int, int, int, float]],
) -> dict[str, Any]:
    buckets: dict[tuple[str, str, int, int, int], list[float]] = defaultdict(list)
    for bucket_inning, batting_side, diff_bucket, outs, base_code, outcome in segments:
        buckets[(bucket_inning, batting_side, diff_bucket, outs, base_code)].append(outcome)

    cells = []
    for bucket_inning in INNING_BUCKETS:
        for batting_side in ("1", "2"):
            for diff_bucket in range(-SCORE_DIFF_CAP, SCORE_DIFF_CAP + 1):
                for outs in (0, 1, 2):
                    for base_code in range(8):
                        values = buckets.get(
                            (bucket_inning, batting_side, diff_bucket, outs, base_code), []
                        )
                        cells.append(
                            {
                                "inningBucket": bucket_inning,
                                "battingSide": batting_side,
                                "battingSideLabel": BATTING_SIDE_LABELS[batting_side],
                                "scoreDiffBucket": diff_bucket,
                                "scoreDiffLabel": score_diff_label(diff_bucket),
                                "outs": outs,
                                "baseCode": base_code,
                                "baseLabel": BASE_STATE_LABELS[base_code],
                                "n": len(values),
                                "winRate": round(mean(values), 4) if values else None,
                                "stdWinRate": round(pstdev(values), 4) if len(values) > 1 else None,
                            }
                        )

    return {"cells": cells, "totalSegments": len(segments)}


def write_csv(matrix: dict[str, Any], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    fieldnames = [
        "InningBucket", "BattingSide", "BattingSideLabel", "ScoreDiffBucket",
        "ScoreDiffLabel", "Outs", "BaseCode", "BaseLabel", "N", "WinRate", "StdWinRate",
    ]
    with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for cell in matrix["cells"]:
            writer.writerow(
                {
                    "InningBucket": cell["inningBucket"],
                    "BattingSide": cell["battingSide"],
                    "BattingSideLabel": cell["battingSideLabel"],
                    "ScoreDiffBucket": cell["scoreDiffBucket"],
                    "ScoreDiffLabel": cell["scoreDiffLabel"],
                    "Outs": cell["outs"],
                    "BaseCode": cell["baseCode"],
                    "BaseLabel": cell["baseLabel"],
                    "N": cell["n"],
                    "WinRate": cell["winRate"],
                    "StdWinRate": cell["stdWinRate"],
                }
            )
    temp_path.replace(path)


def write_summary(
    path: Path,
    seasons: list[SeasonSpec],
    games_expected: int,
    games_processed: int,
    games_skipped_incomplete: int,
    failures: list[dict[str, Any]],
    matrix: dict[str, Any],
) -> None:
    summary = {
        "seasons": [
            {"year": s.year, "kind_code": s.kind_code, "start": s.start, "end": s.end}
            for s in seasons
        ],
        "score_diff_cap": SCORE_DIFF_CAP,
        "inning_buckets": INNING_BUCKETS,
        "games_expected": games_expected,
        "games_processed": games_processed,
        "games_skipped_incomplete": games_skipped_incomplete,
        "games_failed": len(failures),
        "failures": failures,
        "total_state_segments": matrix["totalSegments"],
        "cells": matrix["cells"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        action="append",
        default=None,
        help="格式 year:kind_code:start:end，可重複指定；預設合併四個已快取球季",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="每次成功請求後至少等待秒數")
    parser.add_argument("--jitter", type=float, default=1.5, help="額外隨機等待秒數上限")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true", help="忽略快取並重新抓取")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/cpbl"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--output-tag",
        default="2023-2026_A_combined",
        help="輸出檔名用的標籤，預設代表四季合併",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    season_specs = [parse_season_spec(s) for s in (args.seasons or DEFAULT_SEASONS)]
    for spec in season_specs:
        if spec.start < 1 or spec.end < spec.start:
            raise SystemExit(f"場次範圍錯誤：{spec.tag}")

    all_segments: list[tuple[str, str, int, int, int, float]] = []
    failures: list[dict[str, Any]] = []
    games_expected_total = 0
    games_processed_total = 0
    games_skipped_incomplete = 0

    for spec in season_specs:
        expected = spec.end - spec.start + 1
        games_expected_total += expected
        cache_dir = args.cache_dir / f"{spec.year}_{spec.kind_code}"

        # 已快取的場次不需要打官網賽程 API 就能重建 game_meta（load_or_fetch_game
        # 只有真的要發網路請求時才會用到 GameDate 等欄位）；只有快取缺漏時才需要
        # 賽程資料，且賽程 API 打不通時仍讓已快取場次照常處理，不整批中斷。
        cached_numbers = {
            as_int(path.stem.split("_")[-1])
            for path in cache_dir.glob("game_*.json")
        } if cache_dir.exists() else set()
        wanted_numbers = set(range(spec.start, spec.end + 1))
        missing_numbers = sorted(wanted_numbers - cached_numbers)

        games: list[dict[str, Any]] = [
            {"GameSno": n, "Year": spec.year, "KindCode": spec.kind_code}
            for n in sorted(wanted_numbers & cached_numbers)
        ]
        if missing_numbers:
            try:
                schedule = CPBL_steal_getData.get_schedule(spec.year, spec.kind_code)
                schedule_games = deduplicate_schedule(
                    game
                    for game in schedule
                    if spec.start <= as_int(game.get("GameSno")) <= spec.end
                    and as_int(game.get("GameSno")) in missing_numbers
                )
                games.extend(schedule_games)
                still_missing = sorted(
                    set(missing_numbers) - {as_int(g.get("GameSno")) for g in schedule_games}
                )
                if still_missing:
                    print(f"[{spec.tag}] 警告：賽程也缺少 {len(still_missing)} 個 GameSno：{still_missing}")
            except Exception as error:
                print(
                    f"[{spec.tag}] 警告：{len(missing_numbers)} 場沒有本機快取，"
                    f"且賽程 API 無法連線（{error}），這些場次將略過"
                )
        games.sort(key=lambda g: as_int(g.get("GameSno")))
        print(f"[{spec.tag}] 找到 {len(games)}/{expected} 場（快取 {len(cached_numbers & wanted_numbers)} 場），開始處理")
        for position, game in enumerate(games, 1):
            game_sno = as_int(game.get("GameSno"))
            label = f"[{spec.tag} {position}/{len(games)}] GameSno={game_sno}"
            try:
                data, fetched = load_or_fetch_game(
                    game, cache_dir, args.refresh, max(1, args.retries)
                )
                raw = data.get("LiveLogJson")
                rows = (json.loads(raw) if isinstance(raw, str) else raw) if raw else []
                rows = remove_administrative_rows(rows)
                segments = collect_state_segments(rows)
                if not segments and rows:
                    games_skipped_incomplete += 1
                    print(f"{label}：跳過（最後半局未完整或無法判定勝負）")
                else:
                    all_segments.extend(segments)
                    games_processed_total += 1
                    source = "官網" if fetched else "快取"
                    print(f"{label}：{source}，{len(segments)} 個 state 區段")
                if fetched and position < len(games):
                    time.sleep(max(0.0, args.delay) + random.uniform(0, max(0.0, args.jitter)))
            except Exception as error:
                print(f"{label}：失敗：{error}")
                failures.append({"season": spec.tag, "GameSno": game_sno, "error": str(error)})

    matrix = build_matrix(all_segments)

    csv_path = args.output_dir / f"cpbl_win_expectancy_matrix_{args.output_tag}.csv"
    summary_path = args.output_dir / f"cpbl_win_expectancy_matrix_{args.output_tag}_summary.json"
    write_csv(matrix, csv_path)
    write_summary(
        summary_path,
        season_specs,
        games_expected_total,
        games_processed_total,
        games_skipped_incomplete,
        failures,
        matrix,
    )

    print(
        f"完成：{games_processed_total}/{games_expected_total} 場（另有 {games_skipped_incomplete} 場因半局未完整跳過），"
        f"{matrix['totalSegments']} 個 state 區段"
    )
    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    if failures:
        print("仍有失敗場次；重跑同一指令會沿用成功場次快取並重試失敗場次。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
