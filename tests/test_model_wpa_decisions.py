import math
import unittest

from model_wpa_decisions import (
    WinExpectancyTable,
    advance_half,
    binomial_se,
    win_value_after_half_ends,
)


class BinomialSETests(unittest.TestCase):
    def test_matches_binomial_formula(self):
        self.assertAlmostEqual(binomial_se(0.5, 100), math.sqrt(0.25 / 100))

    def test_zero_n_is_zero(self):
        self.assertEqual(binomial_se(0.5, 0), 0.0)


def cell(inning_bucket, side, diff, outs, base, win_rate, n):
    return {
        "inningBucket": inning_bucket,
        "battingSide": side,
        "scoreDiffBucket": diff,
        "outs": outs,
        "baseCode": base,
        "winRate": win_rate,
        "n": n,
    }


class AdvanceHalfTests(unittest.TestCase):
    def test_visiting_half_moves_to_home_half_same_inning(self):
        self.assertEqual(advance_half(7, "1"), (7, "2"))

    def test_home_half_moves_to_visiting_half_next_inning(self):
        self.assertEqual(advance_half(7, "2"), (8, "1"))


class WinExpectancyTableTests(unittest.TestCase):
    def test_exact_cell_used_when_sample_size_sufficient(self):
        cells = [cell("7", "1", 0, 2, 1, 0.5, 50)]
        we = WinExpectancyTable(cells, min_n=20)
        rate, n, used_fallback = we.lookup(7, "1", 0, 2, 1)
        self.assertEqual(rate, 0.5)
        self.assertEqual(n, 50)
        self.assertFalse(used_fallback)

    def test_falls_back_to_inning_pooled_value_when_sparse(self):
        cells = [
            cell("7", "1", 0, 2, 1, 0.9, 5),  # too sparse, should be skipped
            cell("1-6", "1", 0, 2, 1, 0.4, 500),
            cell("8", "1", 0, 2, 1, 0.6, 500),
        ]
        we = WinExpectancyTable(cells, min_n=20)
        rate, n, used_fallback = we.lookup(7, "1", 0, 2, 1)
        self.assertTrue(used_fallback)
        # 合併值＝加權平均：(0.9*5 + 0.4*500 + 0.6*500) / (5+500+500)
        expected = (0.9 * 5 + 0.4 * 500 + 0.6 * 500) / (5 + 500 + 500)
        self.assertAlmostEqual(rate, expected)
        self.assertEqual(n, 5 + 500 + 500)

    def test_score_diff_and_inning_are_bucketed_before_lookup(self):
        # inning 12 應該落在 "9+" 桶；分差 9 應該壓到 +5 桶
        cells = [cell("9+", "2", 5, 0, 0, 0.7, 40)]
        we = WinExpectancyTable(cells, min_n=20)
        rate, n, used_fallback = we.lookup(12, "2", 9, 0, 0)
        self.assertEqual(rate, 0.7)
        self.assertEqual(n, 40)
        self.assertFalse(used_fallback)

    def test_missing_state_raises(self):
        we = WinExpectancyTable([], min_n=20)
        with self.assertRaises(KeyError):
            we.lookup(7, "1", 0, 2, 1)


class WinValueAfterHalfEndsTests(unittest.TestCase):
    def test_flips_opponent_perspective_and_sign_of_diff(self):
        # 客隊進攻(1)半局結束，換主隊進攻(2)在同一局、分差變號。
        cells = [cell("7", "2", -3, 0, 0, 0.3, 100)]
        we = WinExpectancyTable(cells, min_n=20)
        value, n, used_fallback = win_value_after_half_ends(we, 7, "1", 3)
        self.assertAlmostEqual(value, 1 - 0.3)
        self.assertEqual(n, 100)
        self.assertFalse(used_fallback)


if __name__ == "__main__":
    unittest.main()
