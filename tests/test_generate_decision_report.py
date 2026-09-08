import csv
import json
import tempfile
import unittest
from pathlib import Path

from generate_decision_report import build_payload, load_re24_validation, load_steal_validation


def sample_row(outcome="no_steal"):
    return {
        "GameSno": "1",
        "GameDate": "2025-03-29",
        "InningSeq": "7",
        "BattingTeam": "測試隊",
        "VisitingTeam": "客隊",
        "HomeTeam": "主隊",
        "HitterName": "測試打者",
        "HitterLineup": "4",
        "RunnerOnFirst": "測試跑者",
        "PitcherName": "測試投手",
        "Outcome": outcome,
        "Simulations": "2000",
        "ThresholdStatus": "break_even_in_0_1",
        "ProfilePA": "300",
        "ModelP_1B": "0.15",
        "ModelP_2B": "0.05",
        "ModelP_3B": "0.01",
        "ModelP_HR": "0.04",
        "ModelP_BB_HBP": "0.10",
        "ModelP_REACH": "0.05",
        "ModelP_OUT": "0.60",
        "ModelVSuccess": "0.8",
        "ModelVFailure": "0.4",
        "ModelVNoSteal": "0.6",
        "ModelVIfBatterOut": "0.3",
        "RetentionValue": "0.02",
        "ConditionalOutCostNoSteal": "0.5",
        "ExpectedOutPenaltyNoSteal": "0.3",
        "BreakEvenSuccessRate": "0.5",
    }


class DecisionReportTests(unittest.TestCase):
    def test_payload_keeps_cases_and_recomputes_break_even(self):
        summary = {
            "year": 2025,
            "games_with_raw_data": 360,
            "completed_pa_for_profiles": 27161,
            "batter_profiles": 174,
            "simulations_per_context": 2000,
            "prior_pa": 50,
        }
        rows = [sample_row("steal_success"), sample_row("steal_failure")]

        payload = build_payload(rows, summary)

        self.assertEqual(payload["meta"]["samples"], 2)
        self.assertEqual(payload["aggregate"]["outcomes"]["steal_success"], 1)
        self.assertEqual(payload["aggregate"]["outcomes"]["steal_failure"], 1)
        self.assertAlmostEqual(payload["aggregate"]["aggregateThreshold"], 0.5)
        self.assertAlmostEqual(payload["aggregate"]["medianThreshold"], 0.5)
        self.assertEqual(payload["cases"][0]["hitter"], "測試打者")

    def test_payload_carries_validation_data_when_provided(self):
        summary = {
            "year": 2025,
            "games_with_raw_data": 360,
            "completed_pa_for_profiles": 27161,
            "batter_profiles": 174,
            "simulations_per_context": 2000,
            "prior_pa": 50,
        }
        rows = [sample_row("no_steal")]
        re24_validation = {"correlation": 0.992, "weightedMae": 0.033}
        steal_validation = {"parsedSuccess": 508, "officialSuccess": 508}

        payload = build_payload(rows, summary, None, re24_validation, steal_validation)

        self.assertEqual(payload["validation"]["re24"], re24_validation)
        self.assertEqual(payload["validation"]["steal"], steal_validation)

    def test_payload_validation_defaults_to_none(self):
        summary = {
            "year": 2025,
            "games_with_raw_data": 360,
            "completed_pa_for_profiles": 27161,
            "batter_profiles": 174,
            "simulations_per_context": 2000,
            "prior_pa": 50,
        }
        payload = build_payload([sample_row("no_steal")], summary)
        self.assertIsNone(payload["validation"]["re24"])
        self.assertIsNone(payload["validation"]["steal"])


class LoadValidationFilesTests(unittest.TestCase):
    def test_load_re24_validation_returns_none_when_missing(self):
        self.assertIsNone(load_re24_validation(Path("does/not/exist.json")))

    def test_load_re24_validation_reads_expected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "re24.json"
            path.write_text(
                json.dumps(
                    {
                        "correlation": 0.9919,
                        "weighted_mean_absolute_error": 0.0329,
                        "max_absolute_error": 0.1792,
                        "games_with_raw_data": 360,
                        "simulations_per_state": 3000,
                    }
                ),
                encoding="utf-8",
            )
            result = load_re24_validation(path)
            self.assertEqual(result["correlation"], 0.9919)
            self.assertEqual(result["weightedMae"], 0.0329)
            self.assertEqual(result["gamesWithRawData"], 360)

    def test_load_steal_validation_sums_rows_and_counts_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "steal.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "outs", "baseCode", "baseLabel", "parsedSuccess", "officialSuccess",
                        "successDiff", "parsedCaught", "officialCaught", "caughtDiff",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "outs": 0, "baseCode": 0, "baseLabel": "", "parsedSuccess": 300,
                    "officialSuccess": 300, "successDiff": 0, "parsedCaught": 150,
                    "officialCaught": 150, "caughtDiff": 0,
                })
                writer.writerow({
                    "outs": 0, "baseCode": 0, "baseLabel": "", "parsedSuccess": 208,
                    "officialSuccess": 208, "successDiff": 0, "parsedCaught": 91,
                    "officialCaught": 92, "caughtDiff": -1,
                })
            result = load_steal_validation(path)
            self.assertEqual(result["parsedSuccess"], 508)
            self.assertEqual(result["officialSuccess"], 508)
            self.assertEqual(result["parsedCaught"], 241)
            self.assertEqual(result["officialCaught"], 242)
            self.assertEqual(result["combos"], 2)
            self.assertEqual(result["mismatches"], 1)

    def test_load_steal_validation_returns_none_when_missing(self):
        self.assertIsNone(load_steal_validation(Path("does/not/exist.csv")))


if __name__ == "__main__":
    unittest.main()
