import unittest

from analyze_team_decisions import build_summary


def make_row(team, lineup, outcome, threshold):
    return {
        "BattingTeam": team,
        "HitterLineup": lineup,
        "Outcome": outcome,
        "BreakEvenSuccessRate": threshold,
    }


def make_rows(team, lineup, threshold, successes, failures, no_steals=0):
    rows = [make_row(team, lineup, "steal_success", threshold) for _ in range(successes)]
    rows += [make_row(team, lineup, "steal_failure", threshold) for _ in range(failures)]
    rows += [make_row(team, lineup, "no_steal", threshold) for _ in range(no_steals)]
    return rows


class BuildSummaryTests(unittest.TestCase):
    def test_team_with_significantly_higher_success_rate_is_marked_correct(self):
        rows = make_rows("A", "3", "0.5", successes=25, failures=5)
        summary = build_summary(rows)
        team_a = summary["teams"][0]
        self.assertEqual(team_a["team"], "A")
        self.assertEqual(team_a["attempts"], 30)
        self.assertAlmostEqual(team_a["actualSuccessRate"], 25 / 30)
        self.assertAlmostEqual(team_a["thresholdMedian"], 0.5)
        self.assertLess(team_a["pValue"], 0.05)
        self.assertEqual(team_a["verdict"], "跑對")

    def test_team_with_significantly_lower_success_rate_is_marked_wrong(self):
        rows = make_rows("B", "6", "0.5", successes=5, failures=25)
        summary = build_summary(rows)
        team_b = summary["teams"][0]
        self.assertAlmostEqual(team_b["actualSuccessRate"], 5 / 30)
        self.assertLess(team_b["pValue"], 0.05)
        self.assertEqual(team_b["verdict"], "跑錯")

    def test_small_sample_deviation_is_marked_inconclusive_not_wrong(self):
        # 3 成功 / 2 失敗 vs 門檻 0.5：點估計（60%）高於門檻，但 n=5 遠不足以顯著區分，
        # 不該被直接判「跑對」——這正是計畫書 3.3 節「切層後樣本不足」要提防的誤判。
        rows = make_rows("F", "4", "0.5", successes=3, failures=2)
        summary = build_summary(rows)
        team_f = summary["teams"][0]
        self.assertGreaterEqual(team_f["pValue"], 0.05)
        self.assertEqual(team_f["verdict"], "無法判定（不顯著）")
        self.assertIsNotNone(team_f["ci95Low"])
        self.assertIsNotNone(team_f["ci95High"])

    def test_team_with_no_attempts_is_marked_insufficient_sample(self):
        rows = [make_row("C", "2", "no_steal", "0.6")]
        summary = build_summary(rows)
        team_c = summary["teams"][0]
        self.assertEqual(team_c["attempts"], 0)
        self.assertIsNone(team_c["actualSuccessRate"])
        self.assertEqual(team_c["verdict"], "樣本不足（無嘗試）")

    def test_thresholds_outside_zero_one_range_are_excluded_from_median(self):
        rows = [
            make_row("D", "1", "steal_success", "0"),
            make_row("D", "1", "steal_failure", "1.5"),
            make_row("D", "1", "no_steal", "0.4"),
        ]
        summary = build_summary(rows)
        team_d = summary["teams"][0]
        self.assertEqual(team_d["thresholdSamples"], 1)
        self.assertAlmostEqual(team_d["thresholdMedian"], 0.4)

    def test_lineup_half_split_separates_front_and_back(self):
        rows = [
            make_row("E", "2", "steal_success", "0.5"),
            make_row("E", "7", "steal_failure", "0.5"),
        ]
        summary = build_summary(rows)
        halves = summary["teamsByLineupHalf"]["E"]
        self.assertEqual(halves["front_1_5"]["attempts"], 1)
        self.assertEqual(halves["front_1_5"]["successes"], 1)
        self.assertEqual(halves["back_6_9"]["attempts"], 1)
        self.assertEqual(halves["back_6_9"]["failures"], 1)

    def test_multiple_teams_are_sorted_and_independent(self):
        rows = [
            make_row("Z", "1", "steal_success", "0.4"),
            make_row("A", "1", "steal_failure", "0.9"),
        ]
        summary = build_summary(rows)
        self.assertEqual([t["team"] for t in summary["teams"]], ["A", "Z"])

    def test_league_aggregates_all_rows(self):
        rows = [
            make_row("A", "1", "steal_success", "0.5"),
            make_row("B", "1", "steal_failure", "0.5"),
        ]
        summary = build_summary(rows)
        self.assertEqual(summary["league"]["attempts"], 2)
        self.assertEqual(summary["opportunities"], 2)


if __name__ == "__main__":
    unittest.main()
