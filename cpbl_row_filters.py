"""共用的 CPBL 逐球資料列過濾工具。

獨立成模組是因為 `find_2out_first_base.py` 會 `import CPBL_steal_getData`，若讓
`CPBL_steal_getData.py` 反過來 `from find_2out_first_base import ...`會造成循環
import；把過濾邏輯抽到這個沒有專案內部依賴的模組，兩邊都能安全 import。
"""

from __future__ import annotations

from typing import Any


# CPBL 逐球資料裡混著「換投手／代打／代跑／守備／選手」等純公告列，不是真正的
# 投球事件；這種列的 OutCnt／FirstBase／SecondBase／ThirdBase 是殘留自公告發生
# 當下、尚未被下一球更新的舊值，不能當成真實比賽狀態使用（常見於半局交替或
# 換投時，殘留值可能是上一個狀態，也可能是下一個真正打席的前一刻）。用
# 「Content 以『更換』開頭，且不含任何投球結果關鍵字」辨識，實測約佔全部
# 列數 3%。
ADMINISTRATIVE_CONTENT_PREFIX = "更換"
PLAY_CONTENT_MARKERS = (
    "壞球", "好球", "擊出", "四壞", "觸身", "妨礙",
    "盜", "牽制", "暴投", "捕逸", "投手犯規",
)


def is_administrative_only_row(row: dict[str, Any]) -> bool:
    content = str(row.get("Content") or "").strip()
    if not content.startswith(ADMINISTRATIVE_CONTENT_PREFIX):
        return False
    return not any(marker in content for marker in PLAY_CONTENT_MARKERS)


def remove_administrative_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if not is_administrative_only_row(row)]
