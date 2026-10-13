"""同 flag_lineup_substitutions.py，資料來源換成 MLB。CPBL 版要掃逐球快取找每個棒次
第一次出現的打者才能判斷先發／代打；MLB 版更直接：Gumbo boxscore 的 battingOrder
本身就用尾碼區分先發(00)與代打序(01, 02, ...)，不必掃 play。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
from pathlib import Path
from typing import Any

from find_2out_first_base import as_int


def starters_by_game(cache_dir: Path) -> dict[str, dict[tuple[str, int], int]]:
    """回傳 {GamePk: {(側, 棒次): 該場該棒次先發打者 id}}"""
    result: dict[str, dict[tuple[str, int], int]] = {}
    for path in sorted(cache_dir.glob("game_*.json")):
        feed = json.loads(path.read_text(encoding="utf-8"))
        game_pk = path.stem.split("_")[-1]
        starters: dict[tuple[str, int], int] = {}
        for side in ("home", "away"):
            players = feed.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {}).get("players", {})
            for p in players.values():
                order = p.get("battingOrder")
                if order and int(order) % 100 == 0:
                    starters[(side, int(order) // 100)] = p["person"]["id"]
        result[game_pk] = starters
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.start_date}_{args.end_date}"
    input_csv = args.input or Path("outputs") / f"mlb_decision_with_types_{tag}.csv"
    cache_dir = args.cache_dir or Path("data/raw/mlb") / tag
    output = args.output or Path("outputs") / f"mlb_decision_with_starter_flag_{tag}.csv"

    starters = starters_by_game(cache_dir)

    with input_csv.open(encoding="utf-8-sig", newline="") as file:
        rows: list[dict[str, Any]] = list(csv.DictReader(file))

    for row in rows:
        game_pk = str(row["GamePk"])
        side = "away" if row["IsTopInning"] == "True" else "home"
        slot = as_int(row["HitterLineup"])
        starter_id = starters.get(game_pk, {}).get((side, slot))
        row["StarterHitterAcnt"] = starter_id or ""
        row["IsStarterInSlot"] = bool(starter_id) and str(starter_id) == row["HitterAcnt"]

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    is_starter = sum(row["IsStarterInSlot"] for row in rows)
    print(f"決策總數：{total}")
    print(f"棒次先發打者：{is_starter}（{is_starter/total:.1%}）")
    print(f"輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
