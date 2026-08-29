"""驗證：從 Content 自由文字解析出的盜壘成功/失敗筆數，能否對上 CPBL 官方
box score（`BattingJson` 的 `StealBaseOKCnt`／`StealBaseFailCnt`）逐場逐隊的
統計總數。

背景：`find_2out_first_base.py` 的盜壘判讀（`is_steal_success`／`is_steal_failure`）
只鎖定「兩出局、僅一壘有人」這個情境，範圍比全場所有盜壘窄；本腳本改用同一套
Content 文字判讀邏輯的通用版本（不限出局數／壘包狀態），逐場逐隊加總，對照
CPBL 官方自己統計的盜壘成功/失敗數——這是跟研究範圍無關、只驗證「文字解析
邏輯本身準不準」的獨立查核，用官方另一組獨立統計的數字當基準。

用法：

    python validate_steal_parsing.py --year 2025 --start 1 --end 360

資料來源：直接讀已快取的 `data/raw/cpbl/*/game_*.json`（不重新對官網發請求）。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from cpbl_row_filters import remove_administrative_rows


# 逐球 Content 裡出現的盜壘描述樣式（見腳本開發時的抽樣統計）：
# - 成功盜二／三壘："一壘跑者X 盜壘上二壘。"／"二壘跑者X 盜壘上三壘。"
# - 雙盜壘時三壘跑者回本壘："三壘跑者X 雙盜壘回本壘得分。"
# - 盜壘刺（任一壘出局）："X壘跑者Y出局-盜壘刺 N人出局。"
# - 盜壘刺但因野手失誤反而安全上壘："X壘跑者Y 盜壘刺-因野手失誤進壘上N壘。"
#   CPBL 官方 box score 仍把這次算進 StealBaseFailCnt（跑者被判出局在先，
#   失誤是另一件事），因此也要算進 caught，不能因為文字裡出現「上二壘」
#   就誤判成成功盜壘（see STEAL_SUCCESS_PATTERN 只認「盜壘上」緊接壘包，
#   這裡中間隔著「刺-因野手失誤進」，不會誤觸發）。
#
# 跑者名字與動作描述之間的字數用 [^。]{0,15}? 卡住、不用 .{0,N}?：原住民
# 選手名字（如「吉力吉撈．鞏冠」）比一般漢字姓名長，字數上限抓太緊會漏配；
# 用「非句號」而非「任意字元」限制範圍，確保不會跨到下一個句子誤配。
STEAL_SUCCESS_PATTERN = re.compile(r"[一二三]壘跑者[^。]{0,15}?盜壘上[二三]壘")
STEAL_HOME_ON_DOUBLE_STEAL_PATTERN = re.compile(r"三壘跑者[^。]{0,15}?雙盜壘回本壘得分")
STEAL_CAUGHT_PATTERN = re.compile(r"[一二三]壘跑者[^。]{0,15}?出局-盜壘刺")
STEAL_CAUGHT_ON_ERROR_PATTERN = re.compile(r"[一二三]壘跑者[^。]{0,15}?盜壘刺-因野手失誤")


def count_parsed_steals(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """回傳 {VisitingHomeType: {"success": n, "caught": n}}，依 Content 文字判讀。"""
    counts: dict[str, dict[str, int]] = {}
    for row in remove_administrative_rows(rows):
        content = str(row.get("Content") or "")
        if "盜壘" not in content:
            continue
        side = str(row.get("VisitingHomeType") or "")
        bucket = counts.setdefault(side, {"success": 0, "caught": 0})
        bucket["success"] += len(STEAL_SUCCESS_PATTERN.findall(content))
        bucket["success"] += len(STEAL_HOME_ON_DOUBLE_STEAL_PATTERN.findall(content))
        bucket["caught"] += len(STEAL_CAUGHT_PATTERN.findall(content))
        bucket["caught"] += len(STEAL_CAUGHT_ON_ERROR_PATTERN.findall(content))
    return counts


def official_steal_totals(batting_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """回傳 {VisitingHomeType: {"success": n, "caught": n}}，來自官方 box score。"""
    totals: dict[str, dict[str, int]] = {}
    for row in batting_rows:
        side = str(row.get("VisitingHomeType") or "")
        bucket = totals.setdefault(side, {"success": 0, "caught": 0})
        bucket["success"] += int(row.get("StealBaseOKCnt") or 0)
        bucket["caught"] += int(row.get("StealBaseFailCnt") or 0)
    return totals


def compare_game(
    game_sno: int, parsed: dict[str, dict[str, int]], official: dict[str, dict[str, int]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for side in ("1", "2"):
        p = parsed.get(side, {"success": 0, "caught": 0})
        o = official.get(side, {"success": 0, "caught": 0})
        rows.append(
            {
                "gameSno": game_sno,
                "side": side,
                "parsedSuccess": p["success"],
                "officialSuccess": o["success"],
                "successDiff": p["success"] - o["success"],
                "parsedCaught": p["caught"],
                "officialCaught": o["caught"],
                "caughtDiff": p["caught"] - o["caught"],
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    fieldnames = [
        "gameSno", "side", "parsedSuccess", "officialSuccess", "successDiff",
        "parsedCaught", "officialCaught", "caughtDiff",
    ]
    with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    if not cache_dir.exists():
        raise SystemExit(f"{cache_dir} 不存在，請先執行 find_2out_first_base.py 建立快取")

    all_rows: list[dict[str, Any]] = []
    games_checked = 0
    for path in sorted(cache_dir.glob("game_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        live_raw = data.get("LiveLogJson")
        batting_raw = data.get("BattingJson")
        if not live_raw or not batting_raw:
            continue
        live_rows = json.loads(live_raw) if isinstance(live_raw, str) else live_raw
        batting_rows = json.loads(batting_raw) if isinstance(batting_raw, str) else batting_raw
        if not live_rows:
            continue
        game_sno = int(live_rows[0].get("GameSno") or 0)
        parsed = count_parsed_steals(live_rows)
        official = official_steal_totals(batting_rows)
        all_rows.extend(compare_game(game_sno, parsed, official))
        games_checked += 1

    csv_path = args.output_dir / f"cpbl_steal_parsing_validation_{tag}.csv"
    write_csv(all_rows, csv_path)

    total_parsed_success = sum(r["parsedSuccess"] for r in all_rows)
    total_official_success = sum(r["officialSuccess"] for r in all_rows)
    total_parsed_caught = sum(r["parsedCaught"] for r in all_rows)
    total_official_caught = sum(r["officialCaught"] for r in all_rows)
    mismatched_rows = [r for r in all_rows if r["successDiff"] != 0 or r["caughtDiff"] != 0]

    print(f"已核對 {games_checked} 場")
    print(f"盜壘成功：解析 {total_parsed_success} vs 官方 {total_official_success}")
    print(f"盜壘刺：解析 {total_parsed_caught} vs 官方 {total_official_caught}")
    print(f"不相符的（場次,隊伍）組合：{len(mismatched_rows)} / {len(all_rows)}")
    print(f"CSV：{csv_path}")

    worst = sorted(mismatched_rows, key=lambda r: abs(r["successDiff"]) + abs(r["caughtDiff"]), reverse=True)[:10]
    if worst:
        print("差異最大的 10 筆：")
        for r in worst:
            print(
                f"  GameSno={r['gameSno']} side={r['side']}: "
                f"success 解析{r['parsedSuccess']}/官方{r['officialSuccess']}（差{r['successDiff']:+d}）, "
                f"caught 解析{r['parsedCaught']}/官方{r['officialCaught']}（差{r['caughtDiff']:+d}）"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
