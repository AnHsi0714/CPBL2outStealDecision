import unittest

from validate_re24_simulation import compare_matrices


class CompareMatricesTests(unittest.TestCase):
    def test_computes_per_cell_diff_and_aggregate_errors(self):
        sim_means = {
            (2, 0): 0.20,
            (2, 1): 0.25,
        }
        real_cells = {
            (2, 0): {"meanRE": 0.22, "n": 100},
            (2, 1): {"meanRE": 0.20, "n": 50},
        }
        result = compare_matrices(sim_means, real_cells)
        by_key = {(row["outs"], row["baseCode"]): row for row in result["cells"]}

        self.assertAlmostEqual(by_key[(2, 0)]["diff"], -0.02, places=4)
        self.assertAlmostEqual(by_key[(2, 1)]["diff"], 0.05, places=4)
        # 加權 MAE 用真實樣本數加權：(0.02*100 + 0.05*50) / 150
        self.assertAlmostEqual(result["weightedMeanAbsoluteError"], (0.02 * 100 + 0.05 * 50) / 150, places=4)
        self.assertAlmostEqual(result["meanAbsoluteError"], (0.02 + 0.05) / 2, places=4)
        self.assertIsNotNone(result["correlation"])

    def test_missing_real_cell_is_skipped_from_error_stats(self):
        sim_means = {(0, 0): 0.45, (0, 1): 0.80}
        real_cells = {(0, 0): {"meanRE": 0.45, "n": 6000}}
        result = compare_matrices(sim_means, real_cells)
        by_key = {(row["outs"], row["baseCode"]): row for row in result["cells"]}
        self.assertIsNone(by_key[(0, 1)]["diff"])
        self.assertAlmostEqual(result["meanAbsoluteError"], 0.0, places=6)

    def test_all_24_cells_present_even_when_sim_or_real_missing(self):
        result = compare_matrices({}, {})
        self.assertEqual(len(result["cells"]), 24)
        self.assertIsNone(result["meanAbsoluteError"])
        self.assertIsNone(result["correlation"])


if __name__ == "__main__":
    unittest.main()
