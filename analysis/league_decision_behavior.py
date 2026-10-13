"""跨聯盟（MLB／KBO）教練實際盜壘行為分析：嘗試率與成功率如何隨「分差」「棒次」變化。

CPBL 版對應 analyze_score_diff_steal_rate.py／analyze_score_diff_threshold_sensitivity.py 與
analyze_steal_timing.py 的棒次層次，但那幾支直接掃 CPBL 原始逐球 JSON。這裡改讀兩份已經產生的
決策 CSV（RE 版決策模型：有棒次與 RE 門檻；WPA 版決策模型：有 ScoreDiffAtState 與 WPA 門檻），
用 (GamePk, 局, 上下半) join，所以 MLB 與 KBO 共用同一支，不必各自解析原始資料。

輸出兩張表：
1. 分差桶（落後 3+ … 領先 3+）：決策數、嘗試數、嘗試率、成功率、RE 門檻中位數、WPA 門檻中位數。
   用來檢驗 CPBL 版結論「極端分差樣本對整體門檻沒有實質影響」在其他聯盟是否成立，以及
   分差大時 WPA 門檻與 RE 門檻是否分叉。
2. 棒次（1–9）：決策數、嘗試數、嘗試率、成功率，並對嘗試率是否隨棒次不同做卡方獨立性檢定，
   檢驗教練實際盜壘頻率是否隨保留效應代價（見 analyze_retention_contribution.py）調整。

用法：python analysis/league_decision_behavior.py mlb 2025-03-15_2025-10-10
      python analysis/league_decision_behavior.py kbo 2025
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import csv
import sys
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import chi2_contingency

DIFF_CAP = 3


def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def key_of(row: dict[str, str]) -> tuple[str, str, str]:
    return row["GamePk"], row["InningSeq"], row["IsTopInning"]


def floats(rows: list[dict[str, str]], column: str) -> list[float]:
    values = []
    for row in rows:
        raw = row.get(column)
        if raw not in (None, ""):
            value = float(raw)
            if 0 <= value <= 1:
                values.append(value)
    return values


def diff_label(bucket: int) -> str:
    if bucket <= -DIFF_CAP:
        return f"落後{DIFF_CAP}+"
    if bucket < 0:
        return f"落後{-bucket}"
    if bucket == 0:
        return "平手"
    if bucket < DIFF_CAP:
        return f"領先{bucket}"
    return f"領先{DIFF_CAP}+"


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    attempts = [r for r in rows if r["Outcome"] in ("steal_success", "steal_failure")]
    successes = sum(1 for r in attempts if r["Outcome"] == "steal_success")
    re_values = floats(rows, "BreakEvenSuccessRate_RE")
    wpa_values = floats(rows, "BreakEvenSuccessRate_WPA")
    return {
        "decisions": len(rows),
        "attempts": len(attempts),
        "attemptRate": len(attempts) / len(rows) if rows else None,
        "successRate": successes / len(attempts) if attempts else None,
        "medianThresholdRE": median(re_values) if re_values else None,
        "medianThresholdWPA": median(wpa_values) if wpa_values else None,
    }


def main() -> int:
    league, tag = sys.argv[1], sys.argv[2]
    out = Path("outputs")
    wpa_rows = load(out / f"{league}_wpa_decision_model_{tag}.csv")
    re_rows = {key_of(r): r for r in load(out / f"{league}_decision_model_{tag}.csv")}

    joined = []
    for row in wpa_rows:
        re_row = re_rows.get(key_of(row))
        if re_row is None:
            continue
        joined.append({**row, "HitterLineup": re_row["HitterLineup"]})

    by_diff: dict[int, list[dict[str, str]]] = defaultdict(list)
    by_slot: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in joined:
        by_diff[max(-DIFF_CAP, min(DIFF_CAP, int(row["ScoreDiffAtState"])))].append(row)
        by_slot[int(row["HitterLineup"])].append(row)

    diff_table = {diff_label(b): summarize(by_diff[b]) for b in sorted(by_diff)}
    slot_table = {str(s): summarize(by_slot[s]) for s in sorted(by_slot)}

    contingency = [
        [slot_table[s]["attempts"], slot_table[s]["decisions"] - slot_table[s]["attempts"]]
        for s in slot_table
    ]
    chi2, p_value, dof, _ = chi2_contingency(contingency)
    result = {
        "league": league, "tag": tag, "joinedDecisions": len(joined),
        "byScoreDiff": diff_table, "byLineupSlot": slot_table,
        "attemptRateByLineupChiSquare": {"chi2": chi2, "dof": dof, "p": p_value},
    }
    path = out / f"{league}_decision_behavior_{tag}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{league} {tag}：join {len(joined)} 筆決策")
    print("分差桶 | 決策 | 嘗試 | 嘗試率 | 成功率 | RE門檻 | WPA門檻")
    for label, s in diff_table.items():
        print(f"  {label:6s} | {s['decisions']:5d} | {s['attempts']:4d} | {s['attemptRate']:.1%} | "
              f"{(s['successRate'] or 0):.1%} | {(s['medianThresholdRE'] or 0):.1%} | {(s['medianThresholdWPA'] or 0):.1%}")
    print("棒次 | 決策 | 嘗試 | 嘗試率 | 成功率")
    for slot, s in slot_table.items():
        print(f"  {slot} | {s['decisions']:5d} | {s['attempts']:4d} | {s['attemptRate']:.1%} | {(s['successRate'] or 0):.1%}")
    print(f"嘗試率隨棒次不同的卡方檢定：chi2={chi2:.2f} dof={dof} p={p_value:.3g}")
    print(f"輸出：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
