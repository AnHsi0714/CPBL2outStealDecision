import os
import requests
import re
import json
import time
import random
import csv

DATA_DIR = "cpbl_data"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

BASE_URL = "https://www.cpbl.com.tw"


def polite_sleep(base: float = 3.0, jitter: float = 2.0):
    """隨機延遲，降低被判定為爬蟲而封鎖的機率"""
    time.sleep(base + random.uniform(0, jitter))


def get_schedule(year: int, kind_code: str) -> list[dict]:
    """抓整年賽程（GameSno、日期、對戰組合），用來確認比賽場次範圍"""
    page_url = f"{BASE_URL}/schedule"
    resp = session.get(page_url, timeout=15)
    resp.raise_for_status()

    # getgamedatas 呼叫用的 token 是頁面上第二組（緊接在該 ajax url 之後）
    idx = resp.text.find("/schedule/getgamedatas")
    if idx == -1:
        raise RuntimeError("找不到 getgamedatas 區塊，頁面結構可能變了")
    snippet = resp.text[idx:idx + 600]
    match = re.search(r"RequestVerificationToken:\s*'([^']+)'", snippet)
    if not match:
        raise RuntimeError("找不到 RequestVerificationToken，頁面結構可能變了")
    token = match.group(1)

    payload = {
        "calendar": f"{year}/01/01",
        "location": "",
        "kindCode": kind_code,
    }
    headers = {
        "RequestVerificationToken": token,
        "x-requested-with": "XMLHttpRequest",
        "origin": BASE_URL,
        "referer": page_url,
    }
    r = session.post(f"{BASE_URL}/schedule/getgamedatas", data=payload, headers=headers, timeout=15)
    r.raise_for_status()
    result = r.json()
    if not result.get("Success"):
        raise RuntimeError("取得賽程失敗")

    return json.loads(result["GameDatas"])


def get_live_data(year: int, kind_code: str, game_sno: int, select_month: int):
    """單場比賽的完整回傳（逐球紀錄、逐局比分、雙方球員盒分等都在裡面）"""
    # 第一步：訪問 live 頁面，讓 session 拿到 cookie 裡的 token
    page_url = f"{BASE_URL}/box/live?year={year}&kindCode={kind_code}&gameSno={game_sno}"
    resp = session.get(page_url, timeout=15)
    resp.raise_for_status()

    # 第二步：從頁面 HTML 裡抓出表單裡的 token
    match = re.search(
        r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
        resp.text
    )
    if not match:
        raise RuntimeError("找不到 RequestVerificationToken，頁面結構可能變了")
    form_token = match.group(1)

    # 第三步：用 session（帶著 cookie）POST 到 getlive
    api_url = f"{BASE_URL}/box/getlive"
    payload = {
        "__RequestVerificationToken": form_token,
        "GameSno": game_sno,
        "KindCode": kind_code,
        "Year": year,
        "PrevOrNext": 0,
        "SelectKindCode": kind_code,
        "SelectYear": year,
        "SelectMonth": select_month,
    }
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": BASE_URL,
        "referer": page_url,
        "x-requested-with": "XMLHttpRequest",
    }
    r = session.post(api_url, data=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def parse_game(game_meta: dict, data: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """把單場 getlive 回傳拆成三張表：逐球紀錄 / 逐局比分 / 球員盒分"""
    game_id = {
        "Year": game_meta["Year"],
        "KindCode": game_meta["KindCode"],
        "GameSno": game_meta["GameSno"],
        "GameDate": game_meta["GameDate"][:10],
        "VisitingTeam": game_meta["VisitingTeamName"],
        "HomeTeam": game_meta["HomeTeamName"],
    }

    playbyplay = []
    for row in json.loads(data["LiveLogJson"]):
        content = row.get("Content") or ""
        playbyplay.append({
            **game_id,
            "InningSeq": row.get("InningSeq"),
            "VisitingHomeType": row.get("VisitingHomeType"),  # getlive 實測：1=客隊打擊, 2=主隊打擊
            "BattingOrderInInning": row.get("BattingOrder"),  # 該半局第幾位打者（每局重算，非棒次）
            "HitterLineup": row.get("HitterLineup"),          # 真正的棒次 1-9
            "HitterName": row.get("HitterName"),
            "PitcherName": row.get("PitcherName"),
            "PitchCnt": row.get("PitchCnt"),
            "StrikeCnt": row.get("StrikeCnt"),
            "BallCnt": row.get("BallCnt"),
            # OutCnt/壘包狀態是「這一球當下」的即時狀態：打席中途發生盜壘、牽制、跑者進佔等動作時會立刻反映在下一球的紀錄上
            "OutCnt": row.get("OutCnt"),
            "On1B": bool(row.get("FirstBase")),
            "On2B": bool(row.get("SecondBase")),
            "On3B": bool(row.get("ThirdBase")),
            "IsScoreCnt": row.get("IsScoreCnt"),
            "VisitingScore": row.get("VisitingScore"),
            "HomeScore": row.get("HomeScore"),
            # ActionName/BattingActionName 相反：是整個打席「結束後」的最終結果，CPBL 會回填到該打席每一球的紀錄上
            "ActionName": row.get("ActionName"),
            "BattingActionName": row.get("BattingActionName"),
            "Content": content,
            "HasStealMention": "盜" in content,  # 只標記文字裡有沒有提到盜壘，成功/失敗/發生在哪一球需另外判讀
        })

    scoreboard = [
        {**game_id, **{k: row.get(k) for k in (
            "TeamAbbr", "VisitingHomeType", "InningSeq", "ScoreCnt", "HittingCnt", "ErrorCnt"
        )}}
        for row in json.loads(data["ScoreboardJson"])
    ]

    batting = [
        {**game_id, **{k: row.get(k) for k in (
            "VisitingHomeType", "HitterName", "HitterUniformNo", "RoleType",
            "PlateAppearances", "HitCnt", "RunBattedINCnt", "ScoreCnt",
            "OneBaseHitCnt", "TwoBaseHitCnt", "ThreeBaseHitCnt", "HomeRunCnt",
            "BasesONBallsCnt", "StrikeOutCnt", "StealBaseOKCnt", "StealBaseFailCnt",
        )}}
        for row in json.loads(data["BattingJson"])
    ]

    return playbyplay, scoreboard, batting


def fetch_games(games: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """依序抓取一批比賽，每場之間隨機延遲。games 元素需含 Year/KindCode/GameSno/GameDate/VisitingTeamName/HomeTeamName"""
    all_pbp, all_sb, all_bat = [], [], []

    for i, g in enumerate(games, 1):
        game_sno = g["GameSno"]
        year = g["Year"]
        kind_code = g["KindCode"]
        month = int(g["GameDate"][5:7])

        print(f"[{i}/{len(games)}] 抓取 {g['GameDate'][:10]} GameSno={game_sno} "
              f"{g['VisitingTeamName']} @ {g['HomeTeamName']}")

        try:
            data = get_live_data(year, kind_code, game_sno, month)
        except Exception as e:
            print(f"  失敗，略過本場：{e}")
            polite_sleep()
            continue

        if not data.get("Success"):
            print("  API 回傳 Success=False，略過本場")
            polite_sleep()
            continue

        pbp, sb, bat = parse_game(g, data)
        all_pbp.extend(pbp)
        all_sb.extend(sb)
        all_bat.extend(bat)

        polite_sleep()  # 每抓完一場比賽就休息一下，避免被鎖

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
    YEAR = 2026
    KIND_CODE = "A"
    GAME_SNO_START = 226
    GAME_SNO_END = 240

    schedule = get_schedule(YEAR, KIND_CODE)
    games = [g for g in schedule if GAME_SNO_START <= g["GameSno"] <= GAME_SNO_END]
    print(f"共 {len(games)} 場比賽（GameSno {GAME_SNO_START}~{GAME_SNO_END}）")

    pbp_rows, sb_rows, bat_rows = fetch_games(games)

    os.makedirs(DATA_DIR, exist_ok=True)
    tag = f"{YEAR}_{KIND_CODE}_{GAME_SNO_START}-{GAME_SNO_END}"
    save_to_csv(pbp_rows, os.path.join(DATA_DIR, f"cpbl_playbyplay_{tag}.csv"))
    save_to_csv(sb_rows, os.path.join(DATA_DIR, f"cpbl_scoreboard_{tag}.csv"))
    save_to_csv(bat_rows, os.path.join(DATA_DIR, f"cpbl_batting_{tag}.csv"))
