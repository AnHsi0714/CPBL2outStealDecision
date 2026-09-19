"""讓 scrapers/pipeline/re24/win_expectancy/wpa/analysis 底下的腳本可以互相 import。

程式碼搬進功能資料夾後，各腳本原本的扁平 import（例如
`from find_2out_first_base import as_int`）不需要改寫成套件路徑，只要在被
import 之前，把每個功能資料夾加進 sys.path 即可。這支模組就是做這件事，
在每支腳本最前面 `import pathsetup` 一次即可生效。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SUBDIRS = ("scrapers", "pipeline", "re24", "win_expectancy", "wpa", "analysis")


def add_all() -> None:
    root = Path(__file__).resolve().parent
    for sub in _SUBDIRS:
        path_str = str(root / sub)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


add_all()
