"""驗證 `analyze_steal_timing.py` 算出的「球數落後時盜壘率較高」是否為真訊號，
不是巧合或雜訊。讀該腳本四季已輸出的 CSV（`cpbl_steal_count_diff_{tag}.csv`、
`cpbl_steal_count_diff_by_team_{tag}.csv`），不重算、不重爬。

兩種檢定：

1. 全聯盟層級：每季各自、以及四季合併，把「球數落後（好球數>壞球數）」vs
   「球數領先（壞球數>好球數）」的投球機會／盜壘嘗試做成 2x2 表，跑
   Fisher's exact test（小格數也穩健，不用擔心卡方檢定的期望次數下限）。
2. 逐隊一致性（符號檢定）：23 個「隊×年」樣本（2023 五隊＋2024–2026 各六
   隊）裡，有幾個「落後」盜壘率高於「領先」盜壘率。如果這個方向純屬雜訊，
   理論上應接近對半（各隊、各年互相獨立，方向隨機），用 `binomtest` 檢定
   實際偏向一邊的比例是否顯著偏離 50%——這是比單季全聯盟檢定更強的證據，
   因為它同時跨隊跨年重複驗證同一個方向。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scipy.stats import binomtest, fisher_exact


DEFAULT_TAGS = ["2023_A_1-300", "2024_A_1-360", "2025_A_1-360", "2026_A_1-240"]


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def behind_ahead_counts(rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    """回傳 (落後投球數, 落後盜壘數, 領先投球數, 領先盜壘數)。"""
    behind_pitches = behind_attempts = ahead_pitches = ahead_attempts = 0
    for row in rows:
        diff = int(row["CountDiff"])
        pitches = int(row["PitchOpportunities"])
        attempts = int(row["StealAttempts"])
        if diff >= 1:
            behind_pitches += pitches
            behind_attempts += attempts
        elif diff <= -1:
            ahead_pitches += pitches
            ahead_attempts += attempts
    return behind_pitches, behind_attempts, ahead_pitches, ahead_attempts


def fisher_on_counts(
    behind_pitches: int, behind_attempts: int, ahead_pitches: int, ahead_attempts: int
) -> tuple[float, float]:
    table = [
        [behind_attempts, behind_pitches - behind_attempts],
        [ahead_attempts, ahead_pitches - ahead_attempts],
    ]
    odds_ratio, p_value = fisher_exact(table)
    return odds_ratio, p_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tags", nargs="+", default=DEFAULT_TAGS)
    parser.add_argument("--input-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("== 全聯盟層級：球數落後 vs 領先，Fisher's exact test ==\n")
    season_results: list[dict[str, Any]] = []
    pooled_behind_pitches = pooled_behind_attempts = 0
    pooled_ahead_pitches = pooled_ahead_attempts = 0

    for tag in args.tags:
        path = args.input_dir / f"cpbl_steal_count_diff_{tag}.csv"
        rows = load_csv(path)
        bp, ba, ap, aa = behind_ahead_counts(rows)
        rate_behind = ba / bp if bp else 0.0
        rate_ahead = aa / ap if ap else 0.0
        odds_ratio, p_value = fisher_on_counts(bp, ba, ap, aa)
        print(
            f"{tag}：落後 {ba}/{bp}={rate_behind:.2%}，領先 {aa}/{ap}={rate_ahead:.2%}，"
            f"odds ratio={odds_ratio:.2f}，p={p_value:.4g}"
        )
        season_results.append(
            {
                "Tag": tag,
                "BehindPitches": bp,
                "BehindAttempts": ba,
                "BehindRate": rate_behind,
                "AheadPitches": ap,
                "AheadAttempts": aa,
                "AheadRate": rate_ahead,
                "OddsRatio": odds_ratio,
                "PValue": p_value,
            }
        )
        pooled_behind_pitches += bp
        pooled_behind_attempts += ba
        pooled_ahead_pitches += ap
        pooled_ahead_attempts += aa

    pooled_rate_behind = pooled_behind_attempts / pooled_behind_pitches
    pooled_rate_ahead = pooled_ahead_attempts / pooled_ahead_pitches
    pooled_odds_ratio, pooled_p_value = fisher_on_counts(
        pooled_behind_pitches, pooled_behind_attempts, pooled_ahead_pitches, pooled_ahead_attempts
    )
    print(
        f"\n四季合併：落後 {pooled_behind_attempts}/{pooled_behind_pitches}={pooled_rate_behind:.2%}，"
        f"領先 {pooled_ahead_attempts}/{pooled_ahead_pitches}={pooled_rate_ahead:.2%}，"
        f"odds ratio={pooled_odds_ratio:.2f}，p={pooled_p_value:.4g}"
    )

    print("\n== 逐隊一致性：23 個「隊×年」樣本中，落後盜壘率 > 領先盜壘率 的比例 ==\n")
    same_direction = 0
    total_team_seasons = 0
    team_season_rows: list[dict[str, Any]] = []
    for tag in args.tags:
        path = args.input_dir / f"cpbl_steal_count_diff_by_team_{tag}.csv"
        rows = load_csv(path)
        teams = sorted({row["Team"] for row in rows})
        for team in teams:
            team_rows = [row for row in rows if row["Team"] == team]
            bp, ba, ap, aa = behind_ahead_counts(team_rows)
            rate_behind = ba / bp if bp else 0.0
            rate_ahead = aa / ap if ap else 0.0
            favors_behind = rate_behind > rate_ahead
            total_team_seasons += 1
            same_direction += int(favors_behind)
            print(
                f"{tag} {team}：落後 {rate_behind:.2%}（n={bp}）vs 領先 {rate_ahead:.2%}（n={ap}）"
                f"{'yes' if favors_behind else 'no'}"
            )
            team_season_rows.append(
                {
                    "Tag": tag,
                    "Team": team,
                    "BehindRate": rate_behind,
                    "BehindPitches": bp,
                    "AheadRate": rate_ahead,
                    "AheadPitches": ap,
                    "FavorsBehind": favors_behind,
                }
            )

    sign_test = binomtest(same_direction, total_team_seasons, 0.5)
    print(
        f"\n{same_direction}/{total_team_seasons} 個隊×年樣本方向一致"
        f"（落後盜壘率較高），符號檢定 p={sign_test.pvalue:.4g}（虛無假設：方向 50/50 隨機）"
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "cpbl_steal_timing_significance.json"
    summary_path.write_text(
        json.dumps(
            {
                "SeasonResults": season_results,
                "Pooled": {
                    "BehindPitches": pooled_behind_pitches,
                    "BehindAttempts": pooled_behind_attempts,
                    "BehindRate": pooled_rate_behind,
                    "AheadPitches": pooled_ahead_pitches,
                    "AheadAttempts": pooled_ahead_attempts,
                    "AheadRate": pooled_rate_ahead,
                    "OddsRatio": pooled_odds_ratio,
                    "PValue": pooled_p_value,
                },
                "TeamSeasonResults": team_season_rows,
                "SignTest": {
                    "SameDirection": same_direction,
                    "Total": total_team_seasons,
                    "PValue": sign_test.pvalue,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n摘要已寫出：{summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
