"""左右投對**跑者**的影響（計畫書第 4–6 週「左右投分析」延伸項）。

只看投手慣用手如何影響跑者盜二壘，**不涉及打者**：左投面對一壘跑者是正面朝向，
牽制視野好、起跑時機難抓。這影響的是跑者**跑不跑得掉**（實際成功率），
不是門檻本身——門檻由打者的打擊結果分布決定，跟投手是誰無關。

這個區分很重要：簡報上若把「面對左投門檻要調高」跟「面對左投比較難跑」混為一談，
會被問倒。正確說法是**門檻不動，是你達不達得到門檻在變**。

範圍與既有 `analyze_runner_steal_rates.py` 一致：只算「一壘跑者盜二壘」，
不含盜三壘、雙盜壘（那是另一種跑壘能力，混進來會稀釋這個問題本身）。
但**不限兩出局情境**——跑者能力與出局數無關，用全部壘上有人的球數才有足夠樣本
做逐跑者的左右投拆分（四季 2,228 次嘗試，遠多於兩出局子集的 772 次）。

牽制另外分兩種訊號統計：
- 牽制投球（`投手牽制一壘跑者`）：投手多常回頭壓制跑者
- 牽制出局（`一壘跑者…出局-牽制`）：真的把跑者抓掉；四季只有 83 次，樣本很薄

慣用手來源：`data/player_handedness.csv`（由 CPBL 官網球員頁「投打習慣」欄位建立，
以 Acnt 為主鍵，不用姓名 join）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cpbl_row_filters import remove_administrative_rows
from find_2out_first_base import (
    as_int,
    is_steal_failure,
    is_steal_success,
    occupied,
)
from analyze_runner_steal_rates import (
    load_team_names,
    load_thresholds,
    resolve_runner,
)

PICKOFF_THROW = "投手牽制一壘跑者"
PICKOFF_OUT = re.compile(r"一壘跑者.*出局-牽制")
DEFAULT_MIN_ATTEMPTS = 5

TIER_BOTH = "對左右投都可跑"
TIER_RHP_ONLY = "只建議對右投跑"
TIER_LHP_ONLY = "只建議對左投跑"
TIER_NEITHER = "對左右投都不建議"
TIER_INSUFFICIENT = "樣本不足"


def load_handedness(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as file:
        return {
            row["Acnt"]: row["Throws"]
            for row in csv.DictReader(file)
            if row["Throws"] in ("L", "R")
        }


def collect(
    cache_dir: Path, hands: dict[str, str], team_names: dict[int, dict[str, str]]
) -> tuple[dict[str, Counter[str]], list[dict[str, Any]], Counter[str]]:
    """回傳（聯盟層級 by 投手手別、逐次盜壘事件、略過原因計數）。"""
    league: dict[str, Counter[str]] = defaultdict(Counter)
    events: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    for path in sorted(cache_dir.glob("game_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("LiveLogJson")
        if not raw:
            continue
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not rows:
            continue
        rows = remove_administrative_rows(rows)
        game_sno = as_int(rows[0].get("GameSno"))
        game_teams = team_names.get(game_sno, {})

        for index, row in enumerate(rows):
            if not occupied(row.get("FirstBase")):
                continue
            throws = hands.get(str(row.get("PitcherAcnt") or ""))
            if throws is None:
                skipped["投手慣用手未知"] += 1
                continue
            content = str(row.get("Content") or "")
            bucket = league[throws]
            bucket["pitches_with_runner_on_first"] += 1
            if PICKOFF_THROW in content:
                bucket["pickoff_throws"] += 1
            if PICKOFF_OUT.search(content):
                bucket["pickoff_outs"] += 1

            if is_steal_failure(content):
                outcome = "failure"
            elif is_steal_success(content):
                outcome = "success"
            else:
                continue
            bucket["attempts"] += 1
            bucket["success" if outcome == "success" else "caught"] += 1

            batting_side = str(row.get("VisitingHomeType") or "")
            slot = as_int(row.get("FirstBase"), -1)
            if not (1 <= slot <= 9):
                skipped["FirstBase 非有效棒次"] += 1
                continue
            resolved = resolve_runner(rows, index, batting_side, slot)
            if resolved is None:
                skipped["找不到對應打席"] += 1
                continue
            runner_acnt, runner_name = resolved
            events.append(
                {
                    "GameSno": game_sno,
                    "RunnerAcnt": runner_acnt,
                    "RunnerName": runner_name,
                    "Team": game_teams.get(batting_side, ""),
                    "PitcherThrows": throws,
                    "Outcome": outcome,
                }
            )
    return league, events, skipped


def runner_table(
    events: list[dict[str, Any]],
    thresholds: dict[str, Any],
    min_attempts: int,
) -> list[dict[str, Any]]:
    """逐跑者：對左投／對右投各自的成功率，再分別跟逐棒次門檻比對。

    門檻隨下一棒棒次而變（這是本研究的核心發現），所以不比對單一中位數，
    而是看該跑者的成功率能過幾個棒次的門檻——對左投與對右投分開算。
    """
    by_slot: dict[int, float] = thresholds.get("bySlot", {})
    slots = sorted(by_slot)
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        entry = grouped.setdefault(
            event["RunnerAcnt"],
            {
                "RunnerAcnt": event["RunnerAcnt"],
                "RunnerName": event["RunnerName"],
                "Team": event["Team"],
                "counts": defaultdict(Counter),
            },
        )
        entry["Team"] = event["Team"] or entry["Team"]
        entry["counts"][event["PitcherThrows"]][event["Outcome"]] += 1

    rows: list[dict[str, Any]] = []
    for entry in grouped.values():
        counts = entry["counts"]
        record: dict[str, Any] = {
            "RunnerAcnt": entry["RunnerAcnt"],
            "RunnerName": entry["RunnerName"],
            "Team": entry["Team"],
        }
        clears: dict[str, int | None] = {}
        for hand in ("L", "R"):
            success = counts[hand]["success"]
            attempts = success + counts[hand]["failure"]
            rate = success / attempts if attempts else None
            label = "VsLHP" if hand == "L" else "VsRHP"
            record[f"{label}Attempts"] = attempts
            record[f"{label}Success"] = success
            record[f"{label}SuccessRate"] = rate
            if rate is None or attempts < min_attempts or not slots:
                clears[hand] = None
                record[f"{label}SlotsCleared"] = ""
            else:
                cleared = [s for s in slots if rate >= by_slot[s]]
                clears[hand] = len(cleared)
                record[f"{label}SlotsCleared"] = (
                    "/".join(str(s) for s in cleared) if cleared else "無"
                )
        total = sum(
            counts[h][o] for h in ("L", "R") for o in ("success", "failure")
        )
        record["TotalAttempts"] = total

        left, right = clears["L"], clears["R"]
        if left is None or right is None:
            record["Tier"] = TIER_INSUFFICIENT
        elif left > 0 and right > 0:
            record["Tier"] = TIER_BOTH
        elif right > 0:
            record["Tier"] = TIER_RHP_ONLY
        elif left > 0:
            record["Tier"] = TIER_LHP_ONLY
        else:
            record["Tier"] = TIER_NEITHER
        rows.append(record)

    rows.sort(key=lambda r: (-r["TotalAttempts"], r["RunnerName"]))
    return rows


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--model-summary-json", type=Path)
    parser.add_argument(
        "--handedness-csv", type=Path, default=Path("data/player_handedness.csv")
    )
    parser.add_argument("--min-attempts", type=int, default=DEFAULT_MIN_ATTEMPTS)
    parser.add_argument(
        "--pool-years",
        help=(
            "以逗號分隔的年份，合併多季做逐跑者分析（例：2023,2024,2025,2026）。"
            "單季拆左右投後多數跑者樣本不足（2025 為 103 人中 92 人不足），"
            "合併四季才有足夠人數；代價是跨季合併會蓋掉球員轉型或老化。"
            "門檻仍取 --year 指定球季的值。"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start < 1 or args.end < args.start:
        raise SystemExit("場次範圍錯誤：需滿足 1 <= start <= end")
    if args.min_attempts < 1:
        raise SystemExit("min-attempts 必須 >= 1")

    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    decision_csv = args.decision_csv or Path("outputs") / f"cpbl_2out_first_base_{tag}.csv"
    summary_json = (
        args.model_summary_json
        or Path("outputs") / f"cpbl_decision_model_{tag}_summary.json"
    )
    if not args.handedness_csv.exists():
        raise SystemExit(f"找不到慣用手對照表：{args.handedness_csv}")

    hands = load_handedness(args.handedness_csv)
    team_names = load_team_names(decision_csv) if decision_csv.exists() else {}
    thresholds = load_thresholds(summary_json)

    if args.pool_years:
        years = [int(y) for y in args.pool_years.split(",") if y.strip()]
        cache_dirs = [
            Path("data/raw/cpbl") / f"{year}_{args.kind_code}" for year in years
        ]
        missing = [str(d) for d in cache_dirs if not d.is_dir()]
        if missing:
            raise SystemExit(f"找不到快取目錄：{', '.join(missing)}")
        out_tag = f"{min(years)}-{max(years)}_{args.kind_code}_pooled"
    else:
        years = [args.year]
        cache_dirs = [cache_dir]
        out_tag = tag

    league: dict[str, Counter[str]] = defaultdict(Counter)
    events: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for directory in cache_dirs:
        part_league, part_events, part_skipped = collect(directory, hands, team_names)
        for hand, bucket in part_league.items():
            league[hand].update(bucket)
        events.extend(part_events)
        skipped.update(part_skipped)

    runners = runner_table(events, thresholds, args.min_attempts)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / f"cpbl_runner_handedness_{out_tag}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(runners[0].keys()))
        writer.writeheader()
        writer.writerows(runners)

    league_out = {}
    for hand in ("L", "R"):
        b = league[hand]
        pitches = b["pitches_with_runner_on_first"]
        league_out["LHP" if hand == "L" else "RHP"] = {
            "pitchesWithRunnerOnFirst": pitches,
            "attempts": b["attempts"],
            "success": b["success"],
            "caught": b["caught"],
            "successRate": rate(b["success"], b["attempts"]),
            "attemptRatePerPitch": rate(b["attempts"], pitches),
            "pickoffThrows": b["pickoff_throws"],
            "pickoffThrowRate": rate(b["pickoff_throws"], pitches),
            "pickoffOuts": b["pickoff_outs"],
            "pickoffOutRate": rate(b["pickoff_outs"], pitches),
        }

    tier_counts = Counter(r["Tier"] for r in runners)
    summary = {
        "years": years,
        "kind_code": args.kind_code,
        "pooled": bool(args.pool_years),
        "thresholds_from_year": args.year,
        "scope": "一壘跑者盜二壘，不限出局數；不含盜三壘與雙盜壘",
        "note": "投手慣用手影響的是實際成功率，不是門檻；門檻由打者決定",
        "min_attempts": args.min_attempts,
        "skipped": dict(skipped),
        "league_by_pitcher_hand": league_out,
        "runner_tier_counts": dict(tier_counts),
        "thresholds_by_slot": thresholds.get("bySlot", {}),
    }
    summary_path = args.output_dir / f"cpbl_runner_handedness_{out_tag}_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lhp, rhp = league_out["LHP"], league_out["RHP"]
    print(f"一壘有人球數：左投 {lhp['pitchesWithRunnerOnFirst']:,} / 右投 {rhp['pitchesWithRunnerOnFirst']:,}")
    print(
        f"盜二壘成功率：對左投 {lhp['successRate']*100:.1f}%（{lhp['attempts']} 次）"
        f" / 對右投 {rhp['successRate']*100:.1f}%（{rhp['attempts']} 次）"
    )
    print(
        f"每球嘗試率：對左投 {lhp['attemptRatePerPitch']*100:.2f}%"
        f" / 對右投 {rhp['attemptRatePerPitch']*100:.2f}%"
    )
    print(
        f"牽制投球率：左投 {lhp['pickoffThrowRate']*100:.2f}%"
        f" / 右投 {rhp['pickoffThrowRate']*100:.2f}%"
        f"；牽制出局：{lhp['pickoffOuts']} / {rhp['pickoffOuts']}"
    )
    print(f"跑者分級（{len(runners)} 人）：{dict(tier_counts)}")
    if skipped:
        print(f"略過：{dict(skipped)}")
    print(f"CSV：{csv_path}")
    print(f"摘要：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
