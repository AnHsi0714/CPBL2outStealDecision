import unittest

from compare_wpa_groups import (
    build_group_comparisons,
    direction_label,
    lineup_slot_medians,
    valid_threshold,
)


class ValidThresholdTests(unittest.TestCase):
    def test_accepts_values_in_0_1(self):
        self.assertAlmostEqual(valid_threshold("0.5"), 0.5)

    def test_rejects_none_empty_and_out_of_range(self):
        self.assertIsNone(valid_threshold(None))
        self.assertIsNone(valid_threshold(""))
        self.assertIsNone(valid_threshold("0"))
        self.assertIsNone(valid_threshold("1.5"))
        self.assertIsNone(valid_threshold("-0.2"))


class LineupSlotMediansTests(unittest.TestCase):
    def test_groups_by_hitter_lineup(self):
        rows = [
            {"HitterLineup": "1", "_t": 0.3},
            {"HitterLineup": "1", "_t": 0.5},
            {"HitterLineup": "2", "_t": 0.9},
            {"HitterLineup": "3", "_t": None},
        ]
        result = lineup_slot_medians(rows, "_t")
        self.assertEqual(result[1]["n"], 2)
        self.assertAlmostEqual(result[1]["median"], 0.4)
        self.assertEqual(result[2]["n"], 1)
        self.assertEqual(result[3]["n"], 0)
        self.assertIsNone(result[3]["median"])


class DirectionLabelTests(unittest.TestCase):
    def test_higher_group_wins(self):
        comparison = {
            "comparison": "x",
            "high_ISO": {"n": 5, "median": 0.6, "mean": 0.6},
            "low_ISO": {"n": 5, "median": 0.4, "mean": 0.4},
            "mann_whitney_u": 1.0,
            "p_value": 0.01,
        }
        self.assertEqual(direction_label(comparison), "high_ISO>low_ISO")

    def test_reports_na_when_group_empty(self):
        comparison = {
            "comparison": "x",
            "high_ISO": {"n": 0, "median": None, "mean": None},
            "low_ISO": {"n": 5, "median": 0.4, "mean": 0.4},
            "mann_whitney_u": None,
            "p_value": None,
        }
        self.assertEqual(direction_label(comparison), "NA")


class BuildGroupComparisonsTests(unittest.TestCase):
    def test_filters_to_qualified_rows_with_a_valid_threshold(self):
        rows = [
            {"BatterTypeQualified": "True", "PowerGroup": "high_ISO", "PatienceGroup": "low_BB",
             "OBPGroup": "low_OBP", "ContactGroup": "low_1B", "TTOGroup": "low_TTO", "_t": 0.6},
            {"BatterTypeQualified": "True", "PowerGroup": "low_ISO", "PatienceGroup": "low_BB",
             "OBPGroup": "low_OBP", "ContactGroup": "low_1B", "TTOGroup": "low_TTO", "_t": 0.3},
            {"BatterTypeQualified": "False", "PowerGroup": "high_ISO", "PatienceGroup": "low_BB",
             "OBPGroup": "low_OBP", "ContactGroup": "low_1B", "TTOGroup": "low_TTO", "_t": 0.9},
            {"BatterTypeQualified": "True", "PowerGroup": "high_ISO", "PatienceGroup": "low_BB",
             "OBPGroup": "low_OBP", "ContactGroup": "low_1B", "TTOGroup": "low_TTO", "_t": None},
        ]
        comparisons = build_group_comparisons(rows, "_t")
        power = next(c for c in comparisons if c["comparison"] == "power_high_vs_low_ISO")
        # 未達 PA 門檻(False)跟門檻無效(None)的列都要被排除
        self.assertEqual(power["high_ISO"]["n"], 1)
        self.assertEqual(power["low_ISO"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
