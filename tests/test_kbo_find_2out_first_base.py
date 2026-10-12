import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import unittest

from kbo_find_2out_first_base import (
    analyze_game,
    build_pa_records,
    classify_batter_outcome,
    post_outcome_indices,
    steal_second_kind,
)

META = {"GameId": "20250401AAHH0", "GameDate": "2025-04-01", "AwayTeam": "AA", "HomeTeam": "HH", "GameSno": 2025040101}


def event(kind, text, batter, slot, outs, first=False, second=False, third=False, inning=1, half="top"):
    return {
        "Inning": inning, "HalfInning": half, "BattingTeam": "AA" if half == "top" else "HH",
        "BatterName": batter, "BatterSlot": slot, "Outs": outs,
        "On1B": first, "On2B": second, "On3B": third,
        "EventType": kind, "RawText": text, "Parsed": True,
    }


class OutcomeClassificationTest(unittest.TestCase):
    def test_dropped_third_strike_is_a_reach_not_an_out(self):
        """振落逃過（낫아웃 폭투／포일）打者上到一壘，不能算成一個出局。"""
        self.assertEqual(classify_batter_outcome("A : 스트라이크 낫아웃 폭투")[0], "REACH")
        self.assertEqual(classify_batter_outcome("A : 스트라이크 낫 아웃 (포수->1루수 송구아웃)"), ("OUT", True))

    def test_hit_and_walk_categories(self):
        self.assertEqual(classify_batter_outcome("A : 좌익수 뒤 홈런 (홈런거리:120M)")[0], "HR")
        self.assertEqual(classify_batter_outcome("A : 중견수 왼쪽 앞 1루타")[0], "1B")
        self.assertEqual(classify_batter_outcome("A : 볼넷")[0], "BB_HBP")
        self.assertEqual(classify_batter_outcome("A : 땅볼 실책으로 출루 (유격수 실책)")[0], "REACH")


class StealParsingTest(unittest.TestCase):
    def test_only_single_steal_of_second_from_first_counts(self):
        ok = event("runner_movement", "1루주자 B : 도루로 2루까지 진루", "A", 3, 2, first=True)
        cs = event("runner_movement", "1루주자 B : 도루실패아웃 (포수->유격수 태그아웃)", "A", 3, 2, first=True)
        double = event("runner_movement", "1루주자 B : 이중도루로 2루까지 진루", "A", 3, 2, first=True)
        indifference = event("runner_movement", "1루주자 B : 무관심도루로 2루까지 진루", "A", 3, 2, first=True)
        self.assertEqual(steal_second_kind(ok), "success")
        self.assertEqual(steal_second_kind(cs), "failure")
        self.assertIsNone(steal_second_kind(double))
        self.assertIsNone(steal_second_kind(indifference))


class StrikeThemOutThrowThemOutTest(unittest.TestCase):
    """文字轉播把三振同時阻殺寫成「타자 삼진 아웃」之後接「도루실패아웃」，狀態機看起來像
    「2 出局、一壘有人時盜壘失敗」，其實是 1 出局時起跑的雙殺，不是教練在兩出局的決策。"""

    def half(self):
        return [
            event("batter_outcome", "A : 삼진 아웃", "A", 3, 1, first=True),
            event("runner_movement", "1루주자 B : 도루실패아웃 (포수->2루수 태그아웃)", "A", 3, 2, first=True),
        ]

    def test_runner_row_after_batter_outcome_is_skipped(self):
        self.assertEqual(post_outcome_indices(self.half()), {1})

    def test_it_does_not_become_a_decision(self):
        rows = self.half() + [event("batter_outcome", "C : 삼진 아웃", "C", 4, 0, inning=2)]
        decisions = analyze_game(META, rows)
        self.assertEqual([d for d in decisions if d["InningSeq"] == 1], [])

    def test_a_real_two_out_caught_stealing_before_the_batter_outcome_is_a_decision(self):
        rows = [
            event("runner_movement", "1루주자 B : 도루실패아웃 (포수->유격수 태그아웃)", "A", 3, 2, first=True),
            event("batter_outcome", "A : 삼진 아웃", "A", 3, 0, inning=2),
        ]
        decisions = analyze_game(META, rows)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["Outcome"], "steal_failure")
        self.assertEqual(decisions[0]["BatterSlot"], 3)
        # 打席中途半局結束，下一局由同一棒次（第 3 棒）開打：保留效應成立
        self.assertIs(decisions[0]["RetentionMatches"], True)


class PlateAppearanceGroupingTest(unittest.TestCase):
    def test_pa_runs_and_end_state_come_from_the_group_and_the_next_group(self):
        rows = [
            event("batter_outcome", "A : 중견수 앞 1루타", "A", 1, 0),
            event("runner_movement", "1루주자 X : 2루까지 진루", "A", 1, 0, first=True),
            event("batter_outcome", "B : 좌익수 뒤 홈런 (홈런거리:120M)", "B", 2, 0, first=True, second=True),
            event("runner_movement", "1루주자 A : 홈인", "B", 2, 0, first=True, second=True),
            event("runner_movement", "2루주자 X : 홈인", "B", 2, 0, first=True),
            event("batter_outcome", "C : 삼진 아웃", "C", 3, 0),
        ]
        records = build_pa_records(rows)
        self.assertEqual(records[1]["runs"], 3)  # 全壘打：打者本人＋兩位跑者各自的「홈인」
        self.assertEqual(records[1]["outs_after"], 0)
        self.assertEqual(records[1]["bases_after"], 0)


if __name__ == "__main__":
    unittest.main()
