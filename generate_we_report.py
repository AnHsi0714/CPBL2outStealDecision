"""把 build_win_expectancy_matrix.py 產生的勝率矩陣畫成互動熱力圖報告。

跟 `generate_re24_report.py` 的差異：RE24 只有 24 格，可以在 Python 端把整
張網格算好直接輸出成固定 HTML；WE 矩陣多了局數／攻守方／出局數三個篩選
維度（2640 格），改成把完整 cells 陣列內嵌成 JSON payload，交給
`templates/we_report.js` 在瀏覽器端依篩選條件即時渲染（沿用
`generate_decision_report.py` 的 payload-in-page 模式）。色階仍是 dataviz
skill 的單一藍色相序列色，因為勝率固定落在 0–1，色階可以直接複用
`generate_re24_report.py` 已經算好、跟資料無關的 13 級 CSS 規則。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from generate_re24_report import SEQUENTIAL_STEPS_DARK, SEQUENTIAL_STEPS_LIGHT, build_cell_styles


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "we_report.html"
STYLE_PATH = ROOT / "templates" / "we_report.css"
SCRIPT_PATH = ROOT / "templates" / "we_report.js"

DEFAULT_MATRIX_SUMMARY = ROOT / "outputs" / "cpbl_win_expectancy_matrix_2023-2026_A_combined_summary.json"
DEFAULT_VALIDATION_SUMMARY = ROOT / "outputs" / "cpbl_win_expectancy_validation_2023-2026_A_combined_summary.json"
DEFAULT_OUTPUT = ROOT / "reports" / "cpbl-win-expectancy-matrix.html"


def build_report(matrix_summary: dict[str, Any], validation_summary: dict[str, Any] | None) -> str:
    light_rules, dark_rules = build_cell_styles()

    seasons = matrix_summary.get("seasons", [])
    season_list = "、".join(f"{s['year']}({s['start']}-{s['end']})" for s in seasons)
    season_range = "/".join(str(s["year"]) for s in seasons)

    payload = {
        "cells": matrix_summary["cells"],
        "inningBuckets": matrix_summary.get("inning_buckets", ["1-6", "7", "8", "9+"]),
        "scoreDiffCap": matrix_summary.get("score_diff_cap", 5),
        "battingSideLabels": {"1": "客隊進攻", "2": "主隊進攻"},
        "validation": validation_summary,
    }

    style = STYLE_PATH.read_text(encoding="utf-8")
    style = style.replace("/*__LIGHT_LEVEL_RULES__*/", "\n    ".join(light_rules))
    style = style.replace("/*__DARK_LEVEL_RULES__*/", "\n      ".join(dark_rules))
    style = style.replace("__LEGEND_STOPS__", " ,".join(SEQUENTIAL_STEPS_LIGHT))
    style = style.replace("__LEGEND_STOPS_DARK__", " ,".join(SEQUENTIAL_STEPS_DARK))

    document = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = document.replace("/*__STYLES__*/", style.rstrip("\n"))
    document = document.replace("/*__SCRIPT__*/", SCRIPT_PATH.read_text(encoding="utf-8").rstrip("\n"))
    document = document.replace("__REPORT_DATA__", json.dumps(payload, ensure_ascii=False))
    document = document.replace("__SEASON_RANGE__", season_range or "?")
    document = document.replace("__SEASON_LIST__", season_list or "?")
    document = document.replace("__GAMES_PROCESSED__", f"{matrix_summary.get('games_processed', 0):,}")
    document = document.replace("__TOTAL_SEGMENTS__", f"{matrix_summary.get('total_state_segments', 0):,}")
    document = document.replace("__SCORE_DIFF_CAP__", str(matrix_summary.get("score_diff_cap", 5)))
    document = document.replace(
        "__MIN_N_COVERAGE__",
        str(validation_summary.get("min_n_for_coverage", 20)) if validation_summary else "20",
    )
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-summary-json", type=Path, default=DEFAULT_MATRIX_SUMMARY)
    parser.add_argument("--validation-summary-json", type=Path, default=DEFAULT_VALIDATION_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.matrix_summary_json.exists():
        raise SystemExit(
            f"找不到 WE 矩陣摘要：{args.matrix_summary_json}，請先執行 build_win_expectancy_matrix.py"
        )
    with args.matrix_summary_json.open("r", encoding="utf-8-sig") as handle:
        matrix_summary = json.load(handle)

    validation_summary = None
    if args.validation_summary_json.exists():
        with args.validation_summary_json.open("r", encoding="utf-8-sig") as handle:
            validation_summary = json.load(handle)
    else:
        print(f"提醒：找不到 {args.validation_summary_json}，報告將略過品質檢查區塊（先跑 validate_win_expectancy_matrix.py 可補上）")

    document = build_report(matrix_summary, validation_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({matrix_summary.get('total_state_segments', 0):,} state 區段)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
