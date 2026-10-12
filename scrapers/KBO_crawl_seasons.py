"""分季爬取 KBO 一軍逐場文字轉播，原始 HTML 快取於 data/raw/kbo/{year}/，輸出逐事件 CSV。

KBO_steal_getData.py 只能逐段日期爬、沒有快取，中斷就得整批重來；這支包一層：
賽程逐日查詢後，每場 HTML 先查快取，沒有才請求，所以可以中斷後續跑。
用法：python scrapers/KBO_crawl_seasons.py --year 2025 --start 2025-03-15 --end 2025-10-20
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import argparse
from pathlib import Path

import KBO_steal_getData as kbo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/kbo"))
    parser.add_argument("--output-dir", type=Path, default=Path("kbo_data"))
    args = parser.parse_args()

    cache = args.cache_dir / args.year
    cache.mkdir(parents=True, exist_ok=True)
    games = kbo.get_schedule(args.start, args.end)
    print(f"賽程找到 {len(games)} 場")

    rows, failures = [], []
    for i, g in enumerate(games, 1):
        cache_file = cache / f"{g['GameId']}.html"
        try:
            if cache_file.exists():
                html = cache_file.read_text(encoding="utf-8")
            else:
                html = kbo.get_full_text(g["GameId"], args.year)
                cache_file.write_text(html, encoding="utf-8")
                kbo.polite_sleep()
            game_rows = kbo.parse_game(g, html)
            rows.extend(game_rows)
            print(f"[{i}/{len(games)}] {g['GameDate']} {g['GameId']}：{len(game_rows)} 列")
        except Exception as error:
            failures.append(g["GameId"])
            print(f"[{i}/{len(games)}] {g['GameId']} 失敗：{error}")
            kbo.polite_sleep()

    args.output_dir.mkdir(exist_ok=True)
    kbo.save_to_csv(rows, str(args.output_dir / f"kbo_playbyplay_{args.year}_{args.start}_{args.end}.csv"))
    print(f"失敗 {len(failures)} 場：{failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
