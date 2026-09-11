"""RE 版「任一棒次都不建議跑」的跑者，換成 WPA 門檻後有多少人翻盤。

延伸自 README「WPA 版損益兩平門檻」一節的機制：晚局時「讓這個半局現在結束」
（換算對手視角的 V失敗）跟「打者繼續打、大機率還是出局收場」（V不跑）兩者
代價越來越接近，門檻公式的分子被壓縮，門檻因此比 RE 版低很多。這件事對
「哪些跑者夠格盜壘」有直接、可驗證的實務含意：RE 版逐棒次門檻全部落在
54–60% 這個窄帶，能把一個跑者判定成「任一棒次都不建議跑」的，本來就必須是
成功率明顯偏低的人；但 WPA 版第 4 局起的門檻只有 20–45%，同一批「RE 全棒次
不建議跑」的跑者，換算到晚局的 WPA 門檻，有多少人其實夠格盜壘？

只比對 RE 判定為 `任一棒次都不建議跑`（`analyze_runner_steal_rates.py` 的
`TIER_NO_SLOTS`）且已通過最低嘗試次數門檻的跑者。這批人正是「兩套判準最
可能吵架」的邊界樣本，任一棒次都可跑或視棒次而定的跑者換成 WPA 判準結論
不會變（本來就夠格）。WPA 門檻只取第 4–8 局，因為第 1–3 局的門檻點估計
本身不穩定（見 README「WPA 版損益兩平門檻」一節），拿不穩定的數字做「這位
跑者夠不夠格」的二元判定沒有意義。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from analyze_runner_steal_rates import TIER_NO_SLOTS, classify_slots


ROOT = Path(__file__).resolve().parent
RELIABLE_INNINGS = (4, 5, 6, 7, 8)


def load_re_never_go_runners(runner_csv: Path) -> list[dict[str, Any]]:
    with runner_csv.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return [row for row in rows if row["Tier"] == TIER_NO_SLOTS]


def load_wpa_inning_thresholds(bootstrap_json: Path) -> dict[int, float]:
    with bootstrap_json.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    thresholds = {}
    for row in data.get("by_inning", []):
        inning = row.get("inning")
        median = row.get("point_median")
        if inning in RELIABLE_INNINGS and median is not None:
            thresholds[inning] = median
    return thresholds


def build_rows(
    never_go_runners: list[dict[str, Any]], wpa_thresholds: dict[int, float]
) -> list[dict[str, Any]]:
    rows = []
    for runner in never_go_runners:
        success_rate = float(runner["SuccessRate"])
        qualifying, non_qualifying = classify_slots(success_rate, wpa_thresholds)
        rows.append(
            {
                "HitterAcnt": runner["HitterAcnt"],
                "HitterName": runner["HitterName"],
                "Team": runner["Team"],
                "Attempts": runner["Attempts"],
                "SuccessRate": success_rate,
                "WPA_QualifyingInnings": ",".join(str(i) for i in qualifying),
                "WPA_NonQualifyingInnings": ",".join(str(i) for i in non_qualifying),
                "ReclassifiedByWPA": bool(qualifying),
            }
        )
    rows.sort(key=lambda row: -row["SuccessRate"])
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--runner-csv", type=Path, help="預設讀 analyze_runner_steal_rates.py 的輸出")
    parser.add_argument("--wpa-bootstrap-json", type=Path, help="預設讀 bootstrap_wpa_threshold_ci.py 的輸出")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    runner_csv = args.runner_csv or Path("outputs") / f"cpbl_runner_steal_rates_{tag}.csv"
    wpa_bootstrap_json = args.wpa_bootstrap_json or Path("outputs") / f"cpbl_wpa_bootstrap_ci_{tag}.json"
    if not runner_csv.exists():
        raise SystemExit(f"找不到 {runner_csv}，請先執行 analyze_runner_steal_rates.py")
    if not wpa_bootstrap_json.exists():
        raise SystemExit(f"找不到 {wpa_bootstrap_json}，請先執行 bootstrap_wpa_threshold_ci.py")

    never_go_runners = load_re_never_go_runners(runner_csv)
    wpa_thresholds = load_wpa_inning_thresholds(wpa_bootstrap_json)
    rows = build_rows(never_go_runners, wpa_thresholds)

    reclassified = [row for row in rows if row["ReclassifiedByWPA"]]
    by_inning_qualify_count = {
        inning: sum(1 for row in rows if str(inning) in row["WPA_QualifyingInnings"].split(","))
        for inning in RELIABLE_INNINGS
    }

    summary = {
        "tag": tag,
        "wpa_thresholds_used": wpa_thresholds,
        "re_never_go_runner_count": len(rows),
        "reclassified_by_wpa_count": len(reclassified),
        "by_inning_qualify_count": by_inning_qualify_count,
    }

    output_csv = args.output_dir / f"cpbl_wpa_runner_reclassification_{tag}.csv"
    output_json = args.output_dir / f"cpbl_wpa_runner_reclassification_{tag}_summary.json"
    write_csv(rows, output_csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    temp_json = output_json.with_suffix(".json.tmp")
    temp_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_json.replace(output_json)

    print(f"{tag}：RE 版「任一棒次都不建議跑」共 {len(rows)} 人")
    print(f"其中 {len(reclassified)} 人（{len(reclassified)/len(rows)*100:.0f}%）在第 4–8 局至少一局的 WPA 門檻下夠格盜壘")
    print("逐局夠格人數：")
    for inning in RELIABLE_INNINGS:
        threshold = wpa_thresholds.get(inning)
        threshold_text = f"{threshold*100:.1f}%" if threshold is not None else "NA"
        print(f"  第{inning}局（門檻{threshold_text}）：{by_inning_qualify_count[inning]} 人")
    print(f"CSV：{output_csv}")
    print(f"摘要：{output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
