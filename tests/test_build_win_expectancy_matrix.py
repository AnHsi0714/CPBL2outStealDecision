import unittest

from build_win_expectancy_matrix import (
    build_matrix,
    collect_state_segments,
    inning_bucket,
    score_diff_bucket,
    score_diff_label,
)


def row(
    inning,
    batting_side,
    out_count,
    first="",
    second="",
    third="",
    visiting_score=0,
    home_score=0,
    content="",
):
    return {
        "InningSeq": inning,
        "VisitingHomeType": batting_side,
        "OutCnt": out_count,
        "FirstBase": first,
        "SecondBase": second,
        "ThirdBase": third,
        "VisitingScore": visiting_score,
        "HomeScore": home_score,
        "Content": content,
    }


class InningBucketTests(unittest.TestCase):
    def test_buckets_early_innings_together_and_keeps_7_8_separate(self):
        self.assertEqual(inning_bucket(1), "1-6")
        self.assertEqual(inning_bucket(6), "1-6")
        self.assertEqual(inning_bucket(7), "7")
        self.assertEqual(inning_bucket(8), "8")
        self.assertEqual(inning_bucket(9), "9+")
        self.assertEqual(inning_bucket(12), "9+")


class ScoreDiffBucketTests(unittest.TestCase):
    def test_caps_at_plus_minus_five(self):
        self.assertEqual(score_diff_bucket(-9), -5)
        self.assertEqual(score_diff_bucket(-2), -2)
        self.assertEqual(score_diff_bucket(0), 0)
        self.assertEqual(score_diff_bucket(3), 3)
        self.assertEqual(score_diff_bucket(9), 5)

    def test_labels(self):
        self.assertEqual(score_diff_label(-5), "落後5+")
        self.assertEqual(score_diff_label(-1), "落後1")
        self.assertEqual(score_diff_label(0), "平手")
        self.assertEqual(score_diff_label(1), "領先1")
        self.assertEqual(score_diff_label(5), "領先5+")


class CollectStateSegmentsTests(unittest.TestCase):
    def test_visiting_team_win_marks_own_half_segments_as_win(self):
        # 客隊(1) 4 分贏主隊(2) 1 分；兩隊各一個半局，都算已打完。
        rows = [
            row(1, "1", 0, visiting_score=4),
            row(1, "1", 2, visiting_score=4, content="3人出局。"),
            row(1, "2", 0, visiting_score=4, home_score=1),
            row(1, "2", 2, visiting_score=4, home_score=1, content="3人出局。"),
        ]
        segments = collect_state_segments(rows)
        outcomes_by_side = {(s[1]): s[5] for s in segments}
        self.assertEqual(outcomes_by_side["1"], 1.0)
        self.assertEqual(outcomes_by_side["2"], 0.0)

    def test_tie_game_records_half_win_value(self):
        rows = [
            row(1, "1", 0, visiting_score=2),
            row(1, "1", 2, visiting_score=2, content="3人出局。"),
            row(1, "2", 0, visiting_score=2, home_score=2),
            row(1, "2", 2, visiting_score=2, home_score=2, content="3人出局。"),
        ]
        segments = collect_state_segments(rows)
        self.assertTrue(all(s[5] == 0.5 for s in segments))

    def test_incomplete_final_half_excludes_whole_game(self):
        rows = [
            row(1, "1", 0, visiting_score=2),
            row(1, "1", 2, visiting_score=2, content="3人出局。"),
            row(1, "2", 0, visiting_score=2, home_score=0),
            row(1, "2", 1, visiting_score=2, home_score=0, first="1"),
            # 下半局沒打完就中止（無下一半局、無 3人出局標記）
        ]
        self.assertEqual(collect_state_segments(rows), [])

    def test_score_diff_uses_pre_event_baseline_for_both_sides(self):
        # 客隊進攻：0 出局空壘時全壘打得 1 分（比分即時更新，壘包狀態不變，
        # 不會另起新區段），下一個新區段（1 出局、一壘有人）起算分應該是
        # 全壘打之後的 1 分，對手（主隊）全程 0 分。
        rows = [
            row(1, "1", 0, visiting_score=0),
            row(1, "1", 0, visiting_score=1, content="全壘打。"),
            row(1, "1", 1, visiting_score=1, first="1"),
            row(1, "1", 2, visiting_score=3, content="3人出局。"),
            row(1, "2", 0, visiting_score=3, home_score=0),
            row(1, "2", 2, visiting_score=3, home_score=0, content="3人出局。"),
        ]
        segments = collect_state_segments(rows)
        # (局數bucket, 攻守方, 分差bucket, 出局, 壘包, 結果)
        diff_by_state = {(s[1], s[3], s[4]): s[2] for s in segments}
        self.assertEqual(diff_by_state[("1", 0, 0)], 0)  # 半局第一個區段：0(起算)-0
        self.assertEqual(diff_by_state[("1", 1, 1)], 1)  # 全壘打後起算分 1，對手仍 0


class BuildMatrixTests(unittest.TestCase):
    def test_aggregates_win_rate(self):
        segments = [
            ("7", "1", 0, 2, 1, 1.0),
            ("7", "1", 0, 2, 1, 0.0),
            ("7", "1", 0, 2, 1, 1.0),
        ]
        matrix = build_matrix(segments)
        cell_map = {
            (c["inningBucket"], c["battingSide"], c["scoreDiffBucket"], c["outs"], c["baseCode"]): c
            for c in matrix["cells"]
        }
        cell = cell_map[("7", "1", 0, 2, 1)]
        self.assertEqual(cell["n"], 3)
        self.assertAlmostEqual(cell["winRate"], round(2 / 3, 4))

        empty_cell = cell_map[("7", "1", 0, 2, 2)]
        self.assertEqual(empty_cell["n"], 0)
        self.assertIsNone(empty_cell["winRate"])


if __name__ == "__main__":
    unittest.main()
