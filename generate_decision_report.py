"""Generate a standalone HTML report for the CPBL steal-decision model."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "decision_report.html"
STYLE_PATH = ROOT / "templates" / "decision_report.css"
SCRIPT_PATH = ROOT / "templates" / "decision_report.js"


def as_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def average(rows: list[dict[str, str]], key: str) -> float:
    values = [value for row in rows if (value := as_float(row, key)) is not None]
    return mean(values)


def compact_case(row: dict[str, str], index: int) -> dict[str, Any]:
    numeric_keys = (
        "ProfilePA",
        "ModelP_1B",
        "ModelP_2B",
        "ModelP_3B",
        "ModelP_HR",
        "ModelP_BB_HBP",
        "ModelP_REACH",
        "ModelP_OUT",
        "ModelVSuccess",
        "ModelVFailure",
        "ModelVNoSteal",
        "ModelVIfBatterOut",
        "RetentionValue",
        "ConditionalOutCostNoSteal",
        "ExpectedOutPenaltyNoSteal",
        "BreakEvenSuccessRate",
    )
    data: dict[str, Any] = {
        "id": index,
        "game": int(row["GameSno"]),
        "date": row["GameDate"],
        "inning": int(row["InningSeq"]),
        "team": row["BattingTeam"],
        "away": row["VisitingTeam"],
        "home": row["HomeTeam"],
        "hitter": row["HitterName"],
        "lineup": int(row["HitterLineup"]),
        "runner": row["RunnerOnFirst"],
        "pitcher": row["PitcherName"],
        "actual": row["Outcome"],
        "simulations": int(row["Simulations"]),
        "thresholdStatus": row["ThresholdStatus"],
    }
    for key in numeric_keys:
        value = as_float(row, key)
        data[key] = None if value is None else round(value, 6)
    return data


def load_re24_validation(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return {
        "correlation": data.get("correlation"),
        "weightedMae": data.get("weighted_mean_absolute_error"),
        "maxAbsoluteError": data.get("max_absolute_error"),
        "gamesWithRawData": data.get("games_with_raw_data"),
        "simulationsPerState": data.get("simulations_per_state"),
    }


def load_steal_validation(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    mismatches = sum(
        1 for row in rows if int(row["successDiff"]) != 0 or int(row["caughtDiff"]) != 0
    )
    return {
        "parsedSuccess": sum(int(row["parsedSuccess"]) for row in rows),
        "officialSuccess": sum(int(row["officialSuccess"]) for row in rows),
        "parsedCaught": sum(int(row["parsedCaught"]) for row in rows),
        "officialCaught": sum(int(row["officialCaught"]) for row in rows),
        "combos": len(rows),
        "mismatches": mismatches,
    }


def load_team_decisions(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def build_segments(comparison: dict[str, Any] | None) -> dict[str, Any] | None:
    if comparison is None:
        return None
    def round_or_none(value: Any) -> float | None:
        return round(value, 6) if value is not None else None

    return {
        "lineupSlots": [
            {
                "slot": item["slot"],
                "n": item["n"],
                "median": round_or_none(item["median"]),
                "meanVNoSteal": round_or_none(item["meanVNoSteal"]),
                "meanVFailure": round_or_none(item["meanVFailure"]),
                "meanVSuccess": round_or_none(item["meanVSuccess"]),
                "numerator": round_or_none(item["numerator"]),
                "denominator": round_or_none(item["denominator"]),
            }
            for item in comparison["lineup_slot_breakdown"]
        ],
        "comparisons": comparison["comparisons"],
        "qualifiedRows": comparison["batter_type_qualified_rows"],
        "substitution": comparison.get("lineup_substitution"),
        "correlations": comparison.get("batter_type_correlations"),
        "crossTables": {
            "lineupXPower": comparison.get("cross_table_lineup_x_power"),
            "lineupXPatience": comparison.get("cross_table_lineup_x_patience"),
            "lineupXObp": comparison.get("cross_table_lineup_x_obp"),
            "lineupXContact": comparison.get("cross_table_lineup_x_contact"),
            "lineupXTto": comparison.get("cross_table_lineup_x_tto"),
        },
    }


def build_payload(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    comparison: dict[str, Any] | None = None,
    re24_validation: dict[str, Any] | None = None,
    steal_validation: dict[str, Any] | None = None,
    team_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome_counts = {"steal_success": 0, "steal_failure": 0, "no_steal": 0}
    for row in rows:
        outcome = row.get("Outcome", "")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    valid_thresholds = [
        value
        for row in rows
        if (value := as_float(row, "BreakEvenSuccessRate")) is not None
        and 0 <= value <= 1
    ]
    cases = [compact_case(row, index) for index, row in enumerate(rows)]
    threshold_median = median(valid_thresholds)
    default_case = min(
        range(len(cases)),
        key=lambda index: abs(
            (cases[index]["BreakEvenSuccessRate"] or threshold_median) - threshold_median
        ),
    )

    v_success = average(rows, "ModelVSuccess")
    v_failure = average(rows, "ModelVFailure")
    v_no_steal = average(rows, "ModelVNoSteal")
    aggregate_threshold = (v_no_steal - v_failure) / (v_success - v_failure)

    return {
        "meta": {
            "year": int(summary["year"]),
            "games": int(summary["games_with_raw_data"]),
            "samples": len(rows),
            "completedPA": int(summary["completed_pa_for_profiles"]),
            "batters": int(summary["batter_profiles"]),
            "simulations": int(summary["simulations_per_context"]),
            "priorPA": float(summary["prior_pa"]),
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "aggregate": {
            "vSuccess": round(v_success, 6),
            "vFailure": round(v_failure, 6),
            "vNoSteal": round(v_no_steal, 6),
            "successGain": round(v_success - v_no_steal, 6),
            "failureCost": round(v_no_steal - v_failure, 6),
            "aggregateThreshold": round(aggregate_threshold, 6),
            "medianThreshold": round(threshold_median, 6),
            "retentionValue": round(average(rows, "RetentionValue"), 6),
            "conditionalOutCost": round(average(rows, "ConditionalOutCostNoSteal"), 6),
            "expectedOutPenalty": round(average(rows, "ExpectedOutPenaltyNoSteal"), 6),
            "outcomes": outcome_counts,
        },
        "defaultCase": default_case,
        "cases": cases,
        "segments": build_segments(comparison),
        "validation": {
            "re24": re24_validation,
            "steal": steal_validation,
        },
        "teamDecisions": team_decisions,
    }


def generate_report(
    model_csv: Path,
    summary_json: Path,
    output: Path,
    comparison_json: Path | None = None,
    re24_validation_json: Path | None = None,
    steal_validation_csv: Path | None = None,
    team_decisions_json: Path | None = None,
) -> dict[str, Any]:
    with model_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Model CSV has no rows: {model_csv}")

    with summary_json.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)

    comparison = None
    if comparison_json is not None and comparison_json.exists():
        with comparison_json.open("r", encoding="utf-8-sig") as handle:
            comparison = json.load(handle)
    elif comparison_json is not None:
        print(f"提醒：找不到 {comparison_json}，報告將略過棒次/打者類型分析區塊"
              f"（可先執行 analyze_batter_types.py / join_decision_batter_types.py / compare_groups.py）")

    re24_validation = load_re24_validation(re24_validation_json) if re24_validation_json else None
    if re24_validation_json is not None and re24_validation is None:
        print(f"提醒：找不到 {re24_validation_json}，報告將略過RE24引擎驗證區塊"
              f"（可先執行 build_re24_matrix.py / validate_re24_simulation.py）")

    steal_validation = load_steal_validation(steal_validation_csv) if steal_validation_csv else None
    if steal_validation_csv is not None and steal_validation is None:
        print(f"提醒：找不到 {steal_validation_csv}，報告將略過盜壘判讀對帳區塊"
              f"（可先執行 validate_steal_parsing.py）")

    team_decisions = load_team_decisions(team_decisions_json) if team_decisions_json else None
    if team_decisions_json is not None and team_decisions is None:
        print(f"提醒：找不到 {team_decisions_json}，報告將略過六隊決策品質評估區塊"
              f"（可先執行 analyze_team_decisions.py）")

    payload = build_payload(rows, summary, comparison, re24_validation, steal_validation, team_decisions)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_json = payload_json.replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = template.replace("/*__STYLES__*/", STYLE_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("/*__SCRIPT__*/", SCRIPT_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("__REPORT_DATA__", payload_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--model-csv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--comparison-json", type=Path)
    parser.add_argument("--re24-validation-json", type=Path)
    parser.add_argument("--steal-validation-csv", type=Path)
    parser.add_argument("--team-decisions-json", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stem = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    model_csv = args.model_csv or ROOT / "outputs" / f"cpbl_decision_model_{stem}.csv"
    summary_json = args.summary_json or ROOT / "outputs" / f"cpbl_decision_model_{stem}_summary.json"
    comparison_json = args.comparison_json or ROOT / "outputs" / f"cpbl_group_comparison_{stem}.json"
    re24_validation_json = (
        args.re24_validation_json or ROOT / "outputs" / f"cpbl_re24_validation_{stem}_summary.json"
    )
    steal_validation_csv = (
        args.steal_validation_csv or ROOT / "outputs" / f"cpbl_steal_parsing_validation_{stem}.csv"
    )
    team_decisions_json = (
        args.team_decisions_json or ROOT / "outputs" / f"cpbl_team_decisions_{stem}.json"
    )
    output = args.output or ROOT / "reports" / f"cpbl-steal-decision-{args.year}.html"
    payload = generate_report(
        model_csv,
        summary_json,
        output,
        comparison_json,
        re24_validation_json,
        steal_validation_csv,
        team_decisions_json,
    )
    print(
        f"Wrote {output} with {payload['meta']['samples']} cases; "
        f"median threshold={payload['aggregate']['medianThreshold']:.3%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
