"""把 WPA 版損益兩平門檻（`model_wpa_decisions.py` + `bootstrap_wpa_threshold_ci.py`
的輸出）畫成逐局、逐季的信賴區間比較圖。

沿用 dataviz skill 的表單選型：這是「兩個系列（RE 點估計、WPA 區間）逐類別
比較」，用 categorical 色（validated 預設調色盤 slot 1 藍＝WPA、slot 2 橘＝RE），
形狀也不同（WPA＝圓點+區間線、RE＝菱形）當第二層區分，不只靠顏色。四季各自
一張小圖（small multiples）並排，因為故事重點是「方向在四季之間一不一致」。

純 HTML/CSS/inline SVG，不依賴圖表套件，跟專案其他報告一致；SVG 在 Python
端整個算好直接輸出（資料量小、不需要前端互動運算），tooltip 沿用專案既有的
`data-tooltip` + CSS `::after` 技巧。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "wpa_report.html"
STYLE_PATH = ROOT / "templates" / "wpa_report.css"

SEASONS = [
    (2023, "A", 1, 300),
    (2024, "A", 1, 360),
    (2025, "A", 1, 360),
    (2026, "A", 1, 240),
]

MAX_PCT = 90.0
PLOT_LEFT = 112
PLOT_RIGHT = 440
ROW_HEIGHT = 34
TOP_OFFSET = 14
AXIS_HEIGHT = 26


def x_pos(pct: float) -> float:
    ratio = max(0.0, min(1.0, pct / MAX_PCT))
    return PLOT_LEFT + ratio * (PLOT_RIGHT - PLOT_LEFT)


def esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def load_we_summary() -> dict[str, Any]:
    path = ROOT / "outputs" / "cpbl_win_expectancy_matrix_2023-2026_A_combined_summary.json"
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def build_leverage_rows(we_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """攻方在「2 出局、空壘」時領先/落後 1 分的勝率，隨局數如何變化。

    這是 WPA 門檻隨局數下降的機制根源：同一分的份量隨局數推進變重，代表
    「讓這個半局現在結束」（不管是盜壘刺還是打者自己正常出局）在晚局的
    代價本來就逼近打者正常出局的代價，跟盜壘失敗的代價差距縮小。
    """
    cells = {
        (c["inningBucket"], c["battingSide"], c["scoreDiffBucket"], c["outs"], c["baseCode"]): c
        for c in we_summary["cells"]
    }
    rows = []
    for bucket, label in (("1-6", "第 1–6 局"), ("7", "第 7 局"), ("8", "第 8 局")):
        ahead = cells[(bucket, "1", 1, 2, 0)]
        behind = cells[(bucket, "1", -1, 2, 0)]
        rows.append(
            {
                "label": label,
                "ahead_pct": ahead["winRate"] * 100,
                "ahead_n": ahead["n"],
                "behind_pct": behind["winRate"] * 100,
                "behind_n": behind["n"],
            }
        )
    return rows


def build_leverage_cards(rows: list[dict[str, Any]]) -> str:
    cards = []
    for row in rows:
        cards.append(
            '<article class="stat">'
            f"<small>{esc(row['label'])}．領先 1 分時的勝率</small>"
            f"<strong>{row['ahead_pct']:.1f}%</strong>"
            f"<span>n={row['ahead_n']:,}</span>"
            "</article>"
        )
    for row in rows:
        cards.append(
            '<article class="stat">'
            f"<small>{esc(row['label'])}．落後 1 分時的勝率</small>"
            f"<strong>{row['behind_pct']:.1f}%</strong>"
            f"<span>n={row['behind_n']:,}</span>"
            "</article>"
        )
    return "".join(cards)


def inning_range_text(seasons: list[dict[str, Any]], inning: int, key: str) -> str:
    values = [
        season["rows"][inning - 1][key] * 100
        for season in seasons
        if season["rows"][inning - 1][key] is not None
    ]
    if not values:
        return "—"
    if max(values) - min(values) < 0.5:
        return f"{values[0]:.0f}%"
    return f"{min(values):.0f}–{max(values):.0f}%"


def load_reclassification(year: int, kind_code: str, start: int, end: int) -> dict[str, Any] | None:
    tag = f"{year}_{kind_code}_{start}-{end}"
    summary_path = ROOT / "outputs" / f"cpbl_wpa_runner_reclassification_{tag}_summary.json"
    csv_path = ROOT / "outputs" / f"cpbl_wpa_runner_reclassification_{tag}.csv"
    if not summary_path.exists():
        return None
    with summary_path.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)
    runners: list[dict[str, Any]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            runners = list(csv.DictReader(handle))
    return {"year": year, "summary": summary, "runners": runners}


def build_reclassification_summary_rows(entries: list[dict[str, Any]]) -> str:
    rows_html = []
    for entry in entries:
        summary = entry["summary"]
        never_go = summary["re_never_go_runner_count"]
        reclassified = summary["reclassified_by_wpa_count"]
        pct = f"{reclassified / never_go * 100:.0f}%" if never_go else "—"
        rows_html.append(
            f"<tr><td>{entry['year']}</td><td>{never_go}</td><td>{reclassified}</td><td>{pct}</td></tr>"
        )
    return "".join(rows_html)


def build_reclassification_runner_rows(entries: list[dict[str, Any]]) -> str:
    rows_html = []
    for entry in entries:
        for runner in entry["runners"]:
            success_rate = float(runner["SuccessRate"]) * 100
            qualifying = runner["WPA_QualifyingInnings"]
            qualifying_text = (
                "、".join(f"{i}局" for i in qualifying.split(",")) if qualifying else "無（各局皆不夠格）"
            )
            rows_html.append(
                "<tr>"
                f"<td>{entry['year']}</td>"
                f"<td>{esc(runner['HitterName'])}</td>"
                f"<td>{esc(runner['Team'])}</td>"
                f"<td>{success_rate:.1f}%</td>"
                f"<td>{runner['Attempts']}</td>"
                f"<td>{esc(qualifying_text)}</td>"
                "</tr>"
            )
    return "".join(rows_html)


GROUP_AXES = [
    ("power_high_vs_low_ISO", "長打力（ISO）", "high_ISO", "low_ISO"),
    ("patience_high_vs_low_BB", "選球力（BB%）", "high_BB", "low_BB"),
    ("obp_high_vs_low_OBP", "真上壘率（OBP）", "high_OBP", "low_OBP"),
    ("contact_high_vs_low_1B", "單打率（接觸型）", "high_1B", "low_1B"),
    ("tto_high_vs_low_TTO", "TTO 複合指標", "high_TTO", "low_TTO"),
]


def load_group_comparison(year: int, kind_code: str, start: int, end: int) -> dict[str, Any] | None:
    tag = f"{year}_{kind_code}_{start}-{end}"
    path = ROOT / "outputs" / f"cpbl_wpa_group_comparison_{tag}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return {"year": year, "data": data}


def _direction(comparison: dict[str, Any], high_key: str, low_key: str) -> str | None:
    high_median = comparison[high_key]["median"]
    low_median = comparison[low_key]["median"]
    if high_median is None or low_median is None or high_median == low_median:
        return None
    return "higher" if high_median > low_median else "lower"


def _majority_direction(directions: list[str], total: int) -> tuple[str | None, int]:
    """回傳（多數方向, 該方向出現的季數）。多數指 >= total 的一半以上。"""
    if not directions:
        return None, 0
    counts = Counter(directions)
    direction, count = counts.most_common(1)[0]
    if count * 2 < total:
        return None, count
    return direction, count


def build_group_axis_rows(entries: list[dict[str, Any]]) -> str:
    rows_html = []
    total = len(entries)
    for axis_key, axis_label, high_key, low_key in GROUP_AXES:
        re_directions = []
        wpa_directions = []
        wpa_significant_count = 0
        for entry in entries:
            data = entry["data"]
            re_cmp = next(c for c in data["group_comparisons_re"] if c["comparison"] == axis_key)
            wpa_cmp = next(c for c in data["group_comparisons_wpa"] if c["comparison"] == axis_key)
            re_dir = _direction(re_cmp, high_key, low_key)
            wpa_dir = _direction(wpa_cmp, high_key, low_key)
            if re_dir:
                re_directions.append(re_dir)
            if wpa_dir:
                wpa_directions.append(wpa_dir)
            if wpa_cmp["p_value"] is not None and wpa_cmp["p_value"] < 0.05:
                wpa_significant_count += 1

        re_direction, re_count = _majority_direction(re_directions, total)
        wpa_direction, wpa_count = _majority_direction(wpa_directions, total)
        re_label = f"高組門檻較{'高' if re_direction == 'higher' else '低'}（{re_count}/{total} 季）" if re_direction else "不一致"
        wpa_label = f"高組門檻較{'高' if wpa_direction == 'higher' else '低'}（{wpa_count}/{total} 季）" if wpa_direction else "不一致"

        if re_direction and wpa_direction and re_direction == wpa_direction:
            verdict = "方向保留" if wpa_significant_count * 2 >= total else "方向保留，顯著性減弱"
            verdict_class = "clear"
        elif re_direction and wpa_direction and re_direction != wpa_direction:
            verdict = "方向反轉"
            verdict_class = "overlap"
        else:
            verdict = "不穩定"
            verdict_class = "overlap"

        rows_html.append(
            "<tr>"
            f"<td>{esc(axis_label)}</td>"
            f"<td>{esc(re_label)}</td>"
            f"<td>{esc(wpa_label)}，{wpa_significant_count}/{total} 季顯著</td>"
            f'<td><span class="flag {verdict_class}">{esc(verdict)}</span></td>'
            "</tr>"
        )
    return "".join(rows_html)


def build_lineup_slot_rows(entries: list[dict[str, Any]]) -> str:
    rows_html = []
    for entry in entries:
        data = entry["data"]
        re_slots = {int(k): v for k, v in data["lineup_slot_re"].items()}
        wpa_slots = {int(k): v for k, v in data["lineup_slot_wpa"].items()}
        re_min_slot = min((s for s in re_slots if re_slots[s]["median"] is not None), key=lambda s: re_slots[s]["median"])
        wpa_min_slot = min((s for s in wpa_slots if wpa_slots[s]["median"] is not None), key=lambda s: wpa_slots[s]["median"])
        rows_html.append(
            "<tr>"
            f"<td>{entry['year']}</td>"
            f"<td>第 {re_min_slot} 棒（{re_slots[re_min_slot]['median'] * 100:.1f}%）</td>"
            f"<td>第 {wpa_min_slot} 棒（{wpa_slots[wpa_min_slot]['median'] * 100:.1f}%）</td>"
            "</tr>"
        )
    return "".join(rows_html)


def load_season(year: int, kind_code: str, start: int, end: int) -> dict[str, Any] | None:
    tag = f"{year}_{kind_code}_{start}-{end}"
    summary_path = ROOT / "outputs" / f"cpbl_wpa_decision_model_{tag}_summary.json"
    bootstrap_path = ROOT / "outputs" / f"cpbl_wpa_bootstrap_ci_{tag}.json"
    if not summary_path.exists() or not bootstrap_path.exists():
        return None
    with summary_path.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)
    with bootstrap_path.open("r", encoding="utf-8-sig") as handle:
        bootstrap = json.load(handle)
    ci_by_inning = {row["inning"]: row for row in bootstrap.get("by_inning", [])}

    rows = []
    for inning in range(1, 9):
        re_median = summary["by_inning"].get(str(inning), {}).get("median_threshold_re")
        ci = ci_by_inning.get(inning) or {}
        rows.append(
            {
                "inning": inning,
                "re_median": re_median,
                "wpa_median": ci.get("point_median"),
                "ci_low": ci.get("ci_low"),
                "ci_high": ci.get("ci_high"),
                "n": ci.get("n"),
            }
        )
    return {"year": year, "tag": tag, "rows": rows}


def build_panel_svg(season: dict[str, Any]) -> str:
    rows = season["rows"]
    height = TOP_OFFSET + len(rows) * ROW_HEIGHT + AXIS_HEIGHT
    parts = [f'<svg viewBox="0 0 460 {height}" role="img" aria-label="{season["year"]} 年逐局 WPA 與 RE 門檻對照圖">']

    for pct in (0, 20, 40, 60, 80):
        x = x_pos(pct)
        parts.append(
            f'<line class="gridline" x1="{x:.1f}" y1="{TOP_OFFSET}" x2="{x:.1f}" '
            f'y2="{TOP_OFFSET + len(rows) * ROW_HEIGHT}" />'
        )
        parts.append(
            f'<text class="axis-label" x="{x:.1f}" y="{TOP_OFFSET + len(rows) * ROW_HEIGHT + 16}" '
            f'text-anchor="middle">{pct}%</text>'
        )

    for index, row in enumerate(rows):
        y = TOP_OFFSET + index * ROW_HEIGHT + ROW_HEIGHT / 2
        inning = row["inning"]
        label = f"第{inning}局" + ("&#8224;" if inning == 1 else "")
        parts.append(f'<text class="axis-label" x="6" y="{y + 4:.1f}">{label}</text>')

        if row["ci_low"] is not None and row["ci_high"] is not None:
            x_low, x_high = x_pos(row["ci_low"] * 100), x_pos(row["ci_high"] * 100)
            wpa_tooltip = (
                f"第{inning}局 WPA 門檻中位數 {row['wpa_median'] * 100:.1f}%"
                f"（95% CI {row['ci_low'] * 100:.1f}%–{row['ci_high'] * 100:.1f}%，n={row['n']}）"
            )
            parts.append(
                f'<g class="mark" tabindex="0" data-tooltip="{esc(wpa_tooltip)}">'
                f'<line x1="{x_low:.1f}" y1="{y:.1f}" x2="{x_high:.1f}" y2="{y:.1f}" '
                f'stroke="var(--series-wpa)" stroke-width="5" stroke-linecap="round" />'
                f'<circle cx="{x_pos(row["wpa_median"] * 100):.1f}" cy="{y:.1f}" r="5" '
                f'fill="var(--series-wpa)" stroke="var(--surface)" stroke-width="2" />'
                f"</g>"
            )
        else:
            parts.append(f'<text class="row-note" x="{PLOT_LEFT}" y="{y + 4:.1f}">樣本不足</text>')

        if row["re_median"] is not None:
            re_x = x_pos(row["re_median"] * 100)
            re_tooltip = f"第{inning}局 RE 門檻中位數 {row['re_median'] * 100:.1f}%"
            parts.append(
                f'<g class="mark" tabindex="0" data-tooltip="{esc(re_tooltip)}" '
                f'transform="translate({re_x:.1f},{y:.1f}) rotate(45)">'
                f'<rect x="-5" y="-5" width="10" height="10" fill="var(--series-re)" '
                f'stroke="var(--surface)" stroke-width="2" />'
                f"</g>"
            )

    parts.append("</svg>")
    return "".join(parts)


def build_table_rows(seasons: list[dict[str, Any]]) -> str:
    rows_html = []
    for season in seasons:
        for row in season["rows"]:
            re_median = row["re_median"]
            wpa_median = row["wpa_median"]
            ci_low, ci_high = row["ci_low"], row["ci_high"]

            re_cell = f"{re_median * 100:.1f}%" if re_median is not None else "—"
            wpa_cell = f"{wpa_median * 100:.1f}%" if wpa_median is not None else "—"
            if ci_low is not None and ci_high is not None:
                ci_cell = f"{ci_low * 100:.1f}%–{ci_high * 100:.1f}%"
            else:
                ci_cell = "—"

            if ci_high is not None and re_median is not None:
                overlap = ci_high >= re_median
                flag_cell = (
                    '<span class="flag overlap">重疊</span>'
                    if overlap
                    else '<span class="flag clear">未重疊</span>'
                )
            else:
                flag_cell = "—"

            row_class = ' class="unreliable"' if row["inning"] == 1 else ""
            rows_html.append(
                f"<tr{row_class}>"
                f'<td>{season["year"]}</td>'
                f'<td>第{row["inning"]}局</td>'
                f"<td>{re_cell}</td>"
                f"<td>{wpa_cell}</td>"
                f"<td>{ci_cell}</td>"
                f"<td>{flag_cell}</td>"
                f"</tr>"
            )
    return "".join(rows_html)


def build_report(
    seasons: list[dict[str, Any]],
    we_summary: dict[str, Any],
    reclassification_entries: list[dict[str, Any]],
    group_comparison_entries: list[dict[str, Any]],
) -> str:
    style = STYLE_PATH.read_text(encoding="utf-8")
    document = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = document.replace("/*__STYLES__*/", style.rstrip("\n"))

    panels_html = []
    for season in seasons:
        panels_html.append(
            f'<div class="season-panel"><h3>{season["year"]}</h3>{build_panel_svg(season)}</div>'
        )
    document = document.replace("__SEASON_PANELS__", "\n".join(panels_html))
    document = document.replace("__TABLE_ROWS__", build_table_rows(seasons))
    document = document.replace(
        "__SEASON_RANGE__", "/".join(str(s["year"]) for s in seasons)
    )

    leverage_rows = build_leverage_rows(we_summary)
    document = document.replace("__LEVERAGE_CARDS__", build_leverage_cards(leverage_rows))

    document = document.replace("__WPA_RANGE_INNING4__", inning_range_text(seasons, 4, "wpa_median"))
    document = document.replace("__RE_RANGE_INNING4__", inning_range_text(seasons, 4, "re_median"))
    document = document.replace("__WPA_RANGE_INNING6__", inning_range_text(seasons, 6, "wpa_median"))
    document = document.replace("__RE_RANGE_INNING6__", inning_range_text(seasons, 6, "re_median"))
    document = document.replace("__WPA_RANGE_INNING7__", inning_range_text(seasons, 7, "wpa_median"))
    document = document.replace("__RE_RANGE_INNING7__", inning_range_text(seasons, 7, "re_median"))
    document = document.replace("__WPA_RANGE_INNING8__", inning_range_text(seasons, 8, "wpa_median"))
    document = document.replace("__RE_RANGE_INNING8__", inning_range_text(seasons, 8, "re_median"))

    document = document.replace(
        "__RECLASSIFICATION_ROWS__", build_reclassification_summary_rows(reclassification_entries)
    )
    document = document.replace(
        "__RECLASSIFICATION_RUNNER_ROWS__", build_reclassification_runner_rows(reclassification_entries)
    )

    document = document.replace("__GROUP_AXIS_ROWS__", build_group_axis_rows(group_comparison_entries))
    document = document.replace("__LINEUP_SLOT_ROWS__", build_lineup_slot_rows(group_comparison_entries))
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "cpbl-wpa-decision-thresholds.html")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seasons = []
    missing = []
    for year, kind_code, start, end in SEASONS:
        season = load_season(year, kind_code, start, end)
        if season is None:
            missing.append(year)
        else:
            seasons.append(season)
    if missing:
        print(
            f"警告：{missing} 年缺少 cpbl_wpa_decision_model_*_summary.json 或 "
            f"cpbl_wpa_bootstrap_ci_*.json，請先執行 model_wpa_decisions.py 與 "
            f"bootstrap_wpa_threshold_ci.py"
        )
    if not seasons:
        raise SystemExit("沒有任何一季有完整資料，無法產生報告")

    we_summary = load_we_summary()
    reclassification_entries = []
    for year, kind_code, start, end in SEASONS:
        entry = load_reclassification(year, kind_code, start, end)
        if entry is not None:
            reclassification_entries.append(entry)
    if not reclassification_entries:
        print(
            "警告：找不到 cpbl_wpa_runner_reclassification_*_summary.json，"
            "請先執行 analyze_wpa_runner_reclassification.py（跑者翻盤區塊將留空）"
        )

    group_comparison_entries = []
    for year, kind_code, start, end in SEASONS:
        entry = load_group_comparison(year, kind_code, start, end)
        if entry is not None:
            group_comparison_entries.append(entry)
    if not group_comparison_entries:
        print(
            "警告：找不到 cpbl_wpa_group_comparison_*.json，"
            "請先執行 compare_wpa_groups.py（棒次/打者類型比較區塊將顯示為空）"
        )

    document = build_report(seasons, we_summary, reclassification_entries, group_comparison_entries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}（{len(seasons)} 季）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
