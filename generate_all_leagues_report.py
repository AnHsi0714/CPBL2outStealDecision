"""把 CPBL／MLB／KBO 的報告整合成單一入口頁面 reports/all-leagues-report.html。

右上角用 cpbl／mlb／kbo 標籤切換聯盟，下方沿用 generate_full_report.py 的分類（決策報告／RE24／WE／WPA）
與年份頁籤，直接用 iframe 載入各個單項報告，不再有各聯盟自己的整合入口頁。分類掃描規則與模板
（templates/full_report.*）重用 generate_full_report.py，只是把檔名規則的 `cpbl-` 換成各聯盟前綴。
樣式內嵌，所以輸出只有一個 html 檔；執行前需已產生各聯盟的單項報告，找不到的分類或聯盟會略過。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import generate_full_report as base

LEAGUES = ("cpbl", "mlb", "kbo")
OUTPUT_NAME = "all-leagues-report.html"


def league_categories(reports_dir: Path, league: str) -> list[dict]:
    original = list(base.CATEGORY_SPECS)
    try:
        base.CATEGORY_SPECS[:] = [
            {**spec, "pattern": re.compile(spec["pattern"].pattern.replace("cpbl-", f"{league}-"))}
            for spec in original
        ]
        return base.discover_categories(reports_dir)
    finally:
        base.CATEGORY_SPECS[:] = original


def build(reports_dir: Path) -> str:
    leagues = {name: league_categories(reports_dir, name) for name in LEAGUES}
    leagues = {name: cats for name, cats in leagues.items() if cats}
    if not leagues:
        raise SystemExit(f"{reports_dir} 底下找不到任何報告")

    style = base.STYLE_PATH.read_text(encoding="utf-8")
    script = base.SCRIPT_PATH.read_text(encoding="utf-8")
    common = (base.ROOT / "templates" / "report_common.js").read_text(encoding="utf-8")
    common_css = (base.ROOT / "templates" / "report_common.css").read_text(encoding="utf-8")
    # 原腳本一次只有一組分類；這裡把它包成「切換聯盟時換一組分類」。
    script = script.replace(
        'const categories = JSON.parse(document.getElementById("categories-data").textContent);',
        'const allLeagues = JSON.parse(document.getElementById("categories-data").textContent);\n'
        'let categories = [];',
    )
    script = script.replace("let activeCategoryId = categories[0].id;", "let activeCategoryId = null;")
    script = script.replace("activateCategory(activeCategoryId);\n", "")
    script += """
const leagueTabs = document.getElementById("league-tabs");

function renderPrimaryButtons() {
  primaryTabs.innerHTML = categories
    .map((c) => `<button type="button" class="tab" data-cat="${c.id}" aria-selected="false">${c.label}</button>`)
    .join("");
  primaryTabs.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => activateCategory(btn.dataset.cat));
  });
}

function activateLeague(league) {
  if (!allLeagues[league]) league = Object.keys(allLeagues)[0];
  categories = allLeagues[league];
  leagueTabs.querySelectorAll("button").forEach((btn) => {
    btn.setAttribute("aria-selected", btn.dataset.league === league ? "true" : "false");
  });
  document.getElementById("league-eyebrow").textContent = league.toUpperCase() + " · 2 OUT, RUNNER ON FIRST";
  try { history.replaceState(null, "", "#" + league); } catch (e) {}
  renderPrimaryButtons();
  // 換聯盟時保持在同一個分類，該分類不存在才回到第一個。
  const keep = categories.find((c) => c.id === activeCategoryId);
  activateCategory(keep ? keep.id : categories[0].id);
}

leagueTabs.addEventListener("click", (event) => {
  const btn = event.target.closest("button");
  if (btn) activateLeague(btn.dataset.league);
});

activateLeague(location.hash.replace("#", ""));
"""
    # 原本綁在靜態按鈕上的 click 註冊會在載入時找不到按鈕，改由 renderPrimaryButtons 處理。
    script = script.replace(
        'primaryTabs.querySelectorAll(".tab").forEach((btn) => {\n  btn.addEventListener("click", () => activateCategory(btn.dataset.cat));\n});\n\nsecondaryTabs.addEventListener',
        "secondaryTabs.addEventListener",
        1,
    )

    script = common + "\n" + script

    league_buttons = "".join(
        f'<button type="button" data-league="{name}" aria-selected="false">{name}</button>' for name in leagues
    )
    extra_css = """
    .league-tabs { display: flex; gap: 6px; margin-left: auto; }
    .league-tabs button { font: inherit; font-size: .8rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
      padding: 5px 14px; border: 1px solid var(--line); border-radius: 0; background: transparent; color: var(--text); cursor: pointer; }
    .league-tabs button:hover { background: color-mix(in srgb, var(--text) 14%, transparent); border-color: var(--text); }
    .league-tabs button[aria-selected="true"], .league-tabs button[aria-selected="true"]:hover { background: var(--text); color: var(--surface); border-color: var(--text); }
    .league-tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .title-row { align-items: center; }

    @media (max-width: 760px) {
      .mobile body { display: block; min-height: 0; }
      .mobile main { display: block; }
      .mobile .frame-panel { min-height: 0; margin: -2px -8px 0; }
      .mobile .report-frame { flex: none; height: 80vh; }
      .mobile .eyebrow { display: none; }
      .mobile h1 { flex: 1 1 0; min-width: 0; }
      .mobile .league-tabs { flex: 0 0 100%; justify-content: flex-end; }
      .mobile .tab, .mobile .sub-tab, .mobile .league-tabs button { min-height: 40px; }
      .mobile header { position: static; }
    }
"""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>三聯盟盜壘決策報告</title>
  <style>
{style}{extra_css}{common_css}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="title-row">
        <h1>兩出局、僅一壘有人，盜壘該不該跑？</h1>
        <div class="eyebrow" id="league-eyebrow"></div>
        <nav class="league-tabs" id="league-tabs" aria-label="聯盟">{league_buttons}</nav>
      </div>
      <div class="tabs-wrap">
        <div class="tabs-row">
          <nav class="tabs" id="primary-tabs"></nav>
          <div class="sub-tabs" id="secondary-tabs" hidden></div>
        </div>
      </div>
    </div>
  </header>

  <main class="wrap">
    <div class="frame-panel">
      <div class="frame-toolbar">
        <span id="frame-current-label" class="frame-label"></span>
        <a id="frame-open-new" href="#" target="_blank" rel="noopener">在新分頁開啟 ↗</a>
      </div>
      <iframe id="report-frame" class="report-frame" title="報告內容"></iframe>
    </div>
  </main>

  <script id="categories-data" type="application/json">{json.dumps(leagues, ensure_ascii=False)}</script>
  <script>
{script}
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=base.REPORTS_DIR)
    args = parser.parse_args()
    document = build(args.reports_dir)
    output = args.reports_dir / OUTPUT_NAME
    output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
