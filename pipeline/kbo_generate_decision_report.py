"""同 generate_decision_report.py，資料來源換成 KBO。共用 payload 產生的通用部分，只有 compact_case
與欄位名稱相關（KBO 球員主鍵是 `球隊:姓名`）。KBO 官網沒有可對帳的官方盜壘統計，所以沒有
「盜壘文字判讀 vs 官方統計」區塊（載入器找不到檔案時會略過）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from generate_decision_report import (
    ROOT,
    STYLE_PATH,
    SCRIPT_PATH,
    TEMPLATE_PATH,
    as_float,
    average,
    build_segments,
    encode_cases,
    load_batter_types,
    load_re24_validation,
    load_runner_qualification,
    load_steal_validation,
    load_team_decisions,
)


def compact_case(row: dict[str, str], index: int, batter_types: dict[str, dict[str, str]]) -> dict[str, Any]:
    numeric_keys = (
        "ProfilePA", "ModelP_1B", "ModelP_2B", "ModelP_3B", "ModelP_HR", "ModelP_BB_HBP",
        "ModelP_REACH", "ModelP_OUT", "ModelVSuccess", "ModelVFailure", "ModelVNoSteal",
        "ModelVIfBatterOut", "RetentionValue", "ConditionalOutCostNoSteal",
        "ExpectedOutPenaltyNoSteal", "BreakEvenSuccessRate",
    )
    data: dict[str, Any] = {
        "id": index,
        "game": row["GameId"],
        "date": row["GameDate"],
        "inning": int(row["InningSeq"]),
        "team": row["BattingTeam"],
        "away": row["AwayTeam"],
        "home": row["HomeTeam"],
        "hitter": row["BatterName"],
        "lineup": int(row["HitterLineup"]),
        "runner": row.get("RunnerOnFirstId", ""),
        "pitcher": row.get("PitcherName", ""),
        "actual": row["Outcome"],
        "simulations": int(row["Simulations"]),
        "thresholdStatus": row["ThresholdStatus"],
    }
    for key in numeric_keys:
        value = as_float(row, key)
        data[key] = None if value is None else round(value, 6)

    type_row = batter_types.get(row.get("HitterAcnt", ""))
    data["batterTypeQualified"] = type_row is not None
    for group_key, source_key in (
        ("typicalLineupGroup", "PrimaryLineupGroup"), ("powerGroup", "PowerGroup"),
        ("patienceGroup", "PatienceGroup"), ("obpGroup", "OBPGroup"),
        ("contactGroup", "ContactGroup"), ("ttoGroup", "TTOGroup"),
    ):
        data[group_key] = type_row[source_key] if type_row and type_row.get(source_key) else None
    return data


def build_payload(rows, summary, comparison=None, re24_validation=None, steal_validation=None,
                   team_decisions=None, runner_qualification=None, batter_types=None) -> dict[str, Any]:
    outcome_counts = {"steal_success": 0, "steal_failure": 0, "no_steal": 0}
    for row in rows:
        outcome_counts[row.get("Outcome", "")] = outcome_counts.get(row.get("Outcome", ""), 0) + 1

    valid_thresholds = [
        value for row in rows
        if (value := as_float(row, "BreakEvenSuccessRate")) is not None and 0 <= value <= 1
    ]
    cases = [compact_case(row, index, batter_types or {}) for index, row in enumerate(rows)]
    threshold_median = median(valid_thresholds)
    default_case = min(
        range(len(cases)),
        key=lambda i: abs((cases[i]["BreakEvenSuccessRate"] or threshold_median) - threshold_median),
    )

    v_success = average(rows, "ModelVSuccess")
    v_failure = average(rows, "ModelVFailure")
    v_no_steal = average(rows, "ModelVNoSteal")
    aggregate_threshold = (v_no_steal - v_failure) / (v_success - v_failure)

    return {
        "meta": {
            "league": "KBO",
            "year": int(summary["year"]),
            "startDate": f"{summary['year']}-03",
            "endDate": f"{summary['year']}-10",
            "games": int(summary["games_with_raw_data"]),
            "samples": len(rows),
            "completedPA": int(summary["completed_pa_for_profiles"]),
            "batters": int(summary["batter_profiles"]),
            "simulations": int(summary["simulations_per_context"]),
            "priorPA": float(summary["prior_pa"]),
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "aggregate": {
            "vSuccess": round(v_success, 6), "vFailure": round(v_failure, 6),
            "vNoSteal": round(v_no_steal, 6), "successGain": round(v_success - v_no_steal, 6),
            "failureCost": round(v_no_steal - v_failure, 6),
            "aggregateThreshold": round(aggregate_threshold, 6),
            "medianThreshold": round(threshold_median, 6),
            "retentionValue": round(average(rows, "RetentionValue"), 6),
            "conditionalOutCost": round(average(rows, "ConditionalOutCostNoSteal"), 6),
            "expectedOutPenalty": round(average(rows, "ExpectedOutPenaltyNoSteal"), 6),
            "outcomes": outcome_counts,
        },
        "defaultCase": default_case,
        "cases": encode_cases(cases),
        "segments": build_segments(comparison),
        "validation": {"re24": re24_validation, "steal": steal_validation},
        "teamDecisions": team_decisions,
        "runnerQualification": runner_qualification,
    }


def generate_report(model_csv, summary_json, output, comparison_json=None, re24_validation_json=None,
                     steal_validation_csv=None, team_decisions_json=None,
                     runner_qualification_json=None, batter_types_csv=None) -> dict[str, Any]:
    with model_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Model CSV has no rows: {model_csv}")
    with summary_json.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)

    comparison = None
    if comparison_json is not None and comparison_json.exists():
        comparison = json.loads(comparison_json.read_text(encoding="utf-8-sig"))
    re24_validation = load_re24_validation(re24_validation_json) if re24_validation_json else None
    steal_validation = load_steal_validation(steal_validation_csv) if steal_validation_csv else None
    team_decisions = load_team_decisions(team_decisions_json) if team_decisions_json else None
    runner_qualification = (
        load_runner_qualification(runner_qualification_json) if runner_qualification_json else None
    )
    batter_types = load_batter_types(batter_types_csv) if batter_types_csv else {}

    payload = build_payload(rows, summary, comparison, re24_validation, steal_validation,
                             team_decisions, runner_qualification, batter_types)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = template.replace("/*__STYLES__*/", STYLE_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("/*__COMMON_CSS__*/", (ROOT / "templates" / "report_common.css").read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("/*__COMMON__*/", (ROOT / "templates" / "report_common.js").read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("/*__SCRIPT__*/", SCRIPT_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("__REPORT_DATA__", payload_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--model-csv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--comparison-json", type=Path)
    parser.add_argument("--re24-validation-json", type=Path)
    parser.add_argument("--steal-validation-csv", type=Path)
    parser.add_argument("--team-decisions-json", type=Path)
    parser.add_argument("--runner-qualification-json", type=Path)
    parser.add_argument("--batter-types-csv", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = args.year
    model_csv = args.model_csv or ROOT / "outputs" / f"kbo_decision_model_{tag}.csv"
    summary_json = args.summary_json or ROOT / "outputs" / f"kbo_decision_model_{tag}_summary.json"
    comparison_json = args.comparison_json or ROOT / "outputs" / f"kbo_group_comparison_{tag}.json"
    re24_validation_json = args.re24_validation_json or ROOT / "outputs" / f"kbo_re24_validation_{tag}_summary.json"
    steal_validation_csv = args.steal_validation_csv or ROOT / "outputs" / f"kbo_steal_parsing_validation_{tag}.csv"
    team_decisions_json = args.team_decisions_json or ROOT / "outputs" / f"kbo_team_decisions_{tag}.json"
    runner_qualification_json = (
        args.runner_qualification_json or ROOT / "outputs" / f"kbo_runner_steal_rates_{tag}.json"
    )
    batter_types_csv = args.batter_types_csv or ROOT / "outputs" / f"kbo_batter_types_{tag}.csv"
    output = args.output or ROOT / "reports" / f"kbo-steal-decision-{tag}.html"
    payload = generate_report(
        model_csv, summary_json, output, comparison_json, re24_validation_json,
        steal_validation_csv, team_decisions_json, runner_qualification_json, batter_types_csv,
    )
    print(f"Wrote {output} with {payload['meta']['samples']} cases; "
          f"median threshold={payload['aggregate']['medianThreshold']:.3%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
