"""同 analyze_batter_types.py，資料來源換成 MLB。ISO_proxy/BBpct_proxy/OBP_proxy/
SingleRate_proxy/TTO_proxy 的算法完全共用（都只是讀 profiles CSV 的欄位），唯一要換的是
PrimaryLineupGroup 的計算來源：CPBL 版掃逐球快取算眾數棒次，MLB 版直接讀 Gumbo
boxscore 的 battingOrder（本來就是該球員整場最終棒次，不必再算眾數）。
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_batter_types import (
    annotate,
    apply_primary_lineup,
    correlation,
    load_profiles,
    write_csv,
)
from mlb_find_2out_first_base import batting_order_slots


def compute_primary_lineup(cache_dir: Path) -> dict[str, int]:
    tally: dict[str, Counter[int]] = defaultdict(Counter)
    for path in sorted(cache_dir.glob("game_*.json")):
        feed = json.loads(path.read_text(encoding="utf-8"))
        for batter_id, slot in batting_order_slots(feed).items():
            if 1 <= slot <= 9:
                tally[str(batter_id)][slot] += 1
    return {hitter_id: counter.most_common(1)[0][0] for hitter_id, counter in tally.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--profiles-csv", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--min-pa", type=float, default=100.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.start_date}_{args.end_date}"
    profiles_csv = args.profiles_csv or Path("outputs") / f"mlb_batter_profiles_{tag}.csv"
    output = args.output or Path("outputs") / f"mlb_batter_types_{tag}.csv"

    rows = load_profiles(profiles_csv, args.min_pa)
    if not rows:
        raise SystemExit(f"沒有打席數 >= {args.min_pa} 的打者，無法分組")

    rows, iso_median, bb_median, obp_median, single_median, tto_median = annotate(rows)

    cache_dir = args.cache_dir or Path("data/raw/mlb") / tag
    if cache_dir.exists():
        apply_primary_lineup(rows, compute_primary_lineup(cache_dir))
    else:
        print(f"提醒：找不到 {cache_dir}，略過 PrimaryLineupGroup 計算")
        apply_primary_lineup(rows, {})

    write_csv(rows, output)

    print(f"符合 PA >= {args.min_pa} 的打者：{len(rows)} 位")
    print(f"ISO_proxy 中位數：{iso_median:.4f}　BBpct_proxy 中位數：{bb_median:.4f}　"
          f"OBP_proxy 中位數：{obp_median:.4f}　SingleRate_proxy 中位數：{single_median:.4f}　"
          f"TTO_proxy 中位數：{tto_median:.4f}")
    corr_bb = correlation([r["ISO_proxy"] for r in rows], [r["BBpct_proxy"] for r in rows])
    corr_tto = correlation([r["ISO_proxy"] for r in rows], [r["TTO_proxy"] for r in rows])
    print(f"ISO 與 BB% 相關係數：{corr_bb}　ISO 與 TTO 相關係數：{corr_tto}")
    print(f"輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
