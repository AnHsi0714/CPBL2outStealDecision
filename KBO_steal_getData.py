import os
import re
import csv
import time
import random
from datetime import date, timedelta
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

# 官網本身的賽程 AJAX（/ws/Schedule.asmx/GetScheduleList）試過會回 401，目前沒找到正確呼叫方式。
NAVER_SCHEDULE_URL = "https://api-gw.sports.naver.com/schedule/games"
KBO_LIVETEXT_URL = "https://www.koreabaseball.com/Game/LiveTextView2.aspx"
DATA_DIR = "kbo_data"

# 球隊簡稱 -> 中文隊名（10支一軍球隊）
TEAM_NAME_ZH = {
    "KIA": "起亞", "한화": "韓華", "KT": "KT", "LG": "LG",
    "두산": "斗山", "NC": "NC", "SSG": "SSG", "삼성": "三星",
    "키움": "키움英雄", "롯데": "樂天",
}

# 守備位置、打法、出局/上壘類型、上壘原因
_TERM_DICT = [
    # 守備位置
    ("투수", "投手"), ("포수", "捕手"), ("1루수", "一壘手"), ("2루수", "二壘手"),
    ("3루수", "三壘手"), ("유격수", "游擊手"), ("좌익수", "左外野手"),
    ("중견수", "中外野手"), ("우익수", "右外野手"),
    # 方向/深淺
    ("우중간 뒤", "右中外野後方"), ("좌중간 뒤", "左中外野後方"),
    ("우중간", "右中外野"), ("좌중간", "左中外野"),
    ("오른쪽 앞", "右前方"), ("왼쪽 앞", "左前方"),
    ("오른쪽", "右側"), ("왼쪽", "左側"), ("앞", "前方"), ("뒤", "後方"),
    # 出局類型（複合詞要排在單一「아웃」前面）
    ("병살타 아웃", "雙殺打出局"), ("병살", "雙殺"), ("희생번트 아웃", "犧牲觸擊出局"),
    ("희생플라이 아웃", "犧牲高飛球出局"), ("파울플라이 아웃", "界外高飛球出局"),
    ("라인드라이브 아웃", "平飛球出局"), ("삼진 아웃", "三振出局"),
    ("플라이 아웃", "高飛球出局"), ("땅볼 아웃", "滾地球出局"), ("플라이", "高飛球"),
    ("포스아웃", "封殺出局"), ("태그아웃", "觸殺出局"), ("터치아웃", "觸殺出局"),
    ("도루실패아웃", "盜壘失敗出局"), ("견제사아웃", "牽制出局"),
    ("스트라이크 낫 아웃", "三振但捕手未觸殺"),
    ("아웃", "出局"),
    # 打者上壘結果
    ("번트안타", "觸擊安打"), ("내야안타", "內野安打"),
    ("1루타", "一壘安打"), ("2루타", "二壘安打"),
    ("3루타", "三壘安打"), ("홈런거리", "全壘打距離"), ("홈런", "全壘打"),
    ("몸에 맞는 볼", "觸身球"), ("자동 고의4구", "自動故意四壞球"), ("고의4구", "故意四壞球"),
    ("볼넷", "保送"),
    ("실책으로 출루", "因失誤上壘"), ("야수선택으로 출루", "因野手選擇上壘"),
    ("땅볼로 출루", "滾地球上壘"), ("안타", "安打"), ("땅볼", "滾地球"),
    # 跑者移動原因與結果
    ("도루로", "盜壘"), ("폭투로", "因暴投"), ("포일로", "因捕逸"),
    ("실책으로", "因失誤"), ("주자의 재치로", "因跑者機警"),
    ("다른주자수비하는 사이", "趁防守其他跑者之際"),
    ("이중도루 실패시 홈인", "雙盜壘失敗之際回本壘得分"),
    ("까지 진루", "壘"), ("홈인", "回本壘得分"), ("득점", "得分"),
    ("대주자", "代跑員"), ("(으)로 교체", "上場替補"), ("로 교체", "上場替補"),
    ("주자", "跑者"),
    # 守備動作細節（多半出現在括號內的補充說明）
    ("송구", "傳球"), ("포구", "接球"), ("실책", "失誤"), ("견제", "牽制"),
    ("맞고", "擊中後"), ("좌전", "左前"),
    # 純壘包名稱（放最後，優先權最低，避免吃掉上面「1루타/1루까지 진루」等更完整的詞）
    ("1루", "一壘"), ("2루", "二壘"), ("3루", "三壘"), ("홈", "本壘"),
]


def translate_terms(text: str, known_names: tuple[str, ...] = ()) -> tuple[str, bool]:
    """用固定詞彙字典做逐句翻譯，回傳 (翻譯後文字, 是否完全翻完)。
    球員/跑者姓名是專有名詞，刻意不翻譯、維持原文，所以判斷「有沒有翻完」之前，
    要先把已知的姓名（known_names）從文字裡拿掉，剩下還有殘留韓文字元，才代表
    字典沒收錄到的用語，保留原文那一段，不去亂猜語意（對照 Parsed 欄位的做法）。"""
    result = text
    for kr, zh in _TERM_DICT:
        result = result.replace(kr, zh)

    check_text = result
    for name in known_names:
        if name:
            check_text = check_text.replace(name, "")
    fully_translated = re.search(r'[가-힣]', check_text) is None
    return result, fully_translated


def polite_sleep(base: float = 1.5, jitter: float = 1.5):
    """隨機延遲，降低被判定為爬蟲而封鎖的機率"""
    time.sleep(base + random.uniform(0, jitter))


def get_schedule(start_date: str, end_date: str) -> list[dict]:
    """抓日期區間內的一軍例行賽場次（gameId、對戰組合）。gameId 是從 Naver 賽程資料反推出官網格式：
    Naver 格式 20260820HTHH02026 = 日期 + 客隊代碼 + 主隊代碼 + 場次序號 + 賽季年份，
    去掉最後 4 碼年份就是官網 LiveTextView2.aspx 要用的 gameId（20260820HTHH0）。

    這個端點實測過：不管 fromDate/toDate 給多寬，一次最多只回傳約 10 場比賽（不是真的
    照日期區間篩選，超過上限的日期會直接被截掉），所以改成逐日呼叫，一天一天累加。"""
    games = []
    day = date.fromisoformat(start_date)
    last_day = date.fromisoformat(end_date)
    while day <= last_day:
        day_str = day.isoformat()
        resp = session.get(NAVER_SCHEDULE_URL, params={
            "upperCategoryId": "kbaseball", "fromDate": day_str, "toDate": day_str,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for g in data.get("result", {}).get("games", []):
            if g.get("categoryId") != "kbo":  # 排除퓨처스리그/2군等非一軍場次
                continue
            games.append({
                "GameId": g["gameId"][:-4],
                "GameDate": g["gameDate"],
                "AwayTeam": g["awayTeamName"],
                "HomeTeam": g["homeTeamName"],
            })

        day += timedelta(days=1)
        polite_sleep(0.5, 0.5)  # 賽程查詢也是對同一個端點連續呼叫

    return games


def get_full_text(game_id: str, year: str) -> str:
    """抓單場比賽的完整文字轉播 HTML（官網 LiveTextView2.aspx，一次回傳全場所有局數）"""
    resp = session.post(KBO_LIVETEXT_URL, data={
        "leagueId": "1", "seriesId": "0", "gameId": game_id, "gyear": year,
    }, timeout=15)
    resp.raise_for_status()
    return resp.text


# 依序比對：先比對更具體的格式，比對不到才「未知」，方便之後檢查有沒有漏掉的用語
_INNING_HEADER_RE = re.compile(r'^(\d+)회(초|말)\s*(\S+)\s*공격')
_BATTER_INTRO_RE = re.compile(r'^(\d+)번타자\s*(\S+)$')
_PITCH_DETAIL_RE = re.compile(r'^-\s*\d+구')
_RUNNER_MOVE_RE = re.compile(r'^([123])루주자\s+(\S+)\s*:\s*(.+)$')
_BATTER_OUTCOME_RE = re.compile(r'^(\S+)\s*:\s*(.+)$')
_HIT_BASE_RE = re.compile(r'([1-3])루타')
_ADVANCE_BASE_RE = re.compile(r'([1-3])루까지\s*진루')


def _extract_spans(html: str) -> list[str]:
    """把某一局的 numCont 區塊拆成 (class, 純文字) 列表，並轉成時間正序
    （官網原始排列是最新事件在最上面，同一局內是倒序，所以要反轉）"""
    blocks = re.findall(r'id="numCont(\d+)" class="numCon">(.*?)</div>\s*(?=<div id="numCont|\Z)', html, re.S)
    blocks.sort(key=lambda b: int(b[0]))  # numCont1(第1局) ... numContN，局數本身正序排列

    spans = []
    for _, block_html in blocks:
        block_spans = re.findall(r'<span id="[^"]+" class="([^"]+)">\s*(.*?)\s*</span>', block_html, re.S)
        block_spans = [(cls, re.sub(r'\s+', ' ', re.sub(r'<br\s*/?>', ' ', txt)).strip()) for cls, txt in block_spans]
        block_spans.reverse()  # 同一局內：官網是新事件在前，反轉成時間正序
        spans.extend(block_spans)
    return spans


def parse_game(game_meta: dict, html: str) -> list[dict]:
    """把整場比賽的文字轉播解析成事件表，每列是「這個事件發生前」的出局數/壘包狀態。
    KBO 官網文字轉播沒有結構化的出局數/壘包欄位（不像 CPBL/MLB 那樣直接給數字/布林值），
    是純敘述句，所以出局數跟壘包狀態是照下面已確認過的用語規則，逐句重建出來的狀態機。
    """
    game_id = {
        "GameId": game_meta["GameId"],
        "GameDate": game_meta["GameDate"],
        "AwayTeam": game_meta["AwayTeam"],
        "HomeTeam": game_meta["HomeTeam"],
        "AwayTeam_zh": TEAM_NAME_ZH.get(game_meta["AwayTeam"], game_meta["AwayTeam"]),
        "HomeTeam_zh": TEAM_NAME_ZH.get(game_meta["HomeTeam"], game_meta["HomeTeam"]),
    }

    inning, half, batting_team, batter_name = None, None, None, None
    outs = 0
    # 壘包狀態用「目前佔用者的姓名」追蹤，沒辦法分辨「原本那個跑者離開」跟「新打者剛上壘」，會把新打者也一起清掉
    # eg. 2026-08-20 두산@NC 第2局，博건우 1루打→이우성 觸身球擠到一壘→박건우 被動→2壘，就是這樣算錯
    base = {1: None, 2: None, 3: None}
    rows = []

    for cls, text in _extract_spans(html):
        if not text:
            continue

        if cls == "blue":
            m = _INNING_HEADER_RE.match(text)
            if m:
                inning, half_kr, batting_team = int(m.group(1)), m.group(2), m.group(3)
                half = "top" if half_kr == "초" else "bottom"
                outs = 0
                base = {1: None, 2: None, 3: None}
            continue

        # class="red" 不是場邊資訊的專用標記，得分相關的安打/跑者移動事件也會用紅字強調
        if text == "=====================================" or text == "경기종료" or \
           re.match(r'^(승리|패전)(팀\s*홀드)?투수\s*:', text) or re.match(r'^세이브투수\s*:', text):
            continue

        if _BATTER_INTRO_RE.match(text):
            batter_name = _BATTER_INTRO_RE.match(text).group(2)
            continue

        if _PITCH_DETAIL_RE.match(text):
            continue

        if "비디오 판독" in text:  # 判決覆審註記，不是新事件
            continue

        m = _RUNNER_MOVE_RE.match(text)
        if m:
            from_base, runner_name, result = int(m.group(1)), m.group(2), m.group(3)
            pinch = re.search(r'대주자\s*(\S+)\s*(?:\(으\))?로\s*교체', result)
            text_zh, text_zh_full = translate_terms(
                text, known_names=(runner_name, pinch.group(1) if pinch else None))
            row = {
                **game_id, "Inning": inning, "HalfInning": half,
                "BattingTeam": batting_team, "BattingTeam_zh": TEAM_NAME_ZH.get(batting_team, batting_team),
                "BatterName": batter_name, "Outs": outs,
                "On1B": base[1] is not None, "On2B": base[2] is not None, "On3B": base[3] is not None,
                "EventType": "runner_movement", "RawText": text,
                "RawText_zh": text_zh, "RawText_zh_Complete": text_zh_full,
                "HasStealMention": "도루" in text,
            }

            is_current_occupant = base[from_base] == runner_name

            if "대주자" in result:  # 代跑上場，人還在同一個壘包，只是姓名換成代跑選手
                if pinch and is_current_occupant:
                    base[from_base] = pinch.group(1)
                row["Parsed"] = True
            elif "아웃" in result:
                outs += 1
                if is_current_occupant:
                    base[from_base] = None
                row["Parsed"] = True
            elif "홈인" in result or "득점" in result:
                if is_current_occupant:
                    base[from_base] = None
                row["Parsed"] = True
            else:
                adv = _ADVANCE_BASE_RE.search(result)
                if adv:
                    dest = int(adv.group(1))
                    if is_current_occupant:
                        base[from_base] = None
                    base[dest] = runner_name
                    row["Parsed"] = True
                else:
                    row["Parsed"] = False  # 沒對到任何已知用語，人工檢查

            rows.append(row)
            continue

        m = _BATTER_OUTCOME_RE.match(text)
        if m:
            name, result = m.group(1), m.group(2)
            text_zh, text_zh_full = translate_terms(text, known_names=(name,))
            row = {
                **game_id, "Inning": inning, "HalfInning": half,
                "BattingTeam": batting_team, "BattingTeam_zh": TEAM_NAME_ZH.get(batting_team, batting_team),
                "BatterName": batter_name, "Outs": outs,
                "On1B": base[1] is not None, "On2B": base[2] is not None, "On3B": base[3] is not None,
                "EventType": "batter_outcome", "RawText": text,
                "RawText_zh": text_zh, "RawText_zh_Complete": text_zh_full,
                "HasStealMention": "도루" in text,
            }

            if "아웃" in result:
                outs += 1
                row["Parsed"] = True
            elif "홈런" in result:
                row["Parsed"] = True  # 打者直接得分，不佔壘包，其他跑者各自有自己的得分事件列
            else:
                hit = _HIT_BASE_RE.search(result)
                if hit:
                    dest = int(hit.group(1))
                elif "안타" in result:  # 「안타」視為一安打
                    dest = 1
                elif "볼넷" in result or "몸에 맞는 볼" in result or "고의4구" in result:
                    dest = 1
                elif "출루" in result:  # 失策/野手選擇上壘
                    dest = 1
                else:
                    dest = None

                if dest is not None:
                    base[dest] = name

                row["Parsed"] = dest is not None

            rows.append(row)

    return rows


def fetch_games(games: list[dict]) -> list[dict]:
    """依序抓取一批比賽，每場之間隨機延遲"""
    all_rows = []

    for i, g in enumerate(games, 1):
        print(f"[{i}/{len(games)}] 抓取 {g['GameDate']} GameId={g['GameId']} "
              f"{g['AwayTeam']} @ {g['HomeTeam']}")

        try:
            year = g["GameDate"][:4]
            html = get_full_text(g["GameId"], year)
        except Exception as e:
            print(f"  失敗，略過本場：{e}")
            polite_sleep()
            continue

        rows = parse_game(g, html)
        unparsed = sum(1 for r in rows if not r["Parsed"])
        if unparsed:
            print(f"  注意：{unparsed}/{len(rows)} 筆事件文字沒對到已知用語規則，Parsed=False，需人工檢查")
        all_rows.extend(rows)
        polite_sleep()

    return all_rows


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

    rows = fetch_games(games)

    os.makedirs(DATA_DIR, exist_ok=True)
    tag = f"{START_DATE}_{END_DATE}"
    save_to_csv(rows, os.path.join(DATA_DIR, f"kbo_playbyplay_{tag}.csv"))
