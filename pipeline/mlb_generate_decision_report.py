"""同 generate_decision_report.py，資料來源換成 MLB。共用 payload 產生的通用部分
（build_segments、各驗證檔案載入、average/as_float），只有欄位名稱
相關（CPBL 用 GameSno/VisitingTeam，MLB 用 GamePk/AwayTeam）需要換。
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
    load_re24_validation,
    load_runner_qualification,
    load_steal_validation,
    load_team_decisions,
)


def build_payload(rows, summary, comparison=None, re24_validation=None, steal_validation=None,
                   team_decisions=None, runner_qualification=None) -> dict[str, Any]:
    outcome_counts = {"steal_success": 0, "steal_failure": 0, "no_steal": 0}
    for row in rows:
        outcome_counts[row.get("Outcome", "")] = outcome_counts.get(row.get("Outcome", ""), 0) + 1

    valid_thresholds = [
        value for row in rows
        if (value := as_float(row, "BreakEvenSuccessRate")) is not None and 0 <= value <= 1
    ]
    threshold_median = median(valid_thresholds)

    v_success = average(rows, "ModelVSuccess")
    v_failure = average(rows, "ModelVFailure")
    v_no_steal = average(rows, "ModelVNoSteal")
    aggregate_threshold = (v_no_steal - v_failure) / (v_success - v_failure)

    return {
        "meta": {
            "league": "MLB",
            "startDate": summary["start_date"],
            "endDate": summary["end_date"],
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
        "segments": build_segments(comparison),
        "validation": {"re24": re24_validation, "steal": steal_validation},
        "teamDecisions": team_decisions,
        "runnerQualification": runner_qualification,
    }


def generate_report(model_csv, summary_json, output, comparison_json=None, re24_validation_json=None,
                     steal_validation_csv=None, team_decisions_json=None,
                     runner_qualification_json=None) -> dict[str, Any]:
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

    payload = build_payload(rows, summary, comparison, re24_validation, steal_validation,
                             team_decisions, runner_qualification)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = template.replace("/*__STYLES__*/", STYLE_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("/*__SCRIPT__*/", SCRIPT_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("__REPORT_DATA__", payload_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--model-csv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--comparison-json", type=Path)
    parser.add_argument("--re24-validation-json", type=Path)
    parser.add_argument("--steal-validation-csv", type=Path)
    parser.add_argument("--team-decisions-json", type=Path)
    parser.add_argument("--runner-qualification-json", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.start_date}_{args.end_date}"
    model_csv = args.model_csv or ROOT / "outputs" / f"mlb_decision_model_{tag}.csv"
    summary_json = args.summary_json or ROOT / "outputs" / f"mlb_decision_model_{tag}_summary.json"
    comparison_json = args.comparison_json or ROOT / "outputs" / f"mlb_group_comparison_{tag}.json"
    re24_validation_json = args.re24_validation_json or ROOT / "outputs" / f"mlb_re24_validation_{tag}_summary.json"
    steal_validation_csv = args.steal_validation_csv or ROOT / "outputs" / f"mlb_steal_parsing_validation_{tag}.csv"
    team_decisions_json = args.team_decisions_json or ROOT / "outputs" / f"mlb_team_decisions_{tag}.json"
    runner_qualification_json = (
        args.runner_qualification_json or ROOT / "outputs" / f"mlb_runner_steal_rates_{tag}.json"
    )
    output = args.output or ROOT / "reports" / f"mlb-steal-decision-{tag}.html"
    payload = generate_report(
        model_csv, summary_json, output, comparison_json, re24_validation_json,
        steal_validation_csv, team_decisions_json, runner_qualification_json,
    )
    print(f"Wrote {output} with {payload['meta']['samples']} 決策樣本；"
          f"median threshold={payload['aggregate']['medianThreshold']:.3%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
