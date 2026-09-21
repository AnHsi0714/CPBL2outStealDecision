"""從 NPB 官網（npb.jp）補抓 yakyuu.db 完全沒有的盜壘資料，產出跟 CPBL_steal_getData.py／
MLB_steal_getData.py 同樣形狀的三張表（playbyplay／scoreboard／batting）。

背景：yakyuu（third-party NPB 資料整理專案，見 yakyuu/ 目錄，另一個獨立 git repo）的
yakyuu.db 裡完全沒有存盜壘欄位——games 表沒有、event 表沒有、batting 表也沒有，連
yakyuu 自己的 parser（Final/imports/eventfiles.py、batting_lineup_parser.py）都沒去解析
NPB 官網頁面上其實就有的「盗塁」欄位。所以能重用的只有 yakyuu.db 現成的賽程/隊名/
逐局比分/一般打擊盒分，盜壘本身這塊得另外對 npb.jp 發請求現抓。

NPB 官網跟 CPBL 的落差（實測 npb.jp/scores/.../box.html、playbyplay.html 得到的結論）：
- box.html 的打擊表只有「盗塁」一欄＝盜壘成功次數，對應 CPBL 的 StealBaseOKCnt；
  沒有對應 StealBaseFailCnt 的官方欄位，盜壘刺次數只能從 playbyplay 文字裡自己算，
  不像 CPBL 官方 box score 本身就兩個數字都有——這裡算出來的 StealBaseFailCnt
  沒有獨立官方數字可以核對，跟 StealBaseOKCnt（有官方數字可以互相驗證）不一樣。
- playbyplay.html 是「逐打席」等級（每列是一個打席的最終結果），不是 CPBL 那種逐球
  紀錄，沒有 PitchCnt／逐球比分可以取得，所以這裡沒有這兩欄。
- 盜壘（成功或刺）在 playbyplay.html 裡是獨立一列，格式固定為
  「（走者・<a>姓名</a>）N塁盗塁成功/失敗」，跟打席結果列穿插在一起，但這一列本身
  沒有出局數/壘包狀態以外的其他欄位（第三、四格是空的），也没有当下是哪位打者在
  打擊——所以 BatterName 是用「這個半局裡，下一個有出現打席結果的打者」回填的
  （盜壘一定發生在某個打席進行中，官網會先列出中途發生的盜壘事件，再列出那個打席
  最終結果），如果盜壘刺剛好是整個半局的第三個出局數（等於該半局沒有下一個打席），
  BatterName 會是 None，這是預期行為，不是漏抓。
"""

import os
import re
import csv
import sys
import time
import random
import sqlite3
import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # 避免 Windows cp950 終端機印到日文字元時 UnicodeEncodeError 當掉

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

BASE_URL = "https://npb.jp/scores"
DATA_DIR = "npb_data"
YAKYUU_DB = "yakyuu/yakyuu.db"


def polite_sleep(base: float = 3.0, jitter: float = 2.0):
    """隨機延遲，降低被判定為爬蟲而封鎖的機率"""
    time.sleep(base + random.uniform(0, jitter))


def get_schedule(season: int, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """從 yakyuu.db 讀賽程（yakyuu 自己的資料庫，這部分不用再對官網發請求）"""
    conn = sqlite3.connect(YAKYUU_DB)
    cur = conn.cursor()

    query = "SELECT game_id, date, home_team_id, away_team_id FROM games WHERE season = ?"
    params: list = [season]
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY game_id"
    cur.execute(query, params)
    rows = cur.fetchall()

    cur.execute("SELECT team_id, team_name FROM teams")
    team_names = dict(cur.fetchall())
    conn.close()

    return [
        {
            "GameId": game_id,
            "GameDate": game_date,
            "HomeTeamId": home_id,
            "AwayTeamId": away_id,
            "HomeTeam": team_names.get(home_id, home_id),
            "AwayTeam": team_names.get(away_id, away_id),
        }
        for game_id, game_date, home_id, away_id in rows
    ]


def get_html(game_id: str, page: str) -> str:
    """抓官網單一頁面（box.html 或 playbyplay.html）"""
    url = f"{BASE_URL}/{game_id}/{page}"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


PLAYER_ID_RE = re.compile(r"/players/(\d+)")
OUT_RE = re.compile(r"(\d+)アウト")
COUNT_RE = re.compile(r"(\d+)-(\d+)")
STEAL_RUNNER_RE = re.compile(r"（走者・.*?）(.+)")


def extract_player_id(cell) -> str | None:
    link = cell.find("a", href=True) if cell else None
    if not link:
        return None
    m = PLAYER_ID_RE.search(link["href"])
    return m.group(1) if m else None


def parse_on_base(bases_text: str) -> tuple[bool, bool, bool]:
    bases_text = (bases_text or "").strip()
    return ("1塁" in bases_text or "満塁" in bases_text,
            "2塁" in bases_text or "満塁" in bases_text,
            "3塁" in bases_text or "満塁" in bases_text)


def map_inning_header(header_text: str) -> tuple[int, str] | None:
    """比照 yakyuu/Final/imports/eventfiles.py 的 map_inning_notation：
    「1回表」＝第1局上（客隊攻擊），「1回裏」＝第1局下（主隊攻擊）"""
    m = re.search(r"(\d+)回表", header_text)
    if m:
        return int(m.group(1)), "top"
    m = re.search(r"(\d+)回裏", header_text)
    if m:
        return int(m.group(1)), "bottom"
    return None


def parse_box_steals(html: str, game: dict) -> list[dict]:
    """box.html 打擊表的「盗塁」欄＝盜壘成功次數（NPB 官方只公布這個，沒有盜壘刺）。
    比照 yakyuu/Final/imports/batting_lineup_parser.py 已驗證過的慣例：
    同一頁裡第一張打擊表＝客隊，第二張＝主隊。"""
    soup = BeautifulSoup(html, "html.parser")
    steals = []
    table_count = 0

    for table in soup.find_all("table"):
        header_cells = None
        rows = table.find_all("tr")
        if not rows:
            continue
        first_row_cells = rows[0].find_all(["th", "td"])
        header_text = [c.get_text(strip=True) for c in first_row_cells]
        if "盗塁" not in header_text or "選手" not in header_text:
            continue

        steal_col = header_text.index("盗塁")
        table_count += 1
        team_id = game["AwayTeamId"] if table_count == 1 else game["HomeTeamId"]
        if table_count > 2:
            break

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= steal_col:
                continue
            player_cell = cells[2] if len(cells) > 2 else None
            player_id = extract_player_id(player_cell)
            if not player_id:
                continue
            sb_text = cells[steal_col].get_text(strip=True)
            if not sb_text.isdigit():
                continue
            steals.append({
                "GameId": game["GameId"],
                "PlayerId": player_id,
                "TeamId": team_id,
                "StealBaseOKCnt": int(sb_text),
            })

    return steals


def parse_playbyplay(html: str, game: dict) -> list[dict]:
    """逐打席事件＋穿插其中的獨立盜壘事件列，兩者都是同一批 <table> 依文件順序出現。"""
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "table"])

    game_id_block = {
        "GameId": game["GameId"],
        "GameDate": game["GameDate"],
        "AwayTeam": game["AwayTeam"],
        "HomeTeam": game["HomeTeam"],
    }

    current_inning, current_half = None, None
    events = []

    for el in elements:
        if el.name != "table":
            header_match = map_inning_header(el.get_text(strip=True))
            if header_match:
                current_inning, current_half = header_match
            continue

        rows = el.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 5 or current_inning is None:
                continue

            out_text = cells[0].get_text(strip=True)
            out_match = OUT_RE.search(out_text)
            if not out_match:
                continue
            outs = int(out_match.group(1))

            on1b, on2b, on3b = parse_on_base(cells[1].get_text(strip=True))
            batter_id = extract_player_id(cells[2])
            result_text = cells[4].get_text(strip=True)
            battting_team = game["AwayTeam"] if current_half == "top" else game["HomeTeam"]

            if batter_id:
                # 一般打席結果列
                count_match = COUNT_RE.search(cells[3].get_text(strip=True))
                events.append({
                    **game_id_block,
                    "Inning": current_inning,
                    "HalfInning": current_half,
                    "BattingTeam": battting_team,
                    "EventType": "batter_outcome",
                    "BatterId": batter_id,
                    "BatterName": cells[2].get_text(strip=True),
                    "RunnerId": None,
                    "Outs": outs,
                    "On1B": on1b, "On2B": on2b, "On3B": on3b,
                    "BallCnt": int(count_match.group(1)) if count_match else None,
                    "StrikeCnt": int(count_match.group(2)) if count_match else None,
                    "RawText": result_text,
                    "HasStealMention": "盗" in result_text,
                    "StealOutcome": None,
                })
            else:
                # 獨立盜壘事件列：跑者連結在結果欄（cells[4]）裡面，不是打者欄
                runner_id = extract_player_id(cells[4])
                if not runner_id or "盗" not in result_text:
                    continue  # 非盜壘、非打席的未知格式列，跳過並留給後面統計清點
                if "成功" in result_text:
                    outcome = "success"
                elif "失敗" in result_text:
                    outcome = "caught"
                else:
                    outcome = "unknown"
                events.append({
                    **game_id_block,
                    "Inning": current_inning,
                    "HalfInning": current_half,
                    "BattingTeam": battting_team,
                    "EventType": "runner_movement",
                    "BatterId": None,  # 兩段式回填，見下方迴圈
                    "BatterName": None,
                    "RunnerId": runner_id,
                    "Outs": outs,
                    "On1B": on1b, "On2B": on2b, "On3B": on3b,
                    "BallCnt": None,
                    "StrikeCnt": None,
                    "RawText": result_text,
                    "HasStealMention": True,
                    "StealOutcome": outcome,
                })

    # 回填 BatterName／BatterId：同一半局裡，盜壘事件列的打者＝之後第一個出現的打席結果列的打者
    # （盜壘一定發生在某個打席進行中，官網先列盜壘、再列該打席最終結果；如果盜壘刺是
    # 該半局最後一個出局數，半局就結束了，找不到「下一個打席」，維持 None 是預期行為）
    for i, ev in enumerate(events):
        if ev["EventType"] != "runner_movement":
            continue
        for later in events[i + 1:]:
            if later["Inning"] != ev["Inning"] or later["HalfInning"] != ev["HalfInning"]:
                break
            if later["EventType"] == "batter_outcome":
                ev["BatterId"] = later["BatterId"]
                ev["BatterName"] = later["BatterName"]
                break

    return events


def build_scoreboard(games: list[dict]) -> list[dict]:
    """逐局比分：yakyuu.db 的 games 表已經有了，不用再對官網發請求"""
    if not games:
        return []
    conn = sqlite3.connect(YAKYUU_DB)
    cur = conn.cursor()
    game_ids = [g["GameId"] for g in games]
    placeholders = ",".join("?" * len(game_ids))
    cols = ["game_id"] + [f"visitor_inn{i}" for i in range(1, 13)] + [f"home_inn{i}" for i in range(1, 13)]
    cur.execute(f"SELECT {','.join(cols)} FROM games WHERE game_id IN ({placeholders})", game_ids)
    db_rows = {r[0]: r[1:] for r in cur.fetchall()}
    conn.close()

    game_meta = {g["GameId"]: g for g in games}
    scoreboard = []
    for game_id, values in db_rows.items():
        g = game_meta[game_id]
        visitor_inns, home_inns = values[:12], values[12:]
        for side, team, inns in (("away", g["AwayTeam"], visitor_inns), ("home", g["HomeTeam"], home_inns)):
            for inning_num, runs in enumerate(inns, start=1):
                if runs is None:
                    continue
                scoreboard.append({
                    "GameId": game_id, "GameDate": g["GameDate"],
                    "AwayTeam": g["AwayTeam"], "HomeTeam": g["HomeTeam"],
                    "Team": team, "HomeOrAway": side,
                    "InningNum": inning_num, "Runs": runs,
                })
    return scoreboard


def build_batting(games: list[dict], all_box_steals: list[dict], all_playbyplay: list[dict]) -> list[dict]:
    """以 yakyuu.db 現成的一般打擊盒分為底，補上 StealBaseOKCnt（官網 box.html 盗塁欄，
    可跟這裡的加總互相核對）跟 StealBaseFailCnt（playbyplay 盜壘刺文字加總，沒有獨立
    官方數字可以核對，是這份資料裡信心相對低的一欄）"""
    if not games:
        return []
    conn = sqlite3.connect(YAKYUU_DB)
    cur = conn.cursor()
    game_ids = [g["GameId"] for g in games]
    placeholders = ",".join("?" * len(game_ids))
    cols = ["game_id", "player_id", "team", "lineup_position", "position", "pa", "ab",
            "b_h", "b_r", "b_rbi", "b_1b", "b_2b", "b_3b", "b_hr", "b_bb", "b_k"]
    cur.execute(f"SELECT {','.join(cols)} FROM batting WHERE game_id IN ({placeholders})", game_ids)
    db_rows = cur.fetchall()
    conn.close()

    ok_by_key: dict[tuple, int] = {}
    for s in all_box_steals:
        ok_by_key[(s["GameId"], s["PlayerId"])] = ok_by_key.get((s["GameId"], s["PlayerId"]), 0) + s["StealBaseOKCnt"]

    fail_by_key: dict[tuple, int] = {}
    for ev in all_playbyplay:
        if ev["EventType"] == "runner_movement" and ev["StealOutcome"] == "caught" and ev["RunnerId"]:
            key = (ev["GameId"], ev["RunnerId"])
            fail_by_key[key] = fail_by_key.get(key, 0) + 1

    game_meta = {g["GameId"]: g for g in games}
    batting = []
    for row in db_rows:
        (game_id, player_id, team, lineup_position, position, pa, ab,
         b_h, b_r, b_rbi, b_1b, b_2b, b_3b, b_hr, b_bb, b_k) = row
        g = game_meta[game_id]
        key = (game_id, player_id)
        batting.append({
            "GameId": game_id, "GameDate": g["GameDate"],
            "AwayTeam": g["AwayTeam"], "HomeTeam": g["HomeTeam"],
            "PlayerId": player_id, "Team": team,
            "LineupPosition": lineup_position, "Position": position,
            "PA": pa, "AB": ab, "H": b_h, "R": b_r, "RBI": b_rbi,
            "1B": b_1b, "2B": b_2b, "3B": b_3b, "HR": b_hr, "BB": b_bb, "K": b_k,
            "StealBaseOKCnt": ok_by_key.get(key, 0),
            "StealBaseFailCnt": fail_by_key.get(key, 0),
        })
    return batting


def fetch_games(games: list[dict]) -> tuple[list[dict], list[dict]]:
    """依序抓官網 box.html + playbyplay.html，每場之間隨機延遲"""
    all_playbyplay, all_box_steals = [], []

    for i, g in enumerate(games, 1):
        print(f"[{i}/{len(games)}] {g['GameDate']} GameId={g['GameId']} {g['AwayTeamId']}@{g['HomeTeamId']}")

        try:
            box_html = get_html(g["GameId"], "box.html")
            polite_sleep()
            pbp_html = get_html(g["GameId"], "playbyplay.html")
        except Exception as e:
            print(f"  失敗，略過本場：{e}")
            polite_sleep()
            continue

        box_steals = parse_box_steals(box_html, g)
        pbp_events = parse_playbyplay(pbp_html, g)
        all_box_steals.extend(box_steals)
        all_playbyplay.extend(pbp_events)

        # 核對：playbyplay 解析出的盜壘成功次數，理論上要對得上 box.html 官方的「盗塁」加總
        parsed_ok = sum(1 for ev in pbp_events if ev["StealOutcome"] == "success")
        official_ok = sum(s["StealBaseOKCnt"] for s in box_steals)
        if parsed_ok != official_ok:
            print(f"  注意：盜壘成功數對不上——playbyplay 解析出 {parsed_ok}，box.html 官方數字 {official_ok}")

        polite_sleep()

    return all_playbyplay, all_box_steals


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
    SEASON = 2026
    START_DATE = None  # None＝season 內 yakyuu.db 有的全部場次，不額外用日期篩選
    END_DATE = None

    games = get_schedule(SEASON, START_DATE, END_DATE)
    print(f"共 {len(games)} 場比賽（{SEASON} 年整季，來自 yakyuu.db；"
          f"yakyuu.db 目前收錄到的最後日期以外的場次不在此列）")

    pbp_rows, box_steal_rows = fetch_games(games)
    scoreboard_rows = build_scoreboard(games)
    batting_rows = build_batting(games, box_steal_rows, pbp_rows)

    os.makedirs(DATA_DIR, exist_ok=True)
    tag = f"{SEASON}_full"
    save_to_csv(pbp_rows, os.path.join(DATA_DIR, f"npb_playbyplay_{tag}.csv"))
    save_to_csv(scoreboard_rows, os.path.join(DATA_DIR, f"npb_scoreboard_{tag}.csv"))
    save_to_csv(batting_rows, os.path.join(DATA_DIR, f"npb_batting_{tag}.csv"))
