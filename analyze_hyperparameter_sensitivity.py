"""模擬引擎超參數敏感度分析：模擬次數／prior_pa／minimum_transition_cell／min-pa。

計畫書第 7–8 週待辦「對模擬次數、最低打席數門檻（PA≥100）等超參數做敏感度分析」。
四個超參數各自只變動一個、其餘維持預設值（simulations=2000、prior_pa=50.0、
minimum_transition_cell=5、batter min-pa=100），跟基準情境（`outputs/` 既有輸出）
比較整體門檻中位數的變化；min-pa 額外比較合格打者人數與四組打者類型比較的
p 值是否翻轉顯著性。

依賴：先用 `--sensitivity-dir` 指定的目錄下，各參數變體已經跑過
`model_batter_decisions.py`（simulations/prior_pa/minimum_transition_cell 三組）
或 `analyze_batter_types.py` + `join_decision_batter_types.py` + `compare_groups.py`
（min-pa 一組），每組各自的 `--output-dir`／`--output` 都指到
`<sensitivity-dir>/<variant>/`，不寫回主要的 `outputs/`。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


SIMULATIONS_VARIANTS = [500, 1000, 4000]
PRIOR_PA_VARIANTS = [25, 100]
MIN_CELL_VARIANTS = [3, 10]
MIN_PA_VARIANTS = [50, 150]

BASELINE = {"simulations": 2000, "prior_pa": 50, "minimum_transition_cell": 5, "min_pa": 100}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025, 2026])
    parser.add_argument(
        "--year-ends",
        type=int,
        nargs="+",
        default=[300, 360, 360, 240],
        help="與 --years 一一對應的 --end 值",
    )
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--sensitivity-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    year_ends = dict(zip(args.years, args.year_ends))
    report: dict[str, Any] = {"years": {}}

    print(f"{'年度':>6} | {'參數':>24} | {'基準門檻':>8} | {'新門檻':>8} | {'差(pp)':>7}")
    for year in args.years:
        end = year_ends[year]
        tag = f"{year}_{args.kind_code}_1-{end}"
        year_report: dict[str, Any] = {}

        baseline_summary = load_json(Path("outputs") / f"cpbl_decision_model_{tag}_summary.json")
        baseline_median = baseline_summary["median_break_even_rate_in_0_1"] if baseline_summary else None
        year_report["baseline_median"] = baseline_median

        def show(label: str, value: float | None) -> None:
            if baseline_median is None or value is None:
                print(f"{year:>6} | {label:>24} | {'NA':>8} | {'NA':>8} | {'NA':>7}")
                return
            delta = (value - baseline_median) * 100
            print(
                f"{year:>6} | {label:>24} | {baseline_median*100:>7.2f}% |"
                f" {value*100:>7.2f}% | {delta:>+6.2f}"
            )

        simulations_results = {}
        for sims in SIMULATIONS_VARIANTS:
            summary = load_json(args.sensitivity_dir / f"sims{sims}" / f"cpbl_decision_model_{tag}_summary.json")
            value = summary["median_break_even_rate_in_0_1"] if summary else None
            simulations_results[sims] = value
            show(f"simulations={sims}", value)
        year_report["simulations"] = simulations_results

        prior_pa_results = {}
        for prior in PRIOR_PA_VARIANTS:
            summary = load_json(args.sensitivity_dir / f"priorpa{prior}" / f"cpbl_decision_model_{tag}_summary.json")
            value = summary["median_break_even_rate_in_0_1"] if summary else None
            prior_pa_results[prior] = value
            show(f"prior_pa={prior}", value)
        year_report["prior_pa"] = prior_pa_results

        min_cell_results = {}
        for cell in MIN_CELL_VARIANTS:
            summary = load_json(args.sensitivity_dir / f"mincell{cell}" / f"cpbl_decision_model_{tag}_summary.json")
            value = summary["median_break_even_rate_in_0_1"] if summary else None
            min_cell_results[cell] = value
            show(f"minimum_transition_cell={cell}", value)
        year_report["minimum_transition_cell"] = min_cell_results

        report["years"][str(year)] = year_report

    print("\n--- min-pa（合格打者門檻）：合格打者人數與四組打者類型比較 p 值 ---")
    baseline_comparison_by_year: dict[int, dict[str, Any]] = {}
    for year in args.years:
        end = year_ends[year]
        tag = f"{year}_{args.kind_code}_1-{end}"
        baseline_comparison_by_year[year] = load_json(Path("outputs") / f"cpbl_group_comparison_{tag}.json") or {}

    minpa_report: dict[str, Any] = {}
    for year in args.years:
        end = year_ends[year]
        tag = f"{year}_{args.kind_code}_1-{end}"
        baseline_comparison = baseline_comparison_by_year[year]
        baseline_qualified = baseline_comparison.get("batter_type_qualified_rows")
        baseline_p = {
            c["comparison"]: c.get("p_value")
            for c in baseline_comparison.get("comparisons", [])
        }
        print(f"\n{year}（基準 min-pa=100，合格決策列 {baseline_qualified}）")
        year_minpa: dict[str, Any] = {"baseline_qualified_rows": baseline_qualified, "variants": {}}
        for min_pa in MIN_PA_VARIANTS:
            comparison = load_json(args.sensitivity_dir / f"minpa{min_pa}" / f"cpbl_group_comparison_{tag}.json")
            if comparison is None:
                print(f"  min-pa={min_pa}：找不到輸出")
                continue
            qualified = comparison.get("batter_type_qualified_rows")
            print(f"  min-pa={min_pa}：合格決策列 {qualified}")
            variant_p = {}
            for c in comparison.get("comparisons", []):
                name = c["comparison"]
                p_new = c.get("p_value")
                p_base = baseline_p.get(name)
                flipped = (
                    p_new is not None and p_base is not None
                    and (p_new < 0.05) != (p_base < 0.05)
                )
                variant_p[name] = {"p_value": p_new, "baseline_p_value": p_base, "significance_flipped": flipped}
                flag = " ← 顯著性翻轉！" if flipped else ""
                p_new_str = f"{p_new:.3g}" if p_new is not None else "NA"
                p_base_str = f"{p_base:.3g}" if p_base is not None else "NA"
                print(f"    {name:<28} p={p_new_str:>10}（基準 p={p_base_str}）{flag}")
            year_minpa["variants"][str(min_pa)] = {"qualified_rows": qualified, "comparisons": variant_p}
        minpa_report[str(year)] = year_minpa

    report["min_pa"] = minpa_report

    output_path = args.output_dir / "cpbl_hyperparameter_sensitivity.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n輸出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
