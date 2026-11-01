import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import league_relabel
from league_relabel import relabel

DOCUMENT = (
    "<title>2025 CPBL 兩出局僅一壘有人：盜壘決策報告</title>\n"
    '<div class="eyebrow">CPBL · 2025 REGULAR SEASON</div>\n'
    '<h2 id="overview-title">2025 資料概況</h2>\n'
    "資料：CPBL 官網逐球紀錄\n"
)


class RelabelTests(unittest.TestCase):
    def test_replaces_league_name_and_source(self):
        result = relabel(DOCUMENT, "mlb")
        self.assertIn("<title>2025 MLB", result)
        self.assertIn("MLB Stats API（Gumbo）逐打席紀錄", result)
        self.assertNotIn("CPBL", result)

    def test_replaces_the_template_year_when_given(self):
        result = relabel(DOCUMENT, "kbo", "2023")
        self.assertIn("<title>2023 KBO", result)
        self.assertIn("KBO · 2023 REGULAR SEASON", result)
        self.assertIn(">2023 資料概況<", result)
        self.assertNotIn("2025", result)

    def test_command_line_passes_the_year_through(self):
        # 命令列的第三個參數（年份）曾經被忽略，MLB／KBO 各年報告標題都寫成 2025
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            path.write_text(DOCUMENT, encoding="utf-8")
            with mock.patch.object(_sys, "argv", ["league_relabel.py", str(path), "mlb", "2024"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    league_relabel.main()
            result = path.read_text(encoding="utf-8")
        self.assertIn("<title>2024 MLB", result)
        self.assertIn(">2024 資料概況<", result)
        self.assertNotIn("2025", result)

    def test_command_line_without_a_year_keeps_the_template_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            path.write_text(DOCUMENT, encoding="utf-8")
            with mock.patch.object(_sys, "argv", ["league_relabel.py", str(path), "kbo"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    league_relabel.main()
            result = path.read_text(encoding="utf-8")
        self.assertIn("<title>2025 KBO", result)


if __name__ == "__main__":
    unittest.main()
