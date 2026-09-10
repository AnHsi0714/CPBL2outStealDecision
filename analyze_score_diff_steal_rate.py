"""分析「兩出局、一壘有人」情境下，盜壘嘗試率隨攻守分差如何變化。

計畫書第 4–6 週「限制與失效條件分析」待辦之一：大分差比賽（落後多分需要拚大局、
領先多分守方不在乎被盜）理論上會讓盜壘變得少見。與其憑棒球直覺寫死幾分的排除
門檻，這裡直接從既有決策樣本算出「盜壘嘗試率 vs. 分差」的實際分布，如果真的
需要排除極端分差，門檻由資料決定，不是猜的。

只讀 `find_2out_first_base.py` 產生的決策 CSV 與本機已快取的原始逐球 JSON
（`data/raw/cpbl/{year}_{kind_code}/game_*.json`），不重爬。分差採「決策當下
（兩出局、一壘有人狀態剛形成，盜壘/不跑事件尚未發生）打擊方分數 - 守備方分
數」，取用前一列的比分以避開事件列比分可能已更新的問題，做法與
`find_2out_first_base.py` 算 RE 基準分數（`before_state_score`）一致。
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

from find_2out_first_base import as_int, batting_score
from model_batter_decisions import load_raw_games


ATTEMPT_OUTCOMES = {"steal_success", "steal_failure"}


def score_diff_at_state(
    rows: list[dict[str, Any]], state_index: int, batting_side: str
) -> int | None:
    if not (0 <= state_index < len(rows)):
        return None
    opponent_side = "2" if batting_side == "1" else "1"
    reference_index = state_index - 1 if state_index > 0 else state_index
    own = batting_score(rows[reference_index], batting_side)
    opp = batting_score(rows[reference_index], opponent_side)
    return own - opp


def bucket_key(diff: int, cap: int) -> int:
    return max(-cap, min(cap, diff))


def bucket_label(key: int, cap: int) -> str:
    if key <= -cap:
        return f"落後{cap}+"
    if key < 0:
        return f"落後{-key}"
    if key == 0:
        return "平手"
    if key < cap:
        return f"領先{key}"
    return f"領先{cap}+"


def load_decisions(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--input", type=Path, default=None, help="預設讀 step 1 的決策 CSV")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--bucket-cap", type=int, default=5, help="分桶時的絕對分差上限")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_path = args.input or Path("outputs") / f"cpbl_2out_first_base_{tag}.csv"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"

    decisions = load_decisions(input_path)
    games = load_raw_games(cache_dir)

    diff_totals: Counter[int] = Counter()
    diff_attempts: Counter[int] = Counter()
    bucket_totals: Counter[int] = Counter()
    bucket_attempts: Counter[int] = Counter()
    missing = 0

    output_rows: list[dict[str, Any]] = []
    for decision in decisions:
        game_sno = as_int(decision.get("GameSno"))
        state_index = as_int(decision.get("StateRowIndex"), -1)
        batting_side = str(decision.get("VisitingHomeType") or "")
        rows = games.get(game_sno)
        diff = score_diff_at_state(rows, state_index, batting_side) if rows else None
        if diff is None:
            missing += 1
            continue

        outcome = str(decision.get("Outcome"))
        is_attempt = outcome in ATTEMPT_OUTCOMES
        key = bucket_key(diff, args.bucket_cap)

        diff_totals[diff] += 1
        bucket_totals[key] += 1
        if is_attempt:
            diff_attempts[diff] += 1
            bucket_attempts[key] += 1

        output_rows.append(
            {
                "GameSno": game_sno,
                "StateRowIndex": state_index,
                "ScoreDiffAtState": diff,
                "Outcome": outcome,
                "IsAttempt": is_attempt,
            }
        )

    if missing:
        print(f"警告：{missing} 筆決策找不到對應快取或分差，已略過")

    print(f"\n{tag}：{len(output_rows)} 筆決策計入分析（分差=打擊方分數-守備方分數，決策當下）\n")
    print(f"{'分差':>6} | {'樣本數':>6} | {'盜壘嘗試':>8} | {'嘗試率':>7}")
    for diff in sorted(diff_totals):
        total = diff_totals[diff]
        attempts = diff_attempts[diff]
        print(f"{diff:>6} | {total:>6} | {attempts:>8} | {attempts / total:>6.1%}")

    print(f"\n{'分桶':>8} | {'樣本數':>6} | {'盜壘嘗試':>8} | {'嘗試率':>7}")
    for key in sorted(bucket_totals):
        total = bucket_totals[key]
        attempts = bucket_attempts[key]
        label = bucket_label(key, args.bucket_cap)
        print(f"{label:>8} | {total:>6} | {attempts:>8} | {attempts / total:>6.1%}")

    output_path = args.output_dir / f"cpbl_score_diff_steal_rate_{tag}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"\n明細已寫出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
