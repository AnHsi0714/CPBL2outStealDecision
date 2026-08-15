"""判定每筆決策當下，該棒次是先發打者還是已被代打換過。

規則：對每場比賽、每隊、每個棒次(1-9)，依出現順序找出第一位站上該棒次的打者視為「先發」；
決策當下若打者不是該場該棒次的第一人，記為「代打／換人後」。

輸出：在 cpbl_decision_with_types 上新增 IsStarterInSlot 欄位的合併檔。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from find_2out_first_base import as_int, half_key


def starters_by_game(cache_dir: Path) -> dict[int, dict[tuple[str, int], str]]:
    """回傳 {GameSno: {(VisitingHomeType, HitterLineup): 該場該棒次第一位打者的 HitterAcnt}}"""
    result: dict[int, dict[tuple[str, int], str]] = {}
    for path in sorted(cache_dir.glob("game_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("LiveLogJson")
        rows = json.loads(raw) if isinstance(raw, str) and raw else []
        if not rows:
            continue
        game_sno = as_int(rows[0].get("GameSno"))
        first_occupant: dict[tuple[str, int], str] = {}
        for row in rows:
            side = str(row.get("VisitingHomeType") or "")
            slot = as_int(row.get("HitterLineup"))
            hitter = str(row.get("HitterAcnt") or "")
            if not side or not (1 <= slot <= 9) or not hitter:
                continue
            key = (side, slot)
            if key not in first_occupant:
                first_occupant[key] = hitter
        result[game_sno] = first_occupant
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    input_csv = args.input or Path("outputs") / f"cpbl_decision_with_types_{tag}.csv"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    output = args.output or Path("outputs") / f"cpbl_decision_with_starter_flag_{tag}.csv"

    starters = starters_by_game(cache_dir)

    with input_csv.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    for row in rows:
        game_sno = as_int(row["GameSno"])
        side = row["VisitingHomeType"]
        slot = as_int(row["HitterLineup"])
        starter_id = starters.get(game_sno, {}).get((side, slot))
        row["StarterHitterAcnt"] = starter_id or ""
        row["IsStarterInSlot"] = bool(starter_id) and starter_id == row["HitterAcnt"]

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    is_starter = sum(row["IsStarterInSlot"] for row in rows)
    print(f"決策總數：{total}")
    print(f"棒次先發打者：{is_starter}（{is_starter/total:.1%}）")
    print(f"代打／換人後：{total - is_starter}（{(total-is_starter)/total:.1%}）")

    by_slot: dict[int, list[bool]] = {}
    for row in rows:
        slot = as_int(row["HitterLineup"])
        by_slot.setdefault(slot, []).append(row["IsStarterInSlot"])
    print("\n逐棒次先發比例：")
    for slot in sorted(by_slot):
        values = by_slot[slot]
        print(f"  第{slot}棒：n={len(values)}，先發比例={sum(values)/len(values):.1%}")

    print(f"\n輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
