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

    document = HTML_TEMPLATE
    document = document.replace("__LIGHT_LEVEL_RULES__", "\n    ".join(light_rules))
    document = document.replace("__DARK_LEVEL_RULES__", "\n      ".join(dark_rules))
    document = document.replace("__COLUMN_HEADERS__", column_headers_html)
    document = document.replace("__GRID_CELLS__", "".join(grid_cells_html))
    document = document.replace("__TABLE_ROWS__", "".join(table_rows_html))
    document = document.replace("__THRESHOLD_CARDS__", threshold_cards)
    document = document.replace("__LEGEND_STOPS__", legend_stops)
    document = document.replace("__LEGEND_STOPS_DARK__", legend_stops_dark)
    document = document.replace("__LEGEND_MIN__", f"{value_min:.3f}")
    document = document.replace("__LEGEND_MAX__", f"{value_max:.3f}")
    document = document.replace("__TOTAL_SEGMENTS__", f"{total_segments:,}")
    document = document.replace("__GAMES_PROCESSED__", f"{games_processed:,}")
    document = document.replace("__YEAR__", str(year))
    document = document.replace("__KIND_CODE__", str(kind_code))
    document = document.replace("__RANGE__", f"{start}–{end}")
    return document


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>中職 RE24 得分期望值矩陣</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f4f1ea;
      --surface: #fffdf8;
      --text: #18201c;
      --muted: #65706a;
      --line: #d9d4c9;
      --accent: #d59c25;
      --shadow: 0 14px 35px rgba(43, 49, 45, .09);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111512;
        --surface: #1a201c;
        --text: #edf2ee;
        --muted: #aab5ae;
        --line: #39423c;
        --accent: #efbd55;
        --shadow: none;
      }
      __DARK_LEVEL_RULES__
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      line-height: 1.65;
    }
    .wrap { width: min(1080px, calc(100% - 32px)); margin: 0 auto; }
    header { padding: 56px 0 26px; border-bottom: 1px solid var(--line); }
    .eyebrow { color: var(--accent); font-weight: 700; letter-spacing: .08em; }
    h1 { max-width: 780px; margin: 8px 0 12px; font-size: clamp(1.8rem, 4.4vw, 3.2rem); line-height: 1.12; letter-spacing: -.03em; }
    h2 { margin: 0 0 18px; font-size: clamp(1.3rem, 2.6vw, 1.7rem); }
    p { margin: 0 0 12px; }
    .lede { max-width: 720px; color: var(--muted); font-size: 1.03rem; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 20px; color: var(--muted); font-size: .88rem; }
    main { padding: 34px 0 80px; }
    section { margin: 0 0 52px; }
    .panel { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); padding: 24px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .stat { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); padding: 18px; }
    .stat small { display: block; color: var(--muted); }
    .stat strong { display: block; margin: 3px 0; font-size: 1.6rem; line-height: 1.2; }
    .stat span { color: var(--muted); font-size: .82rem; }

    .heatmap {
      display: grid;
      grid-template-columns: 84px repeat(8, 1fr);
      gap: 4px;
      margin-top: 6px;
    }
    .col-label, .row-label {
      display: flex; align-items: center; justify-content: center;
      font-size: .82rem; color: var(--muted); font-weight: 600;
      padding: 6px 2px; text-align: center;
    }
    .row-label { justify-content: flex-start; padding-left: 4px; }
    .cell {
      position: relative;
      border-radius: 10px;
      min-height: 64px;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 2px;
      background: var(--cell-bg, var(--line));
      color: var(--cell-fg, var(--text));
      outline: none;
      cursor: default;
    }
    .cell:focus-visible { box-shadow: 0 0 0 2px var(--accent); }
    .cell.empty { background: transparent; border: 1px dashed var(--line); color: var(--muted); }
    .cell-value { font-weight: 700; font-size: 1rem; font-variant-numeric: tabular-nums; }
    .cell-n { font-size: .68rem; opacity: .85; font-variant-numeric: tabular-nums; }
    .cell::after {
      content: attr(data-tooltip);
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%);
      background: var(--text);
      color: var(--surface);
      padding: 6px 10px;
      border-radius: 8px;
      font-size: .76rem;
      white-space: nowrap;
      opacity: 0;
      pointer-events: none;
      transition: opacity .12s ease;
      z-index: 5;
      box-shadow: var(--shadow);
    }
    .cell:hover::after, .cell:focus-visible::after { opacity: 1; }

    .legend { display: flex; align-items: center; gap: 12px; margin-top: 22px; }
    .legend-bar {
      flex: 1;
      height: 14px;
      border-radius: 999px;
      background: linear-gradient(to right, __LEGEND_STOPS__);
    }
    @media (prefers-color-scheme: dark) {
      .legend-bar { background: linear-gradient(to right, __LEGEND_STOPS_DARK__); }
    }
    .legend span { font-size: .82rem; color: var(--muted); white-space: nowrap; }

    .table-wrap { overflow-x: auto; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
    th { color: var(--muted); font-weight: 650; }

    details > summary { cursor: pointer; color: var(--muted); font-size: .88rem; margin-top: 4px; }

    footer { padding: 24px 0 50px; border-top: 1px solid var(--line); color: var(--muted); font-size: .85rem; }
    @media (max-width: 720px) {
      .grid { grid-template-columns: 1fr; }
      .heatmap { grid-template-columns: 56px repeat(8, minmax(46px, 1fr)); }
      .cell-n { display: none; }
    }
  </style>
  <style>
    __LIGHT_LEVEL_RULES__
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="eyebrow">CPBL __YEAR__ REGULAR SEASON</div>
      <h1>中職 RE24 得分期望值矩陣</h1>
      <p class="lede">24 種 base-out state（3 種出局數 × 8 種壘包組合）各自「從該狀態起算到半局結束」的平均剩餘得分。起算點對齊到壘包狀態實際變化的那一球，不是打席或半局的開頭——方法見計畫書 3.0 節。</p>
      <div class="meta">
        <span>KindCode __KIND_CODE__</span>
        <span>GameSno __RANGE__</span>
        <span>__GAMES_PROCESSED__ 場已處理</span>
        <span>__TOTAL_SEGMENTS__ 個 state 區段觀測值</span>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section aria-labelledby="heatmap-title">
      <h2 id="heatmap-title">RE24 熱力圖</h2>
      <div class="panel">
        <div class="heatmap">
          <div class="row-label"></div>
          __COLUMN_HEADERS__
          __GRID_CELLS__
        </div>
        <div class="legend">
          <span>__LEGEND_MIN__ 分</span>
          <div class="legend-bar"></div>
          <span>__LEGEND_MAX__ 分</span>
        </div>
        <p class="lede" style="margin-top:14px; font-size:.86rem">顏色深淺（淺色模式）／亮度（深色模式）代表平均剩餘得分的相對高低；每格滑鼠移過或鍵盤 Tab 到該格可看到樣本數與標準差。空白格代表本季無樣本觀測到該 state。</p>
        <details style="margin-top:16px">
          <summary>顯示完整資料表</summary>
          <div class="table-wrap">
            <table>
              <thead><tr><th>出局數</th><th>壘包狀態</th><th>平均 RE</th><th>SD</th><th>N</th></tr></thead>
              <tbody>__TABLE_ROWS__</tbody>
            </table>
          </div>
        </details>
      </div>
    </section>

    <section aria-labelledby="threshold-title">
      <h2 id="threshold-title">由 RE24 直接推導的基礎門檻（層次二）</h2>
      <p class="lede">計畫書 3.1 節層次二公式：<code>p ≥ RE(一壘) / RE(二壘)</code>，尚未計入盜壘失敗的「保留打者到下一局」效應（層次三蒙地卡羅模擬已處理，見 README 逐棒次門檻）。此處僅作為與模擬結果交叉核對的基準值。</p>
      <div class="grid" style="margin-top:14px">__THRESHOLD_CARDS__</div>
    </section>
  </main>

  <footer><div class="wrap">資料：CPBL 官網逐球紀錄，__YEAR__ 例行賽 GameSno __RANGE__ · RE 計算對齊事件發生當下（計畫書 3.0 節），排除未打完的半局 · 由 build_re24_matrix.py 產生</div></footer>
</body>
</html>
'''


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
