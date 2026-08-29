import json
import unittest

from find_2out_first_base import (
    analyze_game,
    deduplicate_schedule,
    is_administrative_only_row,
    remove_administrative_rows,
)


def row(
    inning,
    batting_side,
    batting_order,
    lineup,
    out_count,
    first="",
    second="",
    third="",
    visiting_score=0,
    home_score=0,
    content="",
    pitch=1,
    hitter="打者",
):
    return {
        "InningSeq": inning,
        "VisitingHomeType": batting_side,
        "BattingOrder": batting_order,
        "HitterLineup": lineup,
        "HitterName": hitter,
        "PitcherName": "投手",
        "PitchCnt": pitch,
        "OutCnt": out_count,
        "FirstBase": first,
        "SecondBase": second,
        "ThirdBase": third,
        "VisitingScore": visiting_score,
        "HomeScore": home_score,
        "ActionName": "",
        "Content": content,
    }


def game_data(rows):
    return {"LiveLogJson": json.dumps(rows, ensure_ascii=False)}


META = {
    "Year": 2026,
    "KindCode": "A",
    "GameSno": 1,
    "GameDate": "2026-04-01T00:00:00",
    "VisitingTeamName": "客隊",
    "HomeTeamName": "主隊",
}


class AnalyzeGameTests(unittest.TestCase):
    def test_schedule_deduplication_prefers_current_rescheduled_row(self):
        games = [
            {
                "GameSno": 14,
                "PresentStatus": 0,
                "GameResult": "1",
                "GameDate": "2026-04-04T00:00:00",
            },
            {
                "GameSno": 14,
                "PresentStatus": 1,
                "GameResult": "0",
                "GameDate": "2026-06-27T00:00:00",
            },
            {"GameSno": 15, "PresentStatus": 1, "GameResult": "0"},
        ]
        result = deduplicate_schedule(games)
        self.assertEqual([game["GameSno"] for game in result], [14, 15])
        self.assertEqual(result[0]["GameDate"], "2026-06-27T00:00:00")

    def test_success_uses_runs_after_steal_event(self):
        rows = [
            row(1, "1", 3, 3, 2, first="2", pitch=10),
            row(
                1,
                "1",
                3,
                3,
                2,
                first="2",
                content="壞球。一壘跑者甲 盜壘上二壘。",
                pitch=11,
            ),
            row(1, "1", 3, 3, 2, second="2", pitch=12),
            row(
                1,
                "1",
                3,
                3,
                2,
                second="2",
                visiting_score=1,
                content="安打，二壘跑者得分。",
                pitch=13,
            ),
            row(
                1,
                "1",
                4,
                4,
                2,
                visiting_score=1,
                content="打者出局。3人出局。",
                pitch=14,
            ),
            row(1, "2", 1, 1, 0, visiting_score=1, pitch=15),
            row(1, "2", 1, 1, 2, visiting_score=1, content="3人出局。", pitch=16),
            row(2, "1", 1, 1, 0, visiting_score=1, pitch=17),
            row(
                2,
                "1",
                1,
                1,
                2,
                visiting_score=3,
                content="3人出局。",
                pitch=18,
            ),
        ]
        result = analyze_game(META, game_data(rows))[0]
        self.assertEqual(result["Outcome"], "steal_success")
        self.assertEqual(result["RequestedRE"], 1)
        self.assertEqual(result["CurrentHalfRemainingRunsAfterDecision"], 1)
        self.assertEqual(result["NextHalfRuns"], 2)
        self.assertEqual(result["TwoHalfRunsAfterDecision"], 3)
        self.assertTrue(result["EventTransitionMatches"])
        self.assertEqual(result["PostStealBase"], "second")

    def test_success_then_throwing_error_marks_third_base(self):
        rows = [
            row(
                1,
                "1",
                3,
                3,
                2,
                first="2",
                content=(
                    "壞球。一壘跑者甲 盜壘上二壘。"
                    "二壘跑者甲 因捕手傳球失誤上三壘。"
                ),
                pitch=11,
            ),
            row(1, "1", 3, 3, 2, third="2", pitch=12),
            row(1, "1", 3, 3, 2, content="3人出局。", pitch=13),
            row(1, "2", 1, 1, 0, pitch=14),
            row(1, "2", 1, 1, 2, content="3人出局。", pitch=15),
            row(2, "1", 1, 1, 0, pitch=16),
            row(2, "1", 1, 1, 2, content="3人出局。", pitch=17),
        ]
        result = analyze_game(META, game_data(rows))[0]
        self.assertEqual(result["Outcome"], "steal_success")
        self.assertTrue(result["EventTransitionMatches"])
        self.assertEqual(result["PostStealBase"], "third")

    def test_success_then_throwing_error_scores_runner(self):
        rows = [
            row(
                1,
                "1",
                3,
                3,
                2,
                first="2",
                visiting_score=1,
                content=(
                    "一壘跑者甲 盜壘上二壘。"
                    "二壘跑者甲 因傳球失誤回本壘得分。"
                ),
                pitch=11,
            ),
            row(1, "1", 3, 3, 2, visiting_score=1, pitch=12),
            row(1, "1", 3, 3, 2, visiting_score=1, content="3人出局。", pitch=13),
            row(1, "2", 1, 1, 0, visiting_score=1, pitch=14),
            row(1, "2", 1, 1, 2, visiting_score=1, content="3人出局。", pitch=15),
            row(2, "1", 1, 1, 0, visiting_score=1, pitch=16),
            row(2, "1", 1, 1, 2, visiting_score=1, content="3人出局。", pitch=17),
        ]
        result = analyze_game(META, game_data(rows))[0]
        self.assertTrue(result["EventTransitionMatches"])
        self.assertEqual(result["PostStealBase"], "home")

    def test_failure_uses_next_half_and_checks_retained_hitter(self):
        rows = [
            row(
                1,
                "1",
                4,
                4,
                2,
                first="3",
                content="壞球。一壘跑者甲出局-盜壘刺 3人出局。",
                pitch=10,
                hitter="保留打者",
            ),
            row(1, "2", 1, 1, 0, pitch=11),
            row(1, "2", 1, 1, 2, content="3人出局。", pitch=12),
            row(2, "1", 1, 4, 0, pitch=13, hitter="保留打者"),
            row(
                2,
                "1",
                1,
                4,
                2,
                visiting_score=1,
                content="3人出局。",
                pitch=14,
                hitter="保留打者",
            ),
        ]
        result = analyze_game(META, game_data(rows))[0]
        self.assertEqual(result["Outcome"], "steal_failure")
        self.assertEqual(result["RequestedRE"], 1)
        self.assertEqual(result["CurrentHalfRemainingRunsAfterDecision"], 0)
        self.assertEqual(result["NextHalfRuns"], 1)
        self.assertTrue(result["RetentionMatches"])
        self.assertTrue(result["EventTransitionMatches"])

    def test_no_steal_uses_next_half_runs(self):
        rows = [
            row(
                1,
                "1",
                4,
                4,
                2,
                first="3",
                content="打者飛球出局。3人出局。",
                pitch=10,
            ),
            row(1, "2", 1, 1, 0, pitch=11),
            row(1, "2", 1, 1, 2, content="3人出局。", pitch=12),
            row(2, "1", 1, 5, 0, pitch=13),
            row(
                2,
                "1",
                1,
                5,
                2,
                visiting_score=2,
                content="3人出局。",
                pitch=14,
            ),
        ]
        result = analyze_game(META, game_data(rows))[0]
        self.assertEqual(result["Outcome"], "no_steal")
        self.assertEqual(result["RequestedRE"], 2)
        self.assertEqual(result["NextHalfRuns"], 2)
        self.assertEqual(result["CurrentHalfRemainingRunsFromState"], 0)

    def test_excludes_wrong_inning_outs_or_base_state(self):
        rows = [
            row(9, "1", 1, 1, 2, first="1"),
            row(1, "1", 1, 1, 1, first="1"),
            row(2, "1", 1, 1, 2, first="1", second="2"),
        ]
        self.assertEqual(analyze_game(META, game_data(rows)), [])


class AdministrativeRowFilterTests(unittest.TestCase):
    def test_pure_substitution_announcement_is_administrative(self):
        self.assertTrue(
            is_administrative_only_row(row(6, "2", 1, 9, 2, content="更換守備：陳重廷-=>二壘手。\r\n"))
        )
        self.assertTrue(
            is_administrative_only_row(row(6, "2", 3, 2, 1, content="更換投手：布雷克=>林子崴。\r\n"))
        )

    def test_substitution_combined_with_a_real_pitch_is_kept(self):
        self.assertFalse(
            is_administrative_only_row(
                row(6, "2", 3, 2, 1, content="更換投手：布雷克=>林子崴。\r\n壞球。")
            )
        )

    def test_normal_pitch_row_is_not_administrative(self):
        self.assertFalse(is_administrative_only_row(row(1, "1", 1, 1, 0, content="壞球。")))
        self.assertFalse(is_administrative_only_row(row(1, "1", 1, 1, 0, content="")))

    def test_remove_administrative_rows_filters_only_matching_rows(self):
        rows = [
            row(6, "2", 1, 9, 2, content="更換守備：陳重廷-=>二壘手。\r\n"),
            row(6, "2", 1, 9, 0, content="好球沒揮棒。"),
            row(6, "2", 1, 9, 0, content="打者出局-三振出局。 1人出局。"),
        ]
        cleaned = remove_administrative_rows(rows)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual([r["OutCnt"] for r in cleaned], [0, 0])

    def test_stale_admin_row_no_longer_corrupts_analyze_game(self):
        # 重現實際抓到的錯誤模式：半局交替時的守備公告列殘留上一個狀態的
        # OutCnt=2、FirstBase 有人，若未過濾會被誤判成「兩出局、一壘有人」
        # 的目標情境（實際上這半局才剛要開始，真正第一球是 0 出局空壘）。
        rows = [
            row(1, "1", 1, 1, 2, content="打者飛球出局。3人出局。", pitch=10),
            row(1, "2", 1, 1, 2, first="9", content="更換守備：某人-=>游擊手。\r\n", pitch=11),
            row(1, "2", 1, 1, 0, pitch=12),
            row(1, "2", 1, 1, 1, content="打者出局。1人出局。", pitch=13),
            row(1, "2", 2, 2, 2, content="打者出局。3人出局。", pitch=14),
            row(2, "1", 1, 5, 0, pitch=15),
            row(2, "1", 1, 5, 2, visiting_score=2, content="3人出局。", pitch=16),
        ]
        results = analyze_game(META, game_data(rows))
        # 過濾後，半局(1,"2")真正的兩出局狀態（第14列）是空壘，不符合
        # is_target_state（需要一壘有人），所以不應該產生任何決策樣本。
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
