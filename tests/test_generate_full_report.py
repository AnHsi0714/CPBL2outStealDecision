import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import tempfile
import unittest
from pathlib import Path

from generate_full_report import discover_categories


class DiscoverCategoriesTests(unittest.TestCase):
    def test_variants_carry_a_size_hint_rounded_to_10_kb(self):
        # 入口頁靠這個欄位決定預載順序（小的先抓）；湊到 10 KB 是為了報告大小微動時入口頁不必跟著重產
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            (reports / "cpbl-re24-matrix-2025.html").write_bytes(b"x" * 41_000)
            (reports / "cpbl-steal-decision-2025.html").write_bytes(b"x" * 100_000)
            (reports / "cpbl-steal-decision-2024.html").write_bytes(b"x" * 100_900)
            categories = {c["id"]: c for c in discover_categories(reports)}
        self.assertEqual([v["kb"] for v in categories["re24"]["variants"]], [40])
        self.assertEqual([(v["year"], v["kb"]) for v in categories["decision"]["variants"]], [("2024", 100), ("2025", 100)])

    def test_categories_without_matching_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            (reports / "cpbl-re24-matrix-2025.html").write_bytes(b"x")
            ids = [c["id"] for c in discover_categories(reports)]
        self.assertEqual(ids, ["re24"])


if __name__ == "__main__":
    unittest.main()
