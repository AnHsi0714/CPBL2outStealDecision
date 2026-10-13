import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import unittest

from mlb_find_2out_first_base import analyze_game, build_event_stream, build_pa_records, is_target_state


def runner(rid, start, end, is_out, event, play_index, name="R"):
    return {
        "movement": {"start": start, "end": end, "isOut": is_out},
        "details": {"event": event, "runner": {"id": rid, "fullName": name}, "playIndex": play_index},
    }


def pitch(index, is_pitch=True, event=None, outs=0):
    details = {"event": event} if event else {}
    return {"index": index, "isPitch": is_pitch, "details": details, "count": {"outs": outs}}


def play(inning, is_top, batter_id, events, runners, outs_after, away=0, home=0):
    return {
        "about": {"inning": inning, "isTopInning": is_top},
        "matchup": {"batter": {"id": batter_id, "fullName": f"B{batter_id}"}},
        "playEvents": events,
        "runners": runners,
        "count": {"outs": outs_after},
        "result": {"awayScore": away, "homeScore": home, "eventType": "field_out", "event": "Field Out"},
    }


class OutsAreCountedFromRunnerMovementsTest(unittest.TestCase):
    """牽制盜壘出局這類非投球事件的 count.outs 是事件「後」的出局數，若直接當事件前使用，
    1 出局的牽制盜壘失敗會被誤歸成 2 出局，進而污染兩出局決策樣本。"""

    def test_pickoff_caught_stealing_at_one_out_is_not_a_two_out_decision(self):
        half = [
            play(3, True, 1, [pitch(0, outs=0)], [runner(1, None, "1B", False, "Single", 0)], 0),
            # 1 出局時牽制盜壘出局：事件本身的 count.outs 已經是 2（事件後）
            play(3, True, 2,
                 [pitch(0, False, "Pickoff Caught Stealing 2B", outs=2), pitch(1, outs=2)],
                 [runner(1, "1B", None, True, "Pickoff Caught Stealing 2B", 0), runner(2, None, "1B", False, "Single", 1)],
                 2),
        ]
        events = build_event_stream(half)
        steal_event = next(e for e in events if e["hasStealMention"])
        self.assertEqual(steal_event["outs"], 0)  # 這個半局第一個打席時還是 0 出局
        self.assertFalse(is_target_state(steal_event, 3))

    def test_caught_stealing_on_a_pitch_event_is_recognised_as_third_out_decision(self):
        """盜壘發生在投球事件上時 playEvent 沒有 event 名稱，盜壘標記只在 runners[].details.event。"""
        half = [
            play(2, True, 1, [pitch(0, outs=0)], [runner(1, None, "1B", False, "Single", 0)], 0),
            play(2, True, 2, [pitch(0, outs=0)], [runner(2, None, None, True, "Strikeout", 0)], 1),
            play(2, True, 3, [pitch(0, outs=1)], [runner(3, None, None, True, "Groundout", 0)], 2),
            # 2 出局、一壘有人：投球事件上盜壘失敗成為第三出局
            play(2, True, 4, [pitch(0, outs=2), pitch(1, outs=2)],
                 [runner(1, "1B", None, True, "Caught Stealing 2B", 1)], 3),
        ]
        game = {"liveData": {"plays": {"allPlays": half}}, "gameData": {"teams": {"away": {"name": "A"}, "home": {"name": "H"}}}}
        decisions = analyze_game({"GamePk": 1, "GameDate": "2025-04-01"}, game)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["Outcome"], "steal_failure")
        self.assertEqual(decisions[0]["BatterId"], 4)


class PlateAppearanceRecordsTest(unittest.TestCase):
    def test_first_pa_of_a_half_inning_records_runs_scored_not_team_total(self):
        """半局第一個打席沒有前一個 play，以前把 score_before 記 0，結果該打席的得分變成該隊累積總分，
        污染所有「空壘」起點的壘包推進池。"""
        first_inning = play(1, True, 1, [pitch(0)], [runner(1, None, "score", False, "Home Run", 0)], 0, away=1)
        fifth_inning = play(5, True, 2, [pitch(0)], [runner(2, None, None, True, "Groundout", 0)], 1, away=7)
        records_first = build_pa_records({"liveData": {"plays": {"allPlays": [first_inning]}}})
        records_fifth = build_pa_records({"liveData": {"plays": {"allPlays": [fifth_inning]}}})
        self.assertEqual(records_first[0]["runs"], 1)
        self.assertEqual(records_fifth[0]["runs"], 0)  # 該隊累積 7 分，但這個打席沒有得分

    def test_outs_after_is_taken_from_the_next_plate_appearance_start(self):
        half = [
            play(1, True, 1, [pitch(0)], [runner(1, None, None, True, "Groundout", 0)], 1),
            play(1, True, 2, [pitch(0)], [runner(2, None, None, True, "Flyout", 0)], 2),
        ]
        records = build_pa_records({"liveData": {"plays": {"allPlays": half}}})
        self.assertEqual(records[0]["outs_after"], 1)  # 不是下一個打席結束後的 2
        self.assertEqual(records[1]["outs_after"], 3)


class ExtraInningsPlacedRunnerTest(unittest.TestCase):
    def test_tenth_inning_starts_with_a_runner_on_second(self):
        half = [play(10, False, 1, [pitch(0)], [runner(9, "2B", "3B", False, "Wild Pitch", 0)], 0)]
        events = build_event_stream(half)
        self.assertTrue(events[0]["on2b"])
        self.assertFalse(events[0]["on1b"])


if __name__ == "__main__":
    unittest.main()
