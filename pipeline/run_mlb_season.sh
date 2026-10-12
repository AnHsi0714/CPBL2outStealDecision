#!/usr/bin/env bash
# 跑完一個 MLB 球季的下游分析（決策模型 mlb_model_batter_decisions.py 已跑完之後）。
# 用法：bash pipeline/run_mlb_season.sh 2025
#
# 通用腳本（join／compare_groups／team_decisions／bootstrap 等）原本只吃 CPBL 的
# {year}_{kind}_{start}-{end} 標籤並輸出 cpbl_ 前綴檔名；這裡一律先輸出到暫存目錄，再把
# cpbl_<名稱>_<year>_R_1-1 改名成 mlb_<名稱>_<日期標籤>，跟 mlb_ 並行腳本的檔名慣例一致。
set -euo pipefail
export PYTHONIOENCODING=utf-8

Y="$1"
S="$Y-03-15"; E="$Y-10-10"; TAG="${S}_${E}"
O=outputs
G="$O/_generic_mlb_$Y"
GT="${Y}_R_1-1"          # 通用腳本需要的假標籤，只用來產生檔名，輸出後立刻改名
mkdir -p "$G"

rename_generic() {
  local f base new
  for f in "$G"/cpbl_*; do
    [ -e "$f" ] || continue
    base=$(basename "$f")
    new="${base/cpbl_/mlb_}"
    new="${new/$GT/$TAG}"
    mv -f "$f" "$O/$new"
  done
}

echo "== [$Y] 打者類型（PA>=100）"
python pipeline/mlb_analyze_batter_types.py --start-date "$S" --end-date "$E"

echo "== [$Y] 決策貼上打者類型"
python pipeline/join_decision_batter_types.py \
  --decision-csv "$O/mlb_decision_model_$TAG.csv" \
  --types-csv "$O/mlb_batter_types_$TAG.csv" \
  --output "$O/mlb_decision_with_types_$TAG.csv"

echo "== [$Y] 先發／代打標記"
python pipeline/mlb_flag_lineup_substitutions.py --start-date "$S" --end-date "$E"

echo "== [$Y] 棒次 x 打者類型分組比較"
python pipeline/compare_groups.py \
  --input "$O/mlb_decision_with_starter_flag_$TAG.csv" \
  --output "$O/mlb_group_comparison_$TAG.json"

echo "== [$Y] 各隊決策品質"
python analysis/analyze_team_decisions.py --year "$Y" --kind-code R --start 1 --end 1 \
  --input "$O/mlb_decision_model_$TAG.csv" --output "$O/mlb_team_decisions_$TAG.json"

echo "== [$Y] 保留效應貢獻"
python analysis/analyze_retention_contribution.py --year "$Y" --kind-code R --start 1 --end 1 \
  --input "$O/mlb_decision_model_$TAG.csv" --output-dir "$G"
rename_generic

echo "== [$Y] 打者層級門檻 vs 打擊結果相關"
python analysis/analyze_batter_threshold_correlations.py --year "$Y" --kind-code R --start 1 --end 1 \
  --decision-csv "$O/mlb_decision_model_$TAG.csv" --profiles-csv "$O/mlb_batter_profiles_$TAG.csv" \
  --output-dir "$G"
rename_generic

echo "== [$Y] 門檻 bootstrap 信賴區間"
python analysis/bootstrap_threshold_ci.py --year "$Y" --kind-code R --start 1 --end 1 \
  --input "$O/mlb_decision_with_types_$TAG.csv" --output-dir "$G"
rename_generic

echo "== [$Y] 盜壘解析對帳（vs 官方 boxscore）"
python analysis/mlb_validate_steal_parsing.py --start-date "$S" --end-date "$E"

echo "== [$Y] 跑者名單（逐棒次門檻）"
python analysis/mlb_analyze_runner_steal_rates.py --start-date "$S" --end-date "$E"

echo "== [$Y] RE24 引擎驗證"
python re24/mlb_validate_re24_simulation.py --start-date "$S" --end-date "$E" --simulations 2000

echo "== [$Y] WPA 版門檻"
python wpa/mlb_model_wpa_decisions.py --start-date "$S" --end-date "$E"

echo "== [$Y] WPA 門檻 bootstrap 信賴區間"
python wpa/bootstrap_wpa_threshold_ci.py --year "$Y" --kind-code R --start 1 --end 1   --input "$O/mlb_wpa_decision_model_$TAG.csv" --output-dir "$G"
rename_generic

echo "== [$Y] RE 版「任一棒次都不建議跑」跑者換 WPA 門檻後翻盤數"
python wpa/analyze_wpa_runner_reclassification.py --year "$Y" --kind-code R --start 1 --end 1   --runner-csv "$O/mlb_runner_steal_rates_$TAG.csv" --wpa-bootstrap-json "$O/mlb_wpa_bootstrap_ci_$TAG.json"   --output-dir "$G"
rename_generic

echo "== [$Y] 棒次 x 打者類型分組換 WPA 重算"
python wpa/compare_wpa_groups.py --year "$Y" --kind-code R --start 1 --end 1   --types-csv "$O/mlb_decision_with_types_$TAG.csv" --wpa-csv "$O/mlb_wpa_decision_model_$TAG.csv"   --output-dir "$G"
rename_generic

echo "== [$Y] 決策報告 HTML"
python pipeline/mlb_generate_decision_report.py --start-date "$S" --end-date "$E"   --output "reports/mlb-steal-decision-$Y.html"
python league_relabel.py "reports/mlb-steal-decision-$Y.html" mlb "$Y"

rmdir "$G" 2>/dev/null || true
echo "== [$Y] 完成"
