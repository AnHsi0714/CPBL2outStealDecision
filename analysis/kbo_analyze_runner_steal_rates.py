"""KBO 版符合門檻的跑者名單，做法同 analyze_runner_steal_rates.py（逐棒次比對而非單一門檻）。

只計「一壘跑者盜二壘」（「1루주자 X : 도루로 2루까지 진루」成功、「도루실패아웃」失敗），不含雙盜壘、
無關心盜壘。單一賽季；跑者身分直接取敘述句裡的姓名，主鍵用 `球隊:姓名`（KBO 文字轉播沒有球員 ID）。
分級、門檻載入、排序全部沿用 analyze_runner_steal_rates.py。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from kbo_find_2out_first_base import iter_cached_games, steal_second_kind
from analyze_runner_steal_rates import (
    DEFAULT_MIN_ATTEMPTS,
    TIER_ALL_SLOTS,
    TIER_DEPENDS,
    TIER_INSUFFICIENT,
    TIER_NO_SLOTS,
    build_leaderboard,
    load_batter_types,
    load_thresholds,
    write_csv,
)

def collect_events(cache_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for meta, rows in iter_cached_games(cache_dir):
        for row in rows:
            kind = steal_second_kind(row)
            if kind is None:
                continue
            name = row["RawText"].split(" : ", 1)[0].split(" ", 1)[1]
            events.append({
                "GameSno": meta["GameSno"],
                "HitterAcnt": f"{row['BattingTeam']}:{name}",
                "HitterName": name,
                "Team": row["BattingTeam"],
                "Outcome": kind,
            })
    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--model-summary-json", type=Path)
    parser.add_argument("--batter-types-csv", type=Path)
    parser.add_argument("--min-attempts", type=int, default=DEFAULT_MIN_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = args.year
    cache_dir = args.cache_dir or Path("data/raw/kbo") / tag
    model_summary_json = args.model_summary_json or Path("outputs") / f"kbo_decision_model_{tag}_summary.json"
    batter_types_csv = args.batter_types_csv or Path("outputs") / f"kbo_batter_types_{tag}.csv"

    events = collect_events(cache_dir)
    thresholds = load_thresholds(model_summary_json)
    leaderboard = build_leaderboard(
        events, args.min_attempts, thresholds["bySlot"], thresholds["leagueMedian"],
        load_batter_types(batter_types_csv),
    )

    csv_path = args.output_dir / f"kbo_runner_steal_rates_{tag}.csv"
    json_path = args.output_dir / f"kbo_runner_steal_rates_{tag}.json"
    write_csv([
        {
            "HitterAcnt": r["hitterAcnt"], "HitterName": r["hitterName"], "Team": r["team"],
            "Attempts": r["attempts"], "Successes": r["successes"], "Failures": r["failures"],
            "SuccessRate": r["successRate"], "Tier": r["tier"],
            "QualifyingSlots": ",".join(str(s) for s in r["qualifyingSlots"]),
            "NonQualifyingSlots": ",".join(str(s) for s in r["nonQualifyingSlots"]),
            "TypicalLineupGroup": r["typicalLineupGroup"] or "", "PowerGroup": r["powerGroup"] or "",
            "PatienceGroup": r["patienceGroup"] or "", "OBPGroup": r["obpGroup"] or "",
            "ContactGroup": r["contactGroup"] or "", "TTOGroup": r["ttoGroup"] or "",
        }
        for r in leaderboard
    ], csv_path)

    tier_counts: dict[str, int] = defaultdict(int)
    for r in leaderboard:
        tier_counts[r["tier"]] += 1
    payload = {
        "year": args.year, "kindCode": "R",
        "gameSnoStart": f"{args.year}-03", "gameSnoEnd": f"{args.year}-10",
        "minAttempts": args.min_attempts, "thresholds": thresholds,
        "eventsTotal": len(events), "eventsUnresolved": 0, "unresolvedSamples": [],
        "tierCounts": dict(tier_counts), "runners": leaderboard,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"解析 {len(events)} 次一壘跑者盜二壘事件，跑者 {len(leaderboard)} 位")
    if thresholds["bySlot"]:
        print(f"逐棒次門檻範圍 {min(thresholds['bySlot'].values()):.1%} ~ {max(thresholds['bySlot'].values()):.1%}")
    print(f"{TIER_ALL_SLOTS} {tier_counts.get(TIER_ALL_SLOTS, 0)}／{TIER_DEPENDS} {tier_counts.get(TIER_DEPENDS, 0)}"
          f"／{TIER_NO_SLOTS} {tier_counts.get(TIER_NO_SLOTS, 0)}／{TIER_INSUFFICIENT} {tier_counts.get(TIER_INSUFFICIENT, 0)}")
    print(f"CSV：{csv_path}\nJSON：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
