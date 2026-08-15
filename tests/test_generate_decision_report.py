import unittest

from generate_decision_report import build_payload


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


if __name__ == "__main__":
    unittest.main()
