import unittest

from build_re24_matrix import base_state_code, build_matrix, collect_state_segments


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


class BaseStateCodeTests(unittest.TestCase):
    def test_encodes_each_base_independently(self):
        self.assertEqual(base_state_code(row(1, "1", 0)), 0)
        self.assertEqual(base_state_code(row(1, "1", 0, first="1")), 1)
        self.assertEqual(base_state_code(row(1, "1", 0, second="1")), 2)
        self.assertEqual(base_state_code(row(1, "1", 0, first="1", second="1")), 3)
        self.assertEqual(base_state_code(row(1, "1", 0, third="1")), 4)
        self.assertEqual(
            base_state_code(row(1, "1", 0, first="1", second="1", third="1")), 7
        )


class CollectStateSegmentsTests(unittest.TestCase):
    def test_splits_on_state_change_and_uses_pre_event_baseline(self):
        # 沿用 test_find_2out_first_base.py 已驗證過的情境：兩出局、一壘有人時
        # 盜壘成功上二壘，接著安打把跑者送回本壘，最後打者出局、3人出局。
        # 壘包欄位在事件發生的那一列尚未更新（下一列才反映新狀態），
        # 比分則在事件發生的那一列就即時更新——與計畫書 3.0 節的說明一致。
        rows = [
            row(1, "1", 2, first="2"),
            row(1, "1", 2, first="2", content="壞球。一壘跑者甲 盜壘上二壘。"),
            row(1, "1", 2, second="2"),
            row(1, "1", 2, second="2", visiting_score=1, content="安打，二壘跑者得分。"),
            row(1, "1", 2, visiting_score=1, content="打者出局。3人出局。"),
            row(1, "2", 0),
            row(1, "2", 2, content="3人出局。"),
        ]
        segments = collect_state_segments(rows)
        # (outs, base_code, remaining_runs)：
        # - 一壘有人(code=1) 起算到半局結束共得 1 分（那顆盜壘成功後的安打分）。
        # - 盜壘成功後二壘有人(code=2) 起算，同一分仍算在這個區段裡，因為得分
        #   是在盜壘之後才發生。
        # - 安打把人送回本壘後，狀態變成空壘(code=0)，此後半局結束前沒有再得分。
        self.assertEqual(
            segments,
            [
                (2, 1, 1),
                (2, 2, 1),
                (2, 0, 0),
                # 下半局（主隊進攻）本身也是兩個 state 區段：0 出局空壘、
                # 2 出局空壘，兩者都沒有再得分。
                (0, 0, 0),
                (2, 0, 0),
            ],
        )

    def test_excludes_incomplete_half_inning(self):
        rows = [
            row(1, "1", 0),
            row(1, "1", 1, first="1"),
            # 半局未打完就中止（無下一半局、無 3人出局標記）
        ]
        self.assertEqual(collect_state_segments(rows), [])

    def test_first_segment_of_next_half_inning_uses_prior_half_final_score(self):
        rows = [
            row(1, "1", 0, visiting_score=2),
            row(1, "1", 2, visiting_score=2, content="3人出局。"),
            row(2, "1", 0, visiting_score=2),
            row(2, "1", 2, visiting_score=5, content="3人出局。"),
        ]
        segments = collect_state_segments(rows)
        # 第二局（同隊）起始狀態的起算分應是第一局結束時的比分（2），
        # 剩餘得分 = 5 - 2 = 3，而不是誤用 0 當起點。
        self.assertIn((0, 0, 3), segments)


class BuildMatrixTests(unittest.TestCase):
    def test_aggregates_mean_and_basic_threshold(self):
        segments = [
            (2, 1, 0),  # 一壘有人，2 出局
            (2, 1, 1),
            (2, 2, 1),  # 二壘有人，2 出局
            (2, 2, 2),
            (2, 2, 3),
        ]
        matrix = build_matrix(segments)
        cell_map = {(c["outs"], c["baseCode"]): c for c in matrix["cells"]}
        self.assertEqual(cell_map[(2, 1)]["n"], 2)
        self.assertAlmostEqual(cell_map[(2, 1)]["meanRE"], 0.5)
        self.assertEqual(cell_map[(2, 2)]["n"], 3)
        self.assertAlmostEqual(cell_map[(2, 2)]["meanRE"], 2.0)
        self.assertEqual(cell_map[(2, 0)]["n"], 0)
        self.assertIsNone(cell_map[(2, 0)]["meanRE"])
        self.assertAlmostEqual(
            matrix["basicBreakEvenThresholdByOuts"]["2"], 0.5 / 2.0
        )


if __name__ == "__main__":
    unittest.main()
