"""MLB／KBO 的超參數敏感度：模擬次數、prior_pa、minimum_transition_cell、打者類型 min-pa。

做法同 analyze_hyperparameter_sensitivity.py（CPBL 版讀 cpbl_ 命名的既有變體輸出），這裡因為
MLB／KBO 的輸出檔名前綴不同，改成自己負責把每個變體跑出來：每個變體用自己的 --output-dir
（outputs/sensitivity_<聯盟>_<標籤>/<變體>/），不寫回 outputs/ 的基準檔。比較：
  1. 模擬類三個超參數：整體門檻中位數與逐棒次門檻中位數相對基準的最大差距（pp）。
  2. min-pa：重跑 打者類型 → join → 棒次×打者類型比較，看各組比較的顯著性（p<0.05）是否翻轉。

用法：python analysis/league_hyperparameter_sensitivity.py mlb 2025-03-15_2025-10-10
      python analysis/league_hyperparameter_sensitivity.py kbo 2025
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent)); import pathsetup  # noqa: E402,F401
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SIM_VARIANTS = {
    "simulations_500": ["--simulations", "500"],
    "simulations_4000": ["--simulations", "4000"],
    "prior_pa_25": ["--prior-pa", "25"],
    "prior_pa_100": ["--prior-pa", "100"],
    "min_cell_2": ["--minimum-transition-cell", "2"],
    "min_cell_10": ["--minimum-transition-cell", "10"],
}
MIN_PA_VARIANTS = (50, 200)


def league_args(league: str, tag: str) -> list[str]:
    if league == "mlb":
        start, end = tag.split("_")
        return ["--start-date", start, "--end-date", end]
    return ["--year", tag]


def run(command: list[str], allow_unmatched_exit: bool = False) -> None:
    """模型腳本在有決策樣本對不上原始場次（unmatched）時回傳 1 但仍會寫出完整輸出，
    此時由呼叫端檢查輸出檔存在，不當成失敗。"""
    result = subprocess.run(command, stdout=subprocess.DEVNULL, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    if result.returncode != 0 and not (allow_unmatched_exit and result.returncode == 1):
        raise subprocess.CalledProcessError(result.returncode, command)


def slot_medians(summary: dict[str, Any]) -> dict[str, float]:
    return {s: v["median_break_even_rate_in_0_1"] for s, v in summary["by_hitter_lineup"].items()
            if v.get("median_break_even_rate_in_0_1") is not None}


def main() -> int:
    league, tag = sys.argv[1], sys.argv[2]
    base_args = league_args(league, tag)
    out_root = Path("outputs") / f"sensitivity_{league}_{tag}"
    baseline = json.loads((Path("outputs") / f"{league}_decision_model_{tag}_summary.json").read_text(encoding="utf-8"))
    base_overall, base_slots = baseline["median_break_even_rate_in_0_1"], slot_medians(baseline)

    results: dict[str, Any] = {"league": league, "tag": tag, "baselineMedian": base_overall, "simVariants": {}, "minPaVariants": {}}
    for name, extra in SIM_VARIANTS.items():
        directory = out_root / name
        directory.mkdir(parents=True, exist_ok=True)
        run([sys.executable, f"pipeline/{league}_model_batter_decisions.py", *base_args, "--output-dir", str(directory), *extra],
            allow_unmatched_exit=True)
        summary = json.loads((directory / f"{league}_decision_model_{tag}_summary.json").read_text(encoding="utf-8"))
        slots = slot_medians(summary)
        max_slot_diff = max(abs(slots[s] - base_slots[s]) for s in base_slots if s in slots)
        results["simVariants"][name] = {
            "median": summary["median_break_even_rate_in_0_1"],
            "overallDiffPP": (summary["median_break_even_rate_in_0_1"] - base_overall) * 100,
            "maxSlotDiffPP": max_slot_diff * 100,
        }
        print(f"{name}: 整體中位數 {summary['median_break_even_rate_in_0_1']:.4f}（差 {results['simVariants'][name]['overallDiffPP']:+.2f}pp），"
              f"逐棒次最大差 {max_slot_diff * 100:.2f}pp", flush=True)

    base_comparison = json.loads((Path("outputs") / f"{league}_group_comparison_{tag}.json").read_text(encoding="utf-8"))
    base_sig = {c["comparison"]: c["p_value"] < 0.05 for c in base_comparison["comparisons"]}
    for min_pa in MIN_PA_VARIANTS:
        directory = out_root / f"min_pa_{min_pa}"
        directory.mkdir(parents=True, exist_ok=True)
        types_csv = directory / f"{league}_batter_types_{tag}.csv"
        joined = directory / f"{league}_decision_with_types_{tag}.csv"
        comparison = directory / f"{league}_group_comparison_{tag}.json"
        run([sys.executable, f"pipeline/{league}_analyze_batter_types.py", *base_args, "--min-pa", str(min_pa), "--output", str(types_csv)])
        run([sys.executable, "pipeline/join_decision_batter_types.py",
             "--decision-csv", f"outputs/{league}_decision_model_{tag}.csv", "--types-csv", str(types_csv), "--output", str(joined)])
        run([sys.executable, "pipeline/compare_groups.py", "--input", str(joined), "--output", str(comparison)])
        variant = json.loads(comparison.read_text(encoding="utf-8"))
        flips = [c["comparison"] for c in variant["comparisons"] if (c["p_value"] < 0.05) != base_sig.get(c["comparison"])]
        results["minPaVariants"][str(min_pa)] = {"significanceFlips": flips}
        print(f"min-pa={min_pa}: 顯著性翻轉的比較 {flips or '無'}", flush=True)

    path = Path("outputs") / f"{league}_hyperparameter_sensitivity_{tag}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"輸出：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
