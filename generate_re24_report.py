"""把 build_re24_matrix.py 產生的 RE24 矩陣畫成互動熱力圖報告。

沿用專案既有的靜態 HTML 報告風格（見 generate_decision_report.py）：純標準
庫、資料內嵌在頁面裡、不依賴任何前端框架或圖表套件。配色依循 dataviz skill
的「單一色相、由淺到深」序列色規則（磁磚背景＝量級，文字維持中性墨色），
熱力圖格數少（3 出局數 × 8 壘包組合＝24 格），因此用 Python 端算好每格的
色階與對比文字色，直接輸出成固定的 CSS 規則，不需要前端 JS 做色彩運算。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "templates" / "re24_report.html"
STYLE_PATH = ROOT / "templates" / "re24_report.css"

# dataviz skill 的序列色（單一藍色相，100→700，淺到深），對齊 references/palette.md。
SEQUENTIAL_STEPS_LIGHT = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
# 深色模式「換錨點」：數值愈小愈貼近深色底（用同一組色階反轉），數值愈大愈亮眼。
SEQUENTIAL_STEPS_DARK = list(reversed(SEQUENTIAL_STEPS_LIGHT))

# 顯示用的壘包欄位順序（比 base_code 的位元順序更符合閱讀直覺）。
BASE_CODE_DISPLAY_ORDER = [0, 1, 2, 4, 3, 5, 6, 7]
BASE_LABELS = {
    0: "空壘", 1: "一壘", 2: "二壘", 4: "三壘",
    3: "一二壘", 5: "一三壘", 6: "二三壘", 7: "一二三壘",
}
OUTS_LABELS = {0: "0 出局", 1: "1 出局", 2: "2 出局"}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def relative_luminance(hex_color: str) -> float:
    def channel(c: int) -> float:
        c_norm = c / 255
        return c_norm / 12.92 if c_norm <= 0.03928 else ((c_norm + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    la, lb = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def best_ink(background_hex: str) -> str:
    dark_ink, light_ink = "#12130f", "#ffffff"
    return dark_ink if contrast_ratio(background_hex, dark_ink) >= contrast_ratio(background_hex, light_ink) else light_ink


def build_cell_styles() -> tuple[list[str], list[str]]:
    """回傳 (light 模式 CSS 規則, dark 模式 CSS 規則)，每個色階一條。"""
    light_rules = []
    dark_rules = []
    for level, (light_bg, dark_bg) in enumerate(zip(SEQUENTIAL_STEPS_LIGHT, SEQUENTIAL_STEPS_DARK)):
        light_rules.append(
            f'.cell[data-level="{level}"] {{ --cell-bg: {light_bg}; --cell-fg: {best_ink(light_bg)}; }}'
        )
        dark_rules.append(
            f'.cell[data-level="{level}"] {{ --cell-bg: {dark_bg}; --cell-fg: {best_ink(dark_bg)}; }}'
        )
    return light_rules, dark_rules


def level_for(value: float, value_min: float, value_max: float, steps: int = 13) -> int:
    if value_max <= value_min:
        return 0
    ratio = (value - value_min) / (value_max - value_min)
    return max(0, min(steps - 1, round(ratio * (steps - 1))))


def esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_report(summary: dict[str, Any]) -> str:
    cells_by_key = {(c["outs"], c["baseCode"]): c for c in summary["cells"]}
    known_values = [c["meanRE"] for c in summary["cells"] if c["meanRE"] is not None]
    value_min, value_max = min(known_values), max(known_values)

    light_rules, dark_rules = build_cell_styles()

    grid_cells_html = []
    table_rows_html = []
    for outs in (0, 1, 2):
        row_cells = []
        for base_code in BASE_CODE_DISPLAY_ORDER:
            cell = cells_by_key.get((outs, base_code))
            label = BASE_LABELS[base_code]
            if cell is None or cell["meanRE"] is None:
                row_cells.append(
                    f'<div class="cell empty" data-tooltip="{esc(OUTS_LABELS[outs])}・{esc(label)}｜無樣本">'
                    f'<span class="cell-value">—</span><span class="cell-n">n=0</span></div>'
                )
                continue
            level = level_for(cell["meanRE"], value_min, value_max)
            std_text = f'{cell["stdRE"]:.3f}' if cell["stdRE"] is not None else "—"
            tooltip = (
                f'{OUTS_LABELS[outs]}・{label}｜平均 {cell["meanRE"]:.3f} 分'
                f'｜n={cell["n"]:,}｜SD {std_text}'
            )
            row_cells.append(
                f'<div class="cell" data-level="{level}" tabindex="0" '
                f'data-tooltip="{esc(tooltip)}">'
                f'<span class="cell-value">{cell["meanRE"]:.3f}</span>'
                f'<span class="cell-n">n={cell["n"]:,}</span></div>'
            )
            table_rows_html.append(
                f'<tr><td>{OUTS_LABELS[outs]}</td><td>{label}</td>'
                f'<td>{cell["meanRE"]:.4f}</td><td>{std_text}</td><td>{cell["n"]:,}</td></tr>'
            )
        grid_cells_html.append(
            f'<div class="row-label">{OUTS_LABELS[outs]}</div>' + "".join(row_cells)
        )

    column_headers_html = "".join(
        f'<div class="col-label">{BASE_LABELS[code]}</div>' for code in BASE_CODE_DISPLAY_ORDER
    )

    legend_stops = " ,".join(SEQUENTIAL_STEPS_LIGHT)
    legend_stops_dark = " ,".join(SEQUENTIAL_STEPS_DARK)

    thresholds = summary.get("basic_break_even_threshold_by_outs", {})
    threshold_cards = "".join(
        f'<article class="stat"><small>{OUTS_LABELS[int(outs)]}｜RE(一壘)／RE(二壘)</small>'
        f'<strong>{(value * 100):.1f}%</strong>'
        f'<span>層次二基礎損益兩平門檻（未計保留效應）</span></article>'
        for outs, value in sorted(thresholds.items())
        if value is not None
    )

    total_segments = summary.get("total_state_segments", 0)
    games_processed = summary.get("games_processed", 0)
    year = summary.get("year")
    kind_code = summary.get("kind_code")
    start = summary.get("game_sno_start")
    end = summary.get("game_sno_end")

    style = STYLE_PATH.read_text(encoding="utf-8")
    style = style.replace("/*__LIGHT_LEVEL_RULES__*/", "\n    ".join(light_rules))
    style = style.replace("/*__DARK_LEVEL_RULES__*/", "\n      ".join(dark_rules))
    style = style.replace("__LEGEND_STOPS__", legend_stops)
    style = style.replace("__LEGEND_STOPS_DARK__", legend_stops_dark)

    document = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = document.replace("/*__STYLES__*/", style.rstrip("\n"))
    document = document.replace("__COLUMN_HEADERS__", column_headers_html)
    document = document.replace("__GRID_CELLS__", "".join(grid_cells_html))
    document = document.replace("__TABLE_ROWS__", "".join(table_rows_html))
    document = document.replace("__THRESHOLD_CARDS__", threshold_cards)
    document = document.replace("__LEGEND_MIN__", f"{value_min:.3f}")
    document = document.replace("__LEGEND_MAX__", f"{value_max:.3f}")
    document = document.replace("__TOTAL_SEGMENTS__", f"{total_segments:,}")
    document = document.replace("__GAMES_PROCESSED__", f"{games_processed:,}")
    document = document.replace("__YEAR__", str(year))
    document = document.replace("__KIND_CODE__", str(kind_code))
    document = document.replace("__RANGE__", f"{start}–{end}")
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stem = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    summary_json = args.summary_json or ROOT / "outputs" / f"cpbl_re24_matrix_{stem}_summary.json"
    output = args.output or ROOT / "reports" / f"cpbl-re24-matrix-{args.year}.html"

    with summary_json.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)

    document = build_report(summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote {output} ({summary.get('total_state_segments', 0):,} state 區段)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
