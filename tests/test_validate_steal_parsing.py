import unittest

from validate_steal_parsing import compare_game, count_parsed_steals, official_steal_totals


def row(side, content, out_count=0):
    return {"VisitingHomeType": side, "Content": content, "OutCnt": out_count}


class CountParsedStealsTests(unittest.TestCase):
    def test_counts_success_and_caught_per_side(self):
        rows = [
            row("1", "一壘跑者甲 盜壘上二壘。"),
            row("1", "一壘跑者乙出局-盜壘刺 2人出局。"),
            row("2", "二壘跑者丙 盜壘上三壘。"),
        ]
        counts = count_parsed_steals(rows)
        self.assertEqual(counts["1"], {"success": 1, "caught": 1})
        self.assertEqual(counts["2"], {"success": 1, "caught": 0})

    def test_double_steal_scoring_from_third_counts_as_success(self):
        rows = [
            row("1", "一壘跑者甲 盜壘上二壘。三壘跑者乙 雙盜壘回本壘得分。"),
        ]
        counts = count_parsed_steals(rows)
        # 兩個跑者都算一次成功盜壘：甲上二壘、乙回本壘。
        self.assertEqual(counts["1"]["success"], 2)

    def test_ignores_administrative_rows_even_if_they_mention_steal_text(self):
        rows = [
            row("1", "更換代跑：某人-=>甲。\r\n"),
            row("1", "一壘跑者甲 盜壘上二壘。"),
        ]
        counts = count_parsed_steals(rows)
        self.assertEqual(counts["1"]["success"], 1)

    def test_rows_without_steal_mention_are_ignored(self):
        rows = [row("1", "壞球。"), row("1", "打者出局。1人出局。")]
        self.assertEqual(count_parsed_steals(rows), {})

    def test_caught_stealing_overturned_safe_by_error_still_counts_as_caught(self):
        # CPBL 官方 StealBaseFailCnt 仍把這種情況算成盜壘刺，跑者只是因為
        # 野手失誤才安全上壘，不能被 STEAL_SUCCESS_PATTERN 誤判成成功盜壘。
        rows = [row("1", "一壘跑者陳傑憲 盜壘刺-因野手失誤進壘上二壘。")]
        counts = count_parsed_steals(rows)
        self.assertEqual(counts["1"], {"success": 0, "caught": 1})

    def test_long_indigenous_style_player_name_does_not_break_matching(self):
        # 原住民選手名字（含全形間隔號）比一般漢字姓名長，曾經因為字數上限
        # 卡太緊漏掉配對；同時確認雙盜壘兩名跑者各自進一個壘都算成功。
        rows = [
            row(
                "1",
                "壞球。 二壘跑者吉力吉撈．鞏冠 雙盜壘上三壘。(重播輔助判決-原判) "
                "一壘跑者朱育賢 雙盜壘上二壘。",
            )
        ]
        counts = count_parsed_steals(rows)
        self.assertEqual(counts["1"]["success"], 2)

    def test_pattern_does_not_spill_across_sentence_boundary(self):
        # [^。] 限制確保不會因為字數上限拉太寬，誤把下一句無關的盜壘描述
        # 併進同一次配對（用一個刻意超長、中間夾著句號的例子驗證邊界）。
        rows = [
            row(
                "1",
                "一壘跑者甲出局-盜壘刺 2人出局。這句話很長很長很長很長很長很長很長很長。"
                "二壘跑者乙 盜壘上三壘。",
            )
        ]
        counts = count_parsed_steals(rows)
        self.assertEqual(counts["1"], {"success": 1, "caught": 1})


class OfficialStealTotalsTests(unittest.TestCase):
    def test_sums_across_all_players_on_each_side(self):
        batting_rows = [
            {"VisitingHomeType": "1", "StealBaseOKCnt": 2, "StealBaseFailCnt": 1},
            {"VisitingHomeType": "1", "StealBaseOKCnt": 1, "StealBaseFailCnt": 0},
            {"VisitingHomeType": "2", "StealBaseOKCnt": 0, "StealBaseFailCnt": 1},
        ]
        totals = official_steal_totals(batting_rows)
        self.assertEqual(totals["1"], {"success": 3, "caught": 1})
        self.assertEqual(totals["2"], {"success": 0, "caught": 1})


class CompareGameTests(unittest.TestCase):
    def test_reports_diff_for_both_sides_even_when_one_has_no_activity(self):
        parsed = {"1": {"success": 2, "caught": 1}}
        official = {"1": {"success": 2, "caught": 0}}
        result = compare_game(101, parsed, official)
        by_side = {r["side"]: r for r in result}
        self.assertEqual(by_side["1"]["successDiff"], 0)
        self.assertEqual(by_side["1"]["caughtDiff"], 1)
        # 客隊完全沒盜壘紀錄，不應該報錯，差異應該是 0。
        self.assertEqual(by_side["2"]["successDiff"], 0)
        self.assertEqual(by_side["2"]["caughtDiff"], 0)


if __name__ == "__main__":
    unittest.main()
