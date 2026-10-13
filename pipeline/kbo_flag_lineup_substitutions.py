"""同 flag_lineup_substitutions.py，資料來源換成 KBO。文字轉播沒有先發名單欄位，
用「每場、每側、每個棒次第一個出現的打者」當先發，之後同棒次換人就是代打／代換。
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

from kbo_find_2out_first_base import build_pa_records, iter_cached_games


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def starters_by_game(cache_dir: Path) -> dict[str, dict[tuple[str, int], str]]:
    """回傳 {GameSno: {(側, 棒次): 該場該棒次第一位打者 id}}"""
    result: dict[str, dict[tuple[str, int], str]] = {}
    for meta, rows in iter_cached_games(cache_dir):
        starters: dict[tuple[str, int], str] = {}
        for record in build_pa_records(rows):
            slot = record["lineup_slot"]
            if slot:
                starters.setdefault(("away" if record["is_top"] else "home", slot), record["batter_id"])
        result[str(meta["GameSno"])] = starters
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = args.year
    input_csv = args.input or Path("outputs") / f"kbo_decision_with_types_{tag}.csv"
    cache_dir = args.cache_dir or Path("data/raw/kbo") / tag
    output = args.output or Path("outputs") / f"kbo_decision_with_starter_flag_{tag}.csv"

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
