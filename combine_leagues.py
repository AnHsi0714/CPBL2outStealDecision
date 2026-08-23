"""把 CPBL/MLB/KBO 三份 playbyplay CSV 統一欄位命名後合併成一份跨聯盟資料集。

三邊原始欄位命名不一致（例如 CPBL 用 OutCnt、MLB/KBO 用 Outs；CPBL 用 VisitingHomeType
數字代碼表示攻守方，MLB/KBO 直接給 TeamBatting/BattingTeam），這裡統一成：
League/GameId/GameDate/AwayTeam/HomeTeam/Inning/HalfInning/BattingTeam/BatterName/
Outs/On1B/On2B/On3B/ResultText/HasStealMention
"""
import csv
import glob
import os

DATA_DIR = "combined_data"


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def newest(pattern: str) -> str:
    """同資料夾下可能有舊的（範圍較小的）跟新的檔案，取檔案大小最大的那份，
    因為抓取範圍越大，檔案自然越大，不用額外去解析檔名裡的日期區間比大小。"""
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(f"找不到符合 {pattern} 的檔案")
    return max(matches, key=os.path.getsize)


def combine_cpbl(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        is_away_batting = r["VisitingHomeType"] == "1"  # 官網實測：1=客隊打擊, 2=主隊打擊
        out.append({
            "League": "CPBL",
            "GameId": f"{r['Year']}_{r['KindCode']}_{r['GameSno']}",
            "GameDate": r["GameDate"],
            "AwayTeam": r["VisitingTeam"],
            "HomeTeam": r["HomeTeam"],
            "Inning": r["InningSeq"],
            "HalfInning": "top" if is_away_batting else "bottom",
            "BattingTeam": r["VisitingTeam"] if is_away_batting else r["HomeTeam"],
            "BatterName": r["HitterName"],
            "Outs": r["OutCnt"],
            "On1B": r["On1B"], "On2B": r["On2B"], "On3B": r["On3B"],
            "ResultText": r["Content"],
            "HasStealMention": r["HasStealMention"],
        })
    return out


def combine_mlb(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "League": "MLB",
            "GameId": r["GamePk"],
            "GameDate": r["GameDate"],
            "AwayTeam": r["AwayTeam"],
            "HomeTeam": r["HomeTeam"],
            "Inning": r["Inning"],
            "HalfInning": r["HalfInning"],
            "BattingTeam": r["TeamBatting"],
            "BatterName": r["BatterName"],
            "Outs": r["Outs"],
            "On1B": r["On1B"], "On2B": r["On2B"], "On3B": r["On3B"],
            "ResultText": r["Description"],
            "HasStealMention": r["HasStealMention"],
        })
    return out


def combine_kbo(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "League": "KBO",
            "GameId": r["GameId"],
            "GameDate": r["GameDate"],
            "AwayTeam": r["AwayTeam"],
            "HomeTeam": r["HomeTeam"],
            "Inning": r["Inning"],
            "HalfInning": r["HalfInning"],
            "BattingTeam": r["BattingTeam"],
            "BatterName": r["BatterName"],
            "Outs": r["Outs"],
            "On1B": r["On1B"], "On2B": r["On2B"], "On3B": r["On3B"],
            "ResultText": r["RawText_zh"],
            "HasStealMention": r["HasStealMention"],
        })
    return out


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
    cpbl_path = newest("cpbl_data/cpbl_playbyplay_*.csv")
    mlb_path = newest("mlb_data/mlb_playbyplay_*.csv")
    kbo_path = newest("kbo_data/kbo_playbyplay_*.csv")
    print(f"讀取 CPBL：{cpbl_path}")
    print(f"讀取 MLB：{mlb_path}")
    print(f"讀取 KBO：{kbo_path}")

    combined = (
        combine_cpbl(load(cpbl_path))
        + combine_mlb(load(mlb_path))
        + combine_kbo(load(kbo_path))
    )

    os.makedirs(DATA_DIR, exist_ok=True)
    save_to_csv(combined, os.path.join(DATA_DIR, "combined_playbyplay.csv"))

    target = [
        r for r in combined
        if r["Outs"] == "2" and r["On1B"] == "True" and r["On2B"] == "False" and r["On3B"] == "False"
    ]
    steal = [r for r in target if r["HasStealMention"] == "True"]
    print(f"\n跨聯盟「2出局、僅一壘有人」情境：{len(target)} 筆，其中有盜壘標記：{len(steal)} 筆")
    for league in ("CPBL", "MLB", "KBO"):
        n_target = sum(1 for r in target if r["League"] == league)
        n_steal = sum(1 for r in steal if r["League"] == league)
        print(f"  {league}: {n_target} 筆情境, {n_steal} 筆盜壘")
