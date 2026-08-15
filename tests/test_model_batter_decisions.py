import random
import unittest
from unittest.mock import patch

from model_batter_decisions import (
    LEAGUE_PROFILE_ID,
    OUTCOMES,
    classify_outcome,
    fallback_transition,
    out_cost_metrics,
    simulate_half,
    threshold_result,
    parse_args,
)


class ModelTests(unittest.TestCase):
    def test_classifies_power_and_outcomes(self):
        self.assertEqual(classify_outcome("一壘安打 內野安打"), "1B")
        self.assertEqual(classify_outcome("二壘安打 "), "2B")
        self.assertEqual(classify_outcome("全壘打"), "HR")
        self.assertEqual(classify_outcome("觸身死球"), "BB_HBP")
        self.assertEqual(classify_outcome("接球失誤"), "REACH")
        self.assertEqual(classify_outcome("飛球接殺"), "OUT")
        self.assertIsNone(classify_outcome(""))

    def test_single_scores_runner_from_third_not_first(self):
        from_first = fallback_transition(2, 1, "1B")
        from_third = fallback_transition(2, 4, "1B")
        self.assertEqual(from_first.runs, 0)
        self.assertEqual(from_third.runs, 1)

    def test_all_out_lineup_ends_half_and_consumes_batter(self):
        cumulative = [0.0] * (len(OUTCOMES) - 1) + [1.0]
        probabilities = {outcome: (1.0 if outcome == "OUT" else 0.0) for outcome in OUTCOMES}
        samplers = {LEAGUE_PROFILE_ID: (cumulative, probabilities)}
        lineup = (LEAGUE_PROFILE_ID,) * 9
        runs, next_slot = simulate_half(
            lineup,
            start_slot=3,
            start_outs=2,
            start_bases=1,
            samplers=samplers,
            pools={},
            rng=random.Random(1),
            minimum_cell=5,
        )
        self.assertEqual(runs, 0)
        self.assertEqual(next_slot, 4)

    def test_threshold_formula(self):
        threshold, status = threshold_result(1.0, 0.2, 0.6)
        self.assertAlmostEqual(threshold, 0.5)
        self.assertEqual(status, "break_even_in_0_1")

    def test_out_cost_separates_non_out_value_and_expected_penalty(self):
        # 25% 出局時價值 0.4、75% 非出局時價值 1.2，總 EV 應為 1.0。
        non_out, conditional_cost, expected_penalty = out_cost_metrics(1.0, 0.4, 0.25)
        self.assertAlmostEqual(non_out, 1.2)
        self.assertAlmostEqual(conditional_cost, 0.8)
        self.assertAlmostEqual(expected_penalty, 0.2)

    def test_model_cli_accepts_year_and_game_range(self):
        with patch(
            "sys.argv",
            [
                "model_batter_decisions.py",
                "--year",
                "2025",
                "--start",
                "1",
                "--end",
                "360",
            ],
        ):
            args = parse_args()
        self.assertEqual(args.year, 2025)
        self.assertEqual(args.start, 1)
        self.assertEqual(args.end, 360)


if __name__ == "__main__":
    unittest.main()
