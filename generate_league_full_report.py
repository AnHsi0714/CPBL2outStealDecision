"""MLB／KBO 版的整合入口頁面：重用 generate_full_report.py 的分類掃描與模板，只把檔名規則從
`cpbl-` 換成 `<聯盟>-`，輸出 `<聯盟>-full-report.html/.css/.js`，並把模板裡寫死的聯盟名稱與
樣式／腳本檔名換掉。用法：python generate_league_full_report.py mlb（或 kbo）
"""

from __future__ import annotations

import re
import sys

import generate_full_report as base
from league_relabel import relabel


def main() -> int:
    league = sys.argv[1]
    if league not in ("mlb", "kbo"):
        raise SystemExit("聯盟必須是 mlb 或 kbo")
    base.CATEGORY_SPECS[:] = [
        {**spec, "pattern": re.compile(spec["pattern"].pattern.replace("cpbl-", f"{league}-"))}
        for spec in base.CATEGORY_SPECS
    ]
    base.OUTPUT_NAME = f"{league}-full-report.html"
    base.OUTPUT_CSS_NAME = f"{league}-full-report.css"
    base.OUTPUT_JS_NAME = f"{league}-full-report.js"
    sys.argv = [sys.argv[0]]
    code = base.main()
    if code == 0:
        html = base.REPORTS_DIR / base.OUTPUT_NAME
        document = relabel(html.read_text(encoding="utf-8"), league)
        document = document.replace("cpbl-full-report", f"{league}-full-report")
        html.write_text(document, encoding="utf-8", newline="\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
