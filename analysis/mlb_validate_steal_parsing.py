"""MLB 版盜壘解析對帳：從逐打席紀錄數出來的盜壘成功／盜壘失敗，跟 MLB 官方 boxscore 逐場逐隊對帳。

做法同 validate_steal_parsing.py：解析數＝Gumbo runners[] 裡 event 以 "Stolen Base" 開頭者（成功），
與 event 含 "Caught Stealing" 且 isOut 者（失敗，含牽制盜壘出局）；官方數＝boxscore teams.{away,home}.
teamStats.batting 的 stolenBases／caughtStealing。輸出欄位名稱與 CPBL 版 CSV 相同，報告載入器可直接讀。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.start_date}_{args.end_date}"
    cache_dir = args.cache_dir or Path("data/raw/mlb") / tag
    rows = []
    for path in sorted(cache_dir.glob("game_*.json")):
        feed = json.loads(path.read_text(encoding="utf-8"))
        box = feed["liveData"]["boxscore"]["teams"]
        for side, is_top in (("away", True), ("home", False)):
            batting = box[side]["teamStats"]["batting"]
            parsed_success = parsed_caught = 0
            for play in feed["liveData"]["plays"]["allPlays"]:
                if bool(play["about"]["isTopInning"]) != is_top:
                    continue
                for runner in play.get("runners", []):
                    event = runner["details"].get("event") or ""
                    if event.startswith("Stolen Base"):
                        parsed_success += 1
                    elif "Caught Stealing" in event and runner["movement"]["isOut"]:
                        parsed_caught += 1
            official_success = int(batting.get("stolenBases", 0))
            official_caught = int(batting.get("caughtStealing", 0))
            rows.append({
                "gameSno": path.stem.split("_")[-1], "side": side,
                "parsedSuccess": parsed_success, "officialSuccess": official_success,
                "parsedCaught": parsed_caught, "officialCaught": official_caught,
                "successDiff": parsed_success - official_success,
                "caughtDiff": parsed_caught - official_caught,
            })
    out = args.output_dir / f"mlb_steal_parsing_validation_{tag}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    mismatches = [r for r in rows if r["successDiff"] or r["caughtDiff"]]
    print(f"對帳 {len(rows)} 隊場：解析成功 {sum(r['parsedSuccess'] for r in rows)}／官方 {sum(r['officialSuccess'] for r in rows)}；"
          f"解析失敗 {sum(r['parsedCaught'] for r in rows)}／官方 {sum(r['officialCaught'] for r in rows)}；不一致 {len(mismatches)} 隊場")
    print(f"CSV：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
