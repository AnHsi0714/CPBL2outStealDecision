import os
import csv
import time
import random
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
GAMEFEED_URL = "https://baseballsavant.mlb.com/gf"
DATA_DIR = "mlb_data"


def polite_sleep(base: float = 1.5, jitter: float = 1.5):
    """隨機延遲，降低被判定為爬蟲而封鎖的機率"""
    time.sleep(base + random.uniform(0, jitter))


def get_schedule(start_date: str, end_date: str) -> list[dict]:
    """抓日期區間內的比賽（gamePk、日期），用來確認要抓哪些場次"""
    params = {"sportId": 1, "startDate": start_date, "endDate": end_date}
    resp = session.get(SCHEDULE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    games = []
    for date_entry in data.get("dates", []):
        for g in date_entry.get("games", []):
            games.append({
                "GamePk": g["gamePk"],
                "GameDate": date_entry["date"],
                "AwayTeam": g["teams"]["away"]["team"]["name"],
                "HomeTeam": g["teams"]["home"]["team"]["name"],
            })
    return games


def get_game_feed(game_pk: int) -> dict:
    """單場比賽的 Statcast 逐球資料（Baseball Savant /gf 端點，pybaseball 底層也用這個）"""
    resp = session.get(GAMEFEED_URL, params={"game_pk": game_pk}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_game(game_meta: dict, feed: dict) -> list[dict]:
    """把單場 /gf 回傳的逐球資料拆成一張表：逐球紀錄（含出局數、壘包狀態、盜壘相關描述）"""
    game_id = {
        "GamePk": game_meta["GamePk"],
        "GameDate": game_meta["GameDate"],
        "AwayTeam": game_meta["AwayTeam"],
        "HomeTeam": game_meta["HomeTeam"],
    }

    playbyplay = []
    for row in feed.get("team_home", []) + feed.get("team_away", []):
        events = row.get("events") or ""
        des = row.get("des") or ""
        playbyplay.append({
            **game_id,
            "Inning": row.get("inning"),
            "HalfInning": row.get("half_inning"),
            "AbNumber": row.get("ab_number"),
            "PitchNumber": row.get("pitch_number"),
            "TeamBatting": row.get("team_batting"),
            "TeamFielding": row.get("team_fielding"),
            "BatterName": row.get("batter_name"),
            "PitcherName": row.get("pitcher_name"),
            # outs/runnerOnXB 都是「這一球投出前」的即時狀態
            "Outs": row.get("outs"),
            "On1B": bool(row.get("runnerOn1B")),
            "On2B": bool(row.get("runnerOn2B")),
            "On3B": bool(row.get("runnerOn3B")),
            "Events": events,
            "Description": des,
            "HasStealMention": "steal" in events.lower() or "steal" in des.lower(),
        })

    return playbyplay


def parse_scoreboard(game_meta: dict, feed: dict) -> list[dict]:
    """逐局比分/安打/失誤，只適合拿來做賽況總覽/核對用（跟 CPBL 版的用途一樣）"""
    game_id = {
        "GamePk": game_meta["GamePk"],
        "GameDate": game_meta["GameDate"],
        "AwayTeam": game_meta["AwayTeam"],
        "HomeTeam": game_meta["HomeTeam"],
    }

    innings = feed.get("scoreboard", {}).get("linescore", {}).get("innings", [])
    scoreboard = []
    for inning in innings:
        for side, team_name in (("home", game_meta["HomeTeam"]), ("away", game_meta["AwayTeam"])):
            side_data = inning.get(side, {})
            scoreboard.append({
                **game_id,
                "Team": team_name,
                "HomeOrAway": side,
                "InningNum": inning.get("num"),
                "Runs": side_data.get("runs"),
                "Hits": side_data.get("hits"),
                "Errors": side_data.get("errors"),
                "LeftOnBase": side_data.get("leftOnBase"),
            })
    return scoreboard


def parse_batting(game_meta: dict, feed: dict) -> list[dict]:
    """球員逐場打擊盒分，只列有上場打擊的人（stats.batting 是空字典 {} 的是純投手，略過）"""
    game_id = {
        "GamePk": game_meta["GamePk"],
        "GameDate": game_meta["GameDate"],
        "AwayTeam": game_meta["AwayTeam"],
        "HomeTeam": game_meta["HomeTeam"],
    }

    teams = feed.get("boxscore", {}).get("teams", {})
    batting = []
    for side, team_name in (("home", game_meta["HomeTeam"]), ("away", game_meta["AwayTeam"])):
        players = teams.get(side, {}).get("players", {})
        for p in players.values():
            bat = p.get("stats", {}).get("batting", {})
            if not bat.get("plateAppearances"):
                continue
            batting.append({
                **game_id,
                "Team": team_name,
                "HomeOrAway": side,
                "PlayerName": p.get("person", {}).get("fullName"),
                "PlateAppearances": bat.get("plateAppearances"),
                "AtBats": bat.get("atBats"),
                "Hits": bat.get("hits"),
                "Doubles": bat.get("doubles"),
                "Triples": bat.get("triples"),
                "HomeRuns": bat.get("homeRuns"),
                "RBI": bat.get("rbi"),
                "Runs": bat.get("runs"),
                "BaseOnBalls": bat.get("baseOnBalls"),
                "StrikeOuts": bat.get("strikeOuts"),
                "StolenBases": bat.get("stolenBases"),
                "CaughtStealing": bat.get("caughtStealing"),
            })
    return batting


def fetch_games(games: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """依序抓取一批比賽，每場之間隨機延遲"""
    all_pbp, all_sb, all_bat = [], [], []

    for i, g in enumerate(games, 1):
        print(f"[{i}/{len(games)}] 抓取 {g['GameDate']} GamePk={g['GamePk']} "
              f"{g['AwayTeam']} @ {g['HomeTeam']}")

        try:
            feed = get_game_feed(g["GamePk"])
        except Exception as e:
            print(f"  失敗，略過本場：{e}")
            polite_sleep()
            continue

        all_pbp.extend(parse_game(g, feed))
        all_sb.extend(parse_scoreboard(g, feed))
        all_bat.extend(parse_batting(g, feed))
        polite_sleep()

    return all_pbp, all_sb, all_bat


def save_to_csv(rows: list[dict], out_file: str):
    if not rows:
        print(f"{out_file}：沒有資料，不寫檔")
        return
    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"已儲存 {len(rows)} 筆到 {out_file}")


if __name__ == "__main__":
    START_DATE = "2026-08-01"
    END_DATE = "2026-08-20"

    games = get_schedule(START_DATE, END_DATE)
    print(f"共 {len(games)} 場比賽（{START_DATE} ~ {END_DATE}）")

    pbp_rows, sb_rows, bat_rows = fetch_games(games)

    os.makedirs(DATA_DIR, exist_ok=True)
    tag = f"{START_DATE}_{END_DATE}"
    save_to_csv(pbp_rows, os.path.join(DATA_DIR, f"mlb_playbyplay_{tag}.csv"))
    save_to_csv(sb_rows, os.path.join(DATA_DIR, f"mlb_scoreboard_{tag}.csv"))
    save_to_csv(bat_rows, os.path.join(DATA_DIR, f"mlb_batting_{tag}.csv"))
