"""MLB 版左右投對跑者盜二壘成功率的影響，做法同 analyze_pitcher_handedness.py 的總體層次。

只看投手慣用手如何改變「跑者盜二壘的實際成功率」，不涉及打者，也不改變損益兩平門檻
（門檻由打者結果分布決定，模型裡完全沒有用到投手；見 CLAUDE.md「左右投：必須分清楚的兩件事」）。
投手慣用手取自 Gumbo gameData.players[ID<id>].pitchHand.code，每個盜壘事件的投手取該 play 的
matchup.pitcher。範圍：一壘跑者盜二壘（Stolen Base 2B／Caught Stealing 2B／Pickoff Caught Stealing 2B），
不限出局數與壘包狀態（有一壘跑者起跑盜二壘的全部情況）。逐跑者拆分（需要跨季合併才夠樣本）：同一位跑者對左投與
右投都至少 min-attempts 次嘗試才列出。

用法：python analysis/mlb_analyze_pitcher_handedness.py 2023-03-15_2023-10-10 2024-03-15_2024-10-10 ...
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from scipy.stats import fisher_exact

STEAL_SECOND_EVENTS = ("Stolen Base 2B", "Caught Stealing 2B", "Pickoff Caught Stealing 2B")
MIN_ATTEMPTS_PER_HAND = 5


def collect(cache_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted(cache_dir.glob("game_*.json")):
        feed = json.loads(path.read_text(encoding="utf-8"))
        players = feed.get("gameData", {}).get("players", {})
        for play in feed.get("liveData", {}).get("plays", {}).get("allPlays", []):
            pitcher_id = play.get("matchup", {}).get("pitcher", {}).get("id")
            hand = players.get(f"ID{pitcher_id}", {}).get("pitchHand", {}).get("code")
            for runner in play.get("runners", []):
                movement = runner.get("movement", {})
                event = runner.get("details", {}).get("event") or ""
                if movement.get("start") != "1B" or event not in STEAL_SECOND_EVENTS or hand not in ("L", "R"):
                    continue
                person = runner["details"]["runner"]
                events.append({
                    "runner": str(person.get("id")), "name": person.get("fullName", ""),
                    "hand": hand, "success": not movement.get("isOut"),
                                })
    return events


def split_table(events: list[dict[str, Any]]) -> dict[str, Any]:
    table: dict[str, Any] = {}
    for hand in ("L", "R"):
        subset = [e for e in events if e["hand"] == hand]
        wins = sum(e["success"] for e in subset)
        table[hand] = {"attempts": len(subset), "successes": wins,
                       "successRate": wins / len(subset) if subset else None}
    a, b = table["L"], table["R"]
    odds, p_value = fisher_exact([[a["successes"], a["attempts"] - a["successes"]],
                                  [b["successes"], b["attempts"] - b["successes"]]])
    table["fisherOddsRatioLvsR"], table["fisherP"] = odds, p_value
    return table


def main() -> int:
    tags = sys.argv[1:]
    all_events: list[dict[str, Any]] = []
    per_season: dict[str, Any] = {}
    for tag in tags:
        events = collect(Path("data/raw/mlb") / tag)
        per_season[tag] = split_table(events)
        all_events.extend(events)

    pooled = split_table(all_events)
    by_runner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in all_events:
        by_runner[event["runner"]].append(event)
    runner_rows = []
    for runner, items in by_runner.items():
        left = [e for e in items if e["hand"] == "L"]
        right = [e for e in items if e["hand"] == "R"]
        if len(left) < MIN_ATTEMPTS_PER_HAND or len(right) < MIN_ATTEMPTS_PER_HAND:
            continue
        runner_rows.append({
            "runner": runner, "name": items[0]["name"],
            "attemptsVsL": len(left), "successRateVsL": sum(e["success"] for e in left) / len(left),
            "attemptsVsR": len(right), "successRateVsR": sum(e["success"] for e in right) / len(right),
        })
    runner_rows.sort(key=lambda r: r["successRateVsR"] - r["successRateVsL"], reverse=True)

    result = {"tags": tags, "pooled": pooled, "perSeason": per_season,
              "minAttemptsPerHand": MIN_ATTEMPTS_PER_HAND, "runnersWithBothHands": runner_rows}
    out = Path("outputs") / "mlb_pitcher_handedness_pooled.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def line(label: str, t: dict[str, Any]) -> str:
        return (f"{label}：左投 {t['L']['successes']}/{t['L']['attempts']} = {t['L']['successRate']:.1%}　"
                f"右投 {t['R']['successes']}/{t['R']['attempts']} = {t['R']['successRate']:.1%}　"
                f"Fisher p={t['fisherP']:.3g}")

    for tag, table in per_season.items():
        print(line(tag, table))
    print(line("四季合併", pooled))
    print(f"同時對左右投都有 >= {MIN_ATTEMPTS_PER_HAND} 次嘗試的跑者：{len(runner_rows)} 位")
    print(f"輸出：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
