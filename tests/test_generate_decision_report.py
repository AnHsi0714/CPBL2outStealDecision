import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import csv
import json
import tempfile
import unittest
from pathlib import Path

from generate_decision_report import (
    build_payload,
    build_segments,
    fisher_exact_two_sided,
    load_handedness,
    load_re24_validation,
    load_steal_validation,
    retention_by_slot,
)

SUMMARY = {
    "year": 2025,
    "games_with_raw_data": 360,
    "completed_pa_for_profiles": 27161,
    "batter_profiles": 174,
    "simulations_per_context": 2000,
    "prior_pa": 50,
}


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
    def test_payload_keeps_representative_case_and_recomputes_break_even(self):
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
        self.assertEqual(payload["cases"]["strings"][payload["cases"]["rows"][0][payload["cases"]["fields"].index("hitter")]], "測試打者")

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


class RetentionBySlotTests(unittest.TestCase):
    @staticmethod
    def row(slot, v_failure, v_if_out):
        row = sample_row()
        row.update(
            {
                "HitterLineup": str(slot),
                "ModelVFailure": str(v_failure),
                "ModelVIfBatterOut": str(v_if_out),
                "RetentionValue": str(round(v_failure - v_if_out, 6)),
            }
        )
        return row

    def test_opposite_signs_cancel_in_the_overall_mean_but_not_per_slot(self):
        rows = [self.row(3, 0.4, 0.3), self.row(8, 0.3, 0.4)]

        slots = retention_by_slot(rows)

        self.assertEqual([item["slot"] for item in slots], list(range(1, 10)))
        self.assertAlmostEqual(slots[2]["meanValue"], 0.1)
        self.assertAlmostEqual(slots[7]["meanValue"], -0.1)
        # 保留有利（正值）會把損益兩平門檻壓低：(0.6-0.4)/(0.8-0.4) - (0.6-0.3)/(0.8-0.3) = -10pp
        self.assertAlmostEqual(slots[2]["thresholdShiftPP"], -10.0)
        self.assertAlmostEqual(slots[7]["thresholdShiftPP"], 10.0)
        self.assertEqual(slots[0]["n"], 0)
        self.assertIsNone(slots[0]["meanValue"])
        self.assertIsNone(slots[0]["thresholdShiftPP"])

        aggregate = build_payload(rows, SUMMARY)["aggregate"]
        self.assertAlmostEqual(aggregate["retentionValue"], 0.0)
        self.assertEqual(aggregate["retentionBySlot"], slots)


class FisherExactTests(unittest.TestCase):
    def test_matches_single_season_values_in_the_findings_doc(self):
        # (左投成功, 左投刺殺, 右投成功, 右投刺殺) 對應 2023–2026 的單季 p 值
        cases = (
            ((62, 41, 308, 122), 0.032),
            ((109, 54, 295, 121), 0.366),
            ((130, 89, 321, 137), 0.007),
            ((89, 50, 359, 147), 0.120),
        )
        for counts, expected in cases:
            self.assertEqual(round(fisher_exact_two_sided(*counts), 3), expected)

    def test_identical_rows_give_p_of_one(self):
        self.assertAlmostEqual(fisher_exact_two_sided(10, 10, 10, 10), 1.0)


class HandednessAndSegmentsTests(unittest.TestCase):
    def test_load_handedness_attaches_fisher_p_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hand.json"
            path.write_text(
                json.dumps(
                    {
                        "league_by_pitcher_hand": {
                            "LHP": {"attempts": 219, "success": 130, "caught": 89, "successRate": 0.5936},
                            "RHP": {"attempts": 458, "success": 321, "caught": 137, "successRate": 0.7009},
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = load_handedness(path)
        self.assertEqual(result["LHP"]["success"], 130)
        self.assertEqual(round(result["pValue"], 3), 0.007)

    def test_load_handedness_returns_none_when_missing(self):
        self.assertIsNone(load_handedness(Path("does/not/exist.json")))

    def test_segments_keep_decision_rows_and_batter_count_apart(self):
        comparison = {
            "lineup_slot_breakdown": [],
            "comparisons": [],
            "batter_type_qualified_rows": 1714,
            "batter_type_correlations": {"batters": 86},
        }

        segments = build_segments(comparison)

        self.assertEqual(segments["qualifiedRows"], 1714)
        self.assertEqual(segments["qualifiedBatters"], 86)


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
