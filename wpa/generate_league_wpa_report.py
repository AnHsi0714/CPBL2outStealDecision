"""MLB／KBO 版 WPA 門檻比較報告：重用 generate_wpa_report.py 的 SVG 與表格產生函式，但換成不含 CPBL
專屬結論的中性模板（templates/wpa_report_league.html）。

CPBL 版模板把「RE 門檻落在 54–60%」「第 4 局起數字穩定」等 CPBL 四季的結論寫死在文字裡，
直接套到其他聯盟會變成錯的敘述，所以另外準備只保留方法說明與資料表的模板。
generate_wpa_report.py 的輸入路徑是寫死的 cpbl_ 檔名＋年份標籤，這裡把本聯盟的輸出複製到暫存目錄
（outputs/_wpa_stage_<聯盟>/outputs/）並改名，產生完就刪除。

用法：python wpa/generate_league_wpa_report.py mlb（或 kbo）
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import shutil
import sys
from pathlib import Path

import generate_wpa_report as base
from league_relabel import relabel

ROOT = Path(__file__).resolve().parent.parent
YEARS = (2023, 2024, 2025, 2026)


def tag_for(league: str, year: int) -> str:
    return f"{year}-03-15_{year}-10-10" if league == "mlb" else str(year)


def main() -> int:
    league = sys.argv[1]
    if league not in ("mlb", "kbo"):
        raise SystemExit("聯盟必須是 mlb 或 kbo")
    out = ROOT / "outputs"
    stage = out / f"_wpa_stage_{league}"
    (stage / "outputs").mkdir(parents=True, exist_ok=True)
    fake = lambda year: f"{year}_R_1-1"  # noqa: E731

    for year in YEARS:
        tag = tag_for(league, year)
        pairs = [
            (f"{league}_wpa_decision_model_{tag}_summary.json", f"cpbl_wpa_decision_model_{fake(year)}_summary.json"),
            (f"{league}_wpa_bootstrap_ci_{tag}.json", f"cpbl_wpa_bootstrap_ci_{fake(year)}.json"),
            (f"{league}_wpa_runner_reclassification_{tag}_summary.json", f"cpbl_wpa_runner_reclassification_{fake(year)}_summary.json"),
            (f"{league}_wpa_runner_reclassification_{tag}.csv", f"cpbl_wpa_runner_reclassification_{fake(year)}.csv"),
            (f"{league}_wpa_group_comparison_{tag}.json", f"cpbl_wpa_group_comparison_{fake(year)}.json"),
        ]
        for source, target in pairs:
            if (out / source).exists():
                shutil.copy(out / source, stage / "outputs" / target)
    shutil.copy(
        out / f"{league}_win_expectancy_matrix_2023-2026_R_combined_summary.json",
        stage / "outputs" / "cpbl_win_expectancy_matrix_2023-2026_A_combined_summary.json",
    )

    base.ROOT = stage
    base.SEASONS = [(year, "R", 1, 1) for year in YEARS]
    base.TEMPLATE_PATH = ROOT / "templates" / "wpa_report_league.html"
    output = ROOT / "reports" / f"{league}-wpa-decision-thresholds.html"
    sys.argv = [sys.argv[0], "--output", str(output)]
    try:
        code = base.main()
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if code == 0:
        document = output.read_text(encoding="utf-8").replace("__LEAGUE_NOTE__", league.upper())
        output.write_text(relabel(document, league), encoding="utf-8", newline="\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
