"""具體球員應用：列出符合門檻的跑者名單（計畫書「第 4–6 週」待辦項）。

只計入計畫書範圍界定的「一壘跑者盜二壘」（沿用 find_2out_first_base.py 的
is_steal_success／is_steal_failure），不含盜三壘、雙盜壘——那是另一種跑壘能力，
混進來會稀釋「這位跑者盜二壘準不準」這個問題本身要回答的東西。

刻意只用單一賽季（--year）的資料，不跨季合併：球員可能轉型或老化，教練現在該不該
派他跑，該看「這一季」的實際表現，而不是被歷史多季平均稀釋掉的長期數字。

球員身分以 HitterAcnt 為主鍵解析（沿用計畫書「建立球員與棒次對照表」的原則，不用
姓名 join）：盜壘事件列的 FirstBase 欄位在事件當下就是跑者所在棒次（1–9，見
find_2out_first_base.py／model_batter_decisions.py 對這個欄位的既有觀察與用法），
往回找同一半局、同棒次最近一次有 HitterAcnt 的打席列，取得該跑者的真實身分。

「門檻」不是單一數字：計畫書 3.1／3.2 節的核心發現正是「門檻隨下一棒棒次而變」
（見 cpbl_decision_model_*_summary.json 的 by_hitter_lineup，逐棒次 1–9 各自的
損益兩平門檻中位數）。如果這裡把跑者的成功率拿去比對單一一個全季中位數，等於
把「門檻會隨打者變動」這個研究本身的結論丟掉，退化成一個跟球員類型無關的假判定。
因此本腳本改成逐棒次比對：每位跑者拿他自己的季成功率，去對照 1–9 棒各自的門檻，
標出「這位跑者站上一壘時，換到哪些棒次值得跑、哪些不值得」——判斷永遠是「這位
跑者 × 現在是第幾棒在打擊」的組合，不是跑者一個人就能決定的單一標籤。

用法：

    python analyze_runner_steal_rates.py --year 2025 --start 1 --end 360
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cpbl_row_filters import remove_administrative_rows
from find_2out_first_base import as_int, is_steal_failure, is_steal_success

ROOT = Path(__file__).resolve().parent
DEFAULT_MIN_ATTEMPTS = 5


def resolve_runner(
    rows: list[dict[str, Any]], event_index: int, batting_side: str, slot: int
) -> tuple[str, str] | None:
    """把盜壘事件列的棒次（FirstBase）解回真正的打者身分。

    正常情況一定能往回找到：這個跑者能站上一壘，代表他在同一半局稍早已經完成
    一次打席上壘，那次打席的列一定在事件列之前。往前找不到才退而求其次往後找，
    這只在資料本身有缺漏時才會發生。
    """
    for index in range(event_index, -1, -1):
        row = rows[index]
        if (
            str(row.get("VisitingHomeType") or "") == batting_side
            and as_int(row.get("HitterLineup")) == slot
            and row.get("HitterAcnt")
        ):
            return str(row["HitterAcnt"]), str(row.get("HitterName") or "")
    for index in range(event_index + 1, len(rows)):
        row = rows[index]
        if (
            str(row.get("VisitingHomeType") or "") == batting_side
            and as_int(row.get("HitterLineup")) == slot
            and row.get("HitterAcnt")
        ):
            return str(row["HitterAcnt"]), str(row.get("HitterName") or "")
    return None


def load_team_names(decision_csv: Path) -> dict[int, dict[str, str]]:
    """從既有的兩出局決策 CSV 取得 GameSno -> {側別: 球隊名}，不必另外呼叫官網賽程 API。"""
    teams: dict[int, dict[str, str]] = {}
    if not decision_csv.exists():
        return teams
    with decision_csv.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            game_sno = as_int(row.get("GameSno"))
            teams.setdefault(
                game_sno,
                {"1": row.get("VisitingTeam") or "", "2": row.get("HomeTeam") or ""},
            )
    return teams


def collect_events(
    cache_dir: Path, team_names: dict[int, dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
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
            content = str(row.get("Content") or "")
            if is_steal_failure(content):
                outcome = "failure"
            elif is_steal_success(content):
                outcome = "success"
            else:
                continue

            batting_side = str(row.get("VisitingHomeType") or "")
            slot = as_int(row.get("FirstBase"), -1)
            if not (1 <= slot <= 9):
                unresolved.append(
                    {"GameSno": game_sno, "rowIndex": index, "reason": "FirstBase 非有效棒次"}
                )
                continue
            resolved = resolve_runner(rows, index, batting_side, slot)
            if resolved is None:
                unresolved.append(
                    {"GameSno": game_sno, "rowIndex": index, "reason": "找不到對應打席"}
                )
                continue
            hitter_acnt, hitter_name = resolved
            events.append(
                {
                    "GameSno": game_sno,
                    "HitterAcnt": hitter_acnt,
                    "HitterName": hitter_name,
                    "Team": game_teams.get(batting_side, ""),
                    "Outcome": outcome,
                }
            )
    return events, unresolved


TIER_ALL_SLOTS = "任一棒次都可跑"
TIER_DEPENDS = "視下一棒棒次而定"
TIER_NO_SLOTS = "任一棒次都不建議跑"
TIER_NO_THRESHOLD = "無門檻可比對"
TIER_INSUFFICIENT = "樣本不足"
TIER_RANK = {
    TIER_ALL_SLOTS: 0,
    TIER_DEPENDS: 1,
    TIER_NO_SLOTS: 2,
    TIER_NO_THRESHOLD: 3,
    TIER_INSUFFICIENT: 4,
}


def classify_slots(
    success_rate: float, slot_thresholds: dict[int, float]
) -> tuple[list[int], list[int]]:
    qualifying = sorted(slot for slot, t in slot_thresholds.items() if success_rate >= t)
    non_qualifying = sorted(slot for slot, t in slot_thresholds.items() if success_rate < t)
    return qualifying, non_qualifying


def load_batter_types(path: Path) -> dict[str, dict[str, str]]:
    """跑者本人的固定球員類型標籤（前段/後段棒次型＋長打/選球/上壘/接觸/TTO 五組），
    跟這份名單的門檻判定（逐棒次比對）是兩件事——判定看的是「換了誰在打擊」，
    這裡的標籤看的是「這個跑者自己平常是什麼樣的打者」，純供辨識/參考用。
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {row["HitterAcnt"]: row for row in csv.DictReader(file)}


def build_leaderboard(
    events: list[dict[str, Any]],
    min_attempts: int,
    slot_thresholds: dict[int, float],
    league_median: float | None,
    batter_types: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event["HitterAcnt"]].append(event)

    rows: list[dict[str, Any]] = []
    for hitter_acnt, items in grouped.items():
        successes = sum(1 for item in items if item["Outcome"] == "success")
        failures = sum(1 for item in items if item["Outcome"] == "failure")
        attempts = successes + failures
        success_rate = successes / attempts if attempts else None
        # 球員季中若轉隊，以出現在最大 GameSno 那場的球隊當作目前所屬球隊。
        last_team = max(items, key=lambda item: item["GameSno"])["Team"]

        qualifying_slots: list[int] = []
        non_qualifying_slots: list[int] = []
        if attempts < min_attempts:
            tier = TIER_INSUFFICIENT
        elif not slot_thresholds:
            tier = TIER_NO_THRESHOLD
        else:
            qualifying_slots, non_qualifying_slots = classify_slots(success_rate, slot_thresholds)
            if not non_qualifying_slots:
                tier = TIER_ALL_SLOTS
            elif not qualifying_slots:
                tier = TIER_NO_SLOTS
            else:
                tier = TIER_DEPENDS

        type_row = batter_types.get(hitter_acnt)
        row_out: dict[str, Any] = {
            "hitterAcnt": hitter_acnt,
            "hitterName": items[0]["HitterName"],
            "team": last_team,
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
            "successRate": success_rate,
            "qualifyingSlots": qualifying_slots,
            "nonQualifyingSlots": non_qualifying_slots,
            "tier": tier,
            # 供快速對照用；判定本身不看這個單一數字，見上方模組說明。
            "vsLeagueMedian": (
                None if success_rate is None or league_median is None
                else success_rate - league_median
            ),
            # 跑者自己的固定球員類型（前段/後段棒次型＋長打/選球/上壘/接觸/TTO），
            # 跟上面的門檻判定無關，純供辨識這位跑者本身是什麼類型的打者。
            "batterTypeQualified": type_row is not None,
        }
        for group_key, source_key in (
            ("typicalLineupGroup", "PrimaryLineupGroup"),
            ("powerGroup", "PowerGroup"),
            ("patienceGroup", "PatienceGroup"),
            ("obpGroup", "OBPGroup"),
            ("contactGroup", "ContactGroup"),
            ("ttoGroup", "TTOGroup"),
        ):
            row_out[group_key] = type_row[source_key] if type_row and type_row.get(source_key) else None
        rows.append(row_out)
    rows.sort(
        key=lambda row: (
            TIER_RANK.get(row["tier"], 9),
            -(row["successRate"] or 0.0),
            -row["attempts"],
        )
    )
    return rows


def load_thresholds(summary_json: Path) -> dict[str, Any]:
    if not summary_json.exists():
        return {"leagueMedian": None, "bySlot": {}}
    summary = json.loads(summary_json.read_text(encoding="utf-8-sig"))
    by_lineup = summary.get("by_hitter_lineup", {})
    by_slot = {
        int(slot): v["median_break_even_rate_in_0_1"]
        for slot, v in by_lineup.items()
        if v.get("median_break_even_rate_in_0_1") is not None
    }
    return {
        "leagueMedian": summary.get("median_break_even_rate_in_0_1"),
        "bySlot": by_slot,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError(f"{path} 沒有資料")
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--model-summary-json", type=Path)
    parser.add_argument("--batter-types-csv", type=Path)
    parser.add_argument("--min-attempts", type=int, default=DEFAULT_MIN_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_attempts < 1:
        raise SystemExit("min-attempts 必須 >= 1")
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    cache_dir = args.cache_dir or Path("data/raw/cpbl") / f"{args.year}_{args.kind_code}"
    if not cache_dir.exists():
        raise SystemExit(f"{cache_dir} 不存在，請先執行 find_2out_first_base.py 建立快取")

    decision_csv = args.decision_csv or ROOT / "outputs" / f"cpbl_2out_first_base_{tag}.csv"
    model_summary_json = (
        args.model_summary_json or ROOT / "outputs" / f"cpbl_decision_model_{tag}_summary.json"
    )
    batter_types_csv = args.batter_types_csv or ROOT / "outputs" / f"cpbl_batter_types_{tag}.csv"

    team_names = load_team_names(decision_csv)
    events, unresolved = collect_events(cache_dir, team_names)
    thresholds = load_thresholds(model_summary_json)
    batter_types = load_batter_types(batter_types_csv)
    leaderboard = build_leaderboard(
        events, args.min_attempts, thresholds["bySlot"], thresholds["leagueMedian"], batter_types
    )

    csv_path = args.output_dir / f"cpbl_runner_steal_rates_{tag}.csv"
    json_path = args.output_dir / f"cpbl_runner_steal_rates_{tag}.json"
    write_csv(
        [
            {
                "HitterAcnt": row["hitterAcnt"],
                "HitterName": row["hitterName"],
                "Team": row["team"],
                "Attempts": row["attempts"],
                "Successes": row["successes"],
                "Failures": row["failures"],
                "SuccessRate": row["successRate"],
                "Tier": row["tier"],
                "QualifyingSlots": ",".join(str(s) for s in row["qualifyingSlots"]),
                "NonQualifyingSlots": ",".join(str(s) for s in row["nonQualifyingSlots"]),
                "TypicalLineupGroup": row["typicalLineupGroup"] or "",
                "PowerGroup": row["powerGroup"] or "",
                "PatienceGroup": row["patienceGroup"] or "",
                "OBPGroup": row["obpGroup"] or "",
                "ContactGroup": row["contactGroup"] or "",
                "TTOGroup": row["ttoGroup"] or "",
            }
            for row in leaderboard
        ],
        csv_path,
    )

    tier_counts: dict[str, int] = defaultdict(int)
    for row in leaderboard:
        tier_counts[row["tier"]] += 1

    payload = {
        "year": args.year,
        "kindCode": args.kind_code,
        "gameSnoStart": args.start,
        "gameSnoEnd": args.end,
        "minAttempts": args.min_attempts,
        "thresholds": thresholds,
        "eventsTotal": len(events),
        "eventsUnresolved": len(unresolved),
        "unresolvedSamples": unresolved[:20],
        "tierCounts": dict(tier_counts),
        "runners": leaderboard,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    temp = json_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(json_path)

    print(f"已從 {len(list(cache_dir.glob('game_*.json')))} 場快取解析 {len(events)} 次一壘跑者盜二壘事件")
    if unresolved:
        print(f"警告：{len(unresolved)} 次事件無法解析出跑者身分，已記錄在摘要 JSON 的 unresolvedSamples")
    if thresholds["bySlot"]:
        slot_range = f"{min(thresholds['bySlot'].values()):.1%} ~ {max(thresholds['bySlot'].values()):.1%}"
        print(f"門檻：逐棒次（1–9）門檻範圍 {slot_range}（全季中位數 {thresholds['leagueMedian']:.1%} 僅供參考，不作為判定依據）")
    else:
        print("門檻：找不到 cpbl_decision_model summary 的逐棒次門檻，無法比對")
    print(
        f"跑者數：{len(leaderboard)}"
        f"（{TIER_ALL_SLOTS} {tier_counts.get(TIER_ALL_SLOTS, 0)}"
        f"／{TIER_DEPENDS} {tier_counts.get(TIER_DEPENDS, 0)}"
        f"／{TIER_NO_SLOTS} {tier_counts.get(TIER_NO_SLOTS, 0)}"
        f"／{TIER_INSUFFICIENT} {tier_counts.get(TIER_INSUFFICIENT, 0)}）"
    )
    with_type = sum(row["batterTypeQualified"] for row in leaderboard)
    print(f"跑者球員類型標籤：{with_type}／{len(leaderboard)} 位有資料（其餘打席數 < 100，無法分組）")
    print(f"CSV：{csv_path}")
    print(f"JSON：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
