"""把 reports/ 底下既有的互動報告整合成一個入口頁面。

不重新運算或重新內嵌任何報告內容：決策報告單一年度就有 1MB 以上的內嵌資料與 JS，
硬塞進同一個檔案只會複製已經各自測試過的邏輯、徒增風險。這裡改用 iframe 包住既有的
靜態 HTML 檔案，外層只負責分類（決策報告／RE24／WE／WPA）與年份的導覽切換。

執行前必須已經跑過至少一份 generate_decision_report.py / generate_re24_report.py /
generate_we_report.py / generate_wpa_report.py，本腳本只掃描 reports/ 目錄找出既有檔案，
找不到的分類會直接略過（不會報錯中斷）。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
TEMPLATE_PATH = ROOT / "templates" / "full_report.html"
STYLE_PATH = ROOT / "templates" / "full_report.css"
SCRIPT_PATH = ROOT / "templates" / "full_report.js"
OUTPUT_NAME = "cpbl-full-report.html"
OUTPUT_CSS_NAME = "cpbl-full-report.css"
OUTPUT_JS_NAME = "cpbl-full-report.js"

# 掃描 reports/ 目錄時比對的檔名規則；有 capture group 的視為「逐年份」分類。
CATEGORY_SPECS = [
    {
        "id": "decision",
        "label": "盜壘決策報告",
        "description": "三分支模擬（成功／失敗／不跑）、棒次 × 打者類型分組、六隊決策品質、符合門檻的跑者名單。",
        "pattern": re.compile(r"^cpbl-steal-decision-(\d{4})\.html$"),
    },
    {
        "id": "re24",
        "label": "RE24 矩陣",
        "description": "24 格 base-out 期望得分熱力圖，以及未計保留效應的基礎損益兩平門檻。",
        "pattern": re.compile(r"^cpbl-re24-matrix-(\d{4})\.html$"),
    },
    {
        "id": "we",
        "label": "勝率增值矩陣（WE）",
        "description": "局數 × 攻守方 × 分差 × 出局 × 壘包，合併四季推回的進攻方最終獲勝機率。",
        "pattern": re.compile(r"^cpbl-win-expectancy-matrix\.html$"),
    },
    {
        "id": "wpa",
        "label": "WPA 版損益兩平門檻",
        "description": "第 2–8 局改以勝率增值取代得分期望值當判準，含四季逐局 bootstrap 信賴區間比較。",
        "pattern": re.compile(r"^cpbl-wpa-decision-thresholds\.html$"),
    },
]

# 逐年份分類的預設顯示年份；不在清單內時退回最新一年。
PREFERRED_YEAR = "2025"


def discover_categories(reports_dir: Path) -> list[dict[str, Any]]:
    available = sorted(p.name for p in reports_dir.glob("*.html") if p.name != OUTPUT_NAME)

    categories: list[dict[str, Any]] = []
    for spec in CATEGORY_SPECS:
        variants = []
        for name in available:
            match = spec["pattern"].match(name)
            if not match:
                continue
            year = match.group(1) if match.groups() else None
            variants.append({"year": year, "file": name})
        if not variants:
            continue
        variants.sort(key=lambda v: v["year"] or "")
        years = [v["year"] for v in variants]
        default_index = years.index(PREFERRED_YEAR) if PREFERRED_YEAR in years else len(variants) - 1
        categories.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "description": spec["description"],
                "variants": variants,
                "defaultIndex": default_index,
            }
        )
    return categories


def esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_nav_html(categories: list[dict[str, Any]]) -> str:
    buttons = [
        f'<button type="button" class="tab" data-cat="{esc(cat["id"])}" '
        f'aria-selected="{"true" if i == 0 else "false"}">{esc(cat["label"])}</button>'
        for i, cat in enumerate(categories)
    ]
    return "".join(buttons)


def build_report(categories: list[dict[str, Any]]) -> str:
    document = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = document.replace("__NAV_BUTTONS__", build_nav_html(categories))
    document = document.replace("__CATEGORIES_JSON__", json.dumps(categories, ensure_ascii=False))
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports_dir = args.reports_dir
    output = args.output or reports_dir / OUTPUT_NAME

    categories = discover_categories(reports_dir)
    if not categories:
        print(f"{reports_dir} 底下找不到任何已知格式的報告，請先跑過對應的 generate_*.py")
        return 1

    document = build_report(categories)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    (output.parent / OUTPUT_CSS_NAME).write_text(STYLE_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    (output.parent / OUTPUT_JS_NAME).write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    total_variants = sum(len(c["variants"]) for c in categories)
    missing = [spec["label"] for spec in CATEGORY_SPECS if spec["id"] not in {c["id"] for c in categories}]
    print(f"Wrote {output}（{len(categories)} 類、共 {total_variants} 份既有報告）")
    if missing:
        print(f"略過（找不到對應檔案）：{'、'.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
