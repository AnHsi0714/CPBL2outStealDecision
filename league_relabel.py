"""把 CPBL 版報告產生器輸出的 HTML 換成其他聯盟的標籤。

CPBL 版報告的模板只有少數幾處寫死聯盟名稱與資料來源，MLB／KBO 重用同一套模板，產生後
用這支腳本做字串替換，不複製模板。用法：python league_relabel.py <html 檔> <mlb|kbo> [年份]
決策報告模板另外把年份寫死成 2025（標題、眉標、概況標題），傳年份時一併換成該年。
"""

from __future__ import annotations

import sys
from pathlib import Path

LABELS = {
    "mlb": [
        ("CPBL 官網逐球紀錄", "MLB Stats API（Gumbo）逐打席紀錄"),
        ("CPBL 官方統計", "MLB 官方 boxscore 統計"),
        ("GameSno ", "日期 "),
        ("中職", "美國職棒大聯盟"),
        ("CPBL", "MLB"),
        ("cpbl-wpa-decision", "mlb-wpa-decision"),
    ],
    "kbo": [
        ("CPBL 官網逐球紀錄", "KBO 官網文字轉播"),
        ("CPBL 官方統計", "KBO 官方統計"),
        ("GameSno ", "日期 "),
        ("中職", "韓職"),
        ("CPBL", "KBO"),
        ("cpbl-wpa-decision", "kbo-wpa-decision"),
    ],
}


def relabel(document: str, league: str, year: str | None = None) -> str:
    if year:
        for old, new in (
            ("<title>2025 CPBL", f"<title>{year} CPBL"),
            ("CPBL · 2025 REGULAR SEASON", f"CPBL · {year} REGULAR SEASON"),
            ('>2025 資料概況<', f'>{year} 資料概況<'),
        ):
            document = document.replace(old, new)
    for old, new in LABELS[league]:
        document = document.replace(old, new)
    return document


def main() -> int:
    path, league = Path(sys.argv[1]), sys.argv[2]
    path.write_text(relabel(path.read_text(encoding="utf-8"), league), encoding="utf-8", newline="\n")
    print(f"relabeled {path} -> {league}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
