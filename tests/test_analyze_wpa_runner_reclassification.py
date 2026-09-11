import unittest

from analyze_wpa_runner_reclassification import build_rows


class BuildRowsTests(unittest.TestCase):
    def test_classifies_qualifying_and_non_qualifying_innings(self):
        never_go_runners = [
            {"HitterAcnt": "1", "HitterName": "A", "Team": "隊A", "Attempts": "10", "SuccessRate": "0.30"},
            {"HitterAcnt": "2", "HitterName": "B", "Team": "隊B", "Attempts": "8", "SuccessRate": "0.05"},
        ]
        wpa_thresholds = {4: 0.40, 5: 0.35, 6: 0.30, 7: 0.20, 8: 0.28}

        rows = build_rows(never_go_runners, wpa_thresholds)

        row_a = next(r for r in rows if r["HitterName"] == "A")
        # 0.30 成功率：只贏過第 6、7、8 局的門檻（0.30/0.20/0.28）
        self.assertEqual(row_a["WPA_QualifyingInnings"], "6,7,8")
        self.assertEqual(row_a["WPA_NonQualifyingInnings"], "4,5")
        self.assertTrue(row_a["ReclassifiedByWPA"])

        row_b = next(r for r in rows if r["HitterName"] == "B")
        # 0.05 成功率：贏不過任何一局的門檻
        self.assertEqual(row_b["WPA_QualifyingInnings"], "")
        self.assertFalse(row_b["ReclassifiedByWPA"])

    def test_sorted_by_success_rate_descending(self):
        never_go_runners = [
            {"HitterAcnt": "1", "HitterName": "Low", "Team": "隊A", "Attempts": "5", "SuccessRate": "0.10"},
            {"HitterAcnt": "2", "HitterName": "High", "Team": "隊B", "Attempts": "5", "SuccessRate": "0.40"},
        ]
        rows = build_rows(never_go_runners, {7: 0.20})
        self.assertEqual([r["HitterName"] for r in rows], ["High", "Low"])


if __name__ == "__main__":
    unittest.main()
