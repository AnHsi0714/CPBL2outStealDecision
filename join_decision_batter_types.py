"""第 2 步：把棒次分組（前段1-5/後段6-9）與打者類型分組（長打/選球）貼到每一筆決策上。

輸入：
  cpbl_decision_model_{tag}.csv  每筆決策一列（含 HitterLineup、HitterAcnt、BreakEvenSuccessRate 等）
  cpbl_batter_types_{tag}.csv    每位合格打者（PA >= min-pa）一列（含 PowerGroup、PatienceGroup）

打者類型是打者查表 join，join 不到（PA < min-pa）的列會保留在輸出裡，
PowerGroup/PatienceGroup 留空，交由後續分析階段自行決定要不要納入。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


def lineup_group(value: str) -> str:
    slot = int(value)
    if 1 <= slot <= 5:
        return "front_1_5"
    if 6 <= slot <= 9:
        return "back_6_9"
    raise ValueError(f"未知棒次：{value}")


def load_types(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return {row["HitterAcnt"]: row for row in csv.DictReader(file)}


def join(decisions: list[dict[str, Any]], types: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    joined = []
    for row in decisions:
        type_row = types.get(row["HitterAcnt"])
        joined.append(
            {
                **row,
                "LineupGroup": lineup_group(row["HitterLineup"]),
                "ISO_proxy": type_row["ISO_proxy"] if type_row else "",
                "BBpct_proxy": type_row["BBpct_proxy"] if type_row else "",
                "OBP_proxy": type_row["OBP_proxy"] if type_row else "",
                "SingleRate_proxy": type_row["SingleRate_proxy"] if type_row else "",
                "TTO_proxy": type_row["TTO_proxy"] if type_row else "",
                "PowerGroup": type_row["PowerGroup"] if type_row else "",
                "PatienceGroup": type_row["PatienceGroup"] if type_row else "",
                "OBPGroup": type_row["OBPGroup"] if type_row else "",
                "ContactGroup": type_row["ContactGroup"] if type_row else "",
                "TTOGroup": type_row["TTOGroup"] if type_row else "",
                "BatterTypeQualified": bool(type_row),
            }
        )
    return joined


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise RuntimeError(f"{path} 沒有資料")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--decision-csv", type=Path)
    parser.add_argument("--types-csv", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    decision_csv = args.decision_csv or Path("outputs") / f"cpbl_decision_model_{tag}.csv"
    types_csv = args.types_csv or Path("outputs") / f"cpbl_batter_types_{tag}.csv"
    output = args.output or Path("outputs") / f"cpbl_decision_with_types_{tag}.csv"

    with decision_csv.open(encoding="utf-8-sig", newline="") as file:
        decisions = list(csv.DictReader(file))
    types = load_types(types_csv)

    joined = join(decisions, types)
    write_csv(joined, output)

    qualified = sum(row["BatterTypeQualified"] for row in joined)
    front = sum(row["LineupGroup"] == "front_1_5" for row in joined)
    back = sum(row["LineupGroup"] == "back_6_9" for row in joined)

    print(f"合併後決策列數：{len(joined)}")
    print(f"打者類型合格（PA足夠）：{qualified}／{len(joined)}")
    print(f"棒次分組：前段(1-5) {front} 筆、後段(6-9) {back} 筆")
    print(f"輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
