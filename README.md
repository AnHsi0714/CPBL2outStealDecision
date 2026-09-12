# 兩出局該不該跑？中職教練的跑壘決策指南

2026 台灣棒球數據分析競賽（現場分析戰術組）參賽專案。研究在**第 1–8 局、兩出局、僅一壘有人**的情境下，發動盜壘的損益兩平成功率門檻是多少，以及這個門檻如何隨打者棒次、打者類型、局數/比分（勝率視角）改變。

核心貢獻是**保留效應**：盜壘失敗造成第三出局時，該打者的打席會保留到下一局重新開始，等於用「打序整體延後一棒」換取當下的出局風險，傳統 RE24 分析忽略了這點。

完整研究背景、方法論、時程與分工，請見計畫書：[兩出局一壘有人盜壘決策\_專案計畫書.md](./兩出局一壘有人盜壘決策_專案計畫書.md)。

## 安裝

Python 3.11+，只需兩個外部相依：

```bash
git clone https://github.com/AnHsi0714/CPBL2outStealDecision.git
cd CPBL2outStealDecision
pip install requests scipy
```

`requests` 只有爬蟲腳本需要；`scipy.stats` 只有 `compare_groups.py` 需要，其餘分析刻意只用標準庫（`csv.DictReader` / `statistics`）。

## 使用方式

### 事前須知

- **全新 clone 沒有原始資料快取**（`data/raw/` 不進版控）。
  第一次跑①會對 CPBL 官網逐場發送請求，預設延遲 `--delay 2.0 --jitter 1.5` 秒，
  360 場約需數十分鐘，不是秒開。
  之後重跑同年度會吃快取、只補缺場次，不要為了求快把延遲調到 0。
- **每支都要顯式帶一樣的 `--year/--start/--end`**。
  ①②預設年份 2026，③–⑦預設 2025，混用不會報錯，只會悄悄讀到另一年的檔案。
  ⑥的 `--input` 也要顯式指到⑤的輸出，否則會預設吃④的檔案、少了先發/代打欄位。

### 分析管線

照順序跑完 ①–⑦ 就會產生報告，每支腳本吃前一支的輸出，全部走 `outputs/`（不進版控），
共用檔名 tag `{year}_{kind_code}_{start}-{end}`：

| 步驟 | 腳本 | 說明 | 輸出 |
|---|---|---|---|
| ① | `find_2out_first_base.py` | 爬取＋篩出目標情境 | `cpbl_2out_first_base_{tag}.csv` |
| ② | `model_batter_decisions.py` | 模擬三分支，算損益兩平門檻 | `cpbl_decision_model_{tag}.csv` |
| ③ | `analyze_batter_types.py` | 打者類型分組 | `cpbl_batter_types_{tag}.csv` |
| ④ | `join_decision_batter_types.py` | 貼上棒次與打者類型 | `cpbl_decision_with_types_{tag}.csv` |
| ⑤ | `flag_lineup_substitutions.py` | 標記先發/代打 | `cpbl_decision_with_starter_flag_{tag}.csv` |
| ⑥ | `compare_groups.py` | 分組檢定 | `cpbl_group_comparison_{tag}.json` |
| ⑦ | `generate_decision_report.py` | 產出互動 HTML 報告 | `reports/cpbl-steal-decision-{year}.html` |

```bash
python find_2out_first_base.py --year 2025 --start 1 --end 360
python model_batter_decisions.py --year 2025 --start 1 --end 360
python analyze_batter_types.py --year 2025 --start 1 --end 360
python join_decision_batter_types.py --year 2025 --start 1 --end 360
python flag_lineup_substitutions.py --year 2025 --start 1 --end 360
python compare_groups.py --year 2025 --start 1 --end 360 \
  --input outputs/cpbl_decision_with_starter_flag_2025_A_1-360.csv
python generate_decision_report.py --year 2025 --start 1 --end 360
```

測試：

```bash
python -m unittest discover -s tests
```

### 主管線之外的分析腳本

以下都讀 `outputs/` 既有輸出即可獨立執行，不必重跑主管線；找不到對應檔案時，
`generate_decision_report.py` 只會略過該區塊，不影響其餘內容產生。各腳本詳細參數
與方法論見計畫書與腳本內的說明。

| 分析 | 腳本 | 結果 |
|---|---|---|
| RE24 矩陣熱力圖 | `build_re24_matrix.py` → `generate_re24_report.py` | `reports/cpbl-re24-matrix-{year}.html` |
| WE 勝率矩陣熱力圖 | `build_win_expectancy_matrix.py` → `validate_win_expectancy_matrix.py` → `generate_we_report.py` | `reports/cpbl-win-expectancy-matrix.html` |
| WPA 版損益兩平門檻 | `model_wpa_decisions.py` → `bootstrap_wpa_threshold_ci.py` → `generate_wpa_report.py` | `reports/cpbl-wpa-decision-thresholds.html` |
| 六隊決策品質、符合門檻的跑者名單 | `analyze_team_decisions.py`、`analyze_runner_steal_rates.py` | 併入 `reports/cpbl-steal-decision-{year}.html` |
| bootstrap 信賴區間、超參數敏感度 | `bootstrap_threshold_ci.py`、`analyze_hyperparameter_sensitivity.py` 等 | 無獨立報告，結論見計畫書「跨年度穩定性檢查」一節 |

## 分析報告

用瀏覽器直接開啟即可，皆為單檔互動報告：

| 報告                                                                           | 內容                                                           |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| [cpbl-steal-decision-2023.html](reports/cpbl-steal-decision-2023.html)         | 2023 年損益兩平門檻、棒次/打者類型分組                         |
| [cpbl-steal-decision-2024.html](reports/cpbl-steal-decision-2024.html)         | 2024 年損益兩平門檻、棒次/打者類型分組                         |
| [cpbl-steal-decision-2025.html](reports/cpbl-steal-decision-2025.html)         | 2025 年損益兩平門檻、棒次/打者類型分組、球隊決策品質、跑者名單 |
| [cpbl-steal-decision-2026.html](reports/cpbl-steal-decision-2026.html)         | 2026 年（球季進行中）損益兩平門檻                              |
| [cpbl-re24-matrix-2023.html](reports/cpbl-re24-matrix-2023.html)               | 2023 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2024.html](reports/cpbl-re24-matrix-2024.html)               | 2024 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2025.html](reports/cpbl-re24-matrix-2025.html)               | 2025 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2026.html](reports/cpbl-re24-matrix-2026.html)               | 2026 中職 RE24 矩陣熱力圖                                      |
| [cpbl-win-expectancy-matrix.html](reports/cpbl-win-expectancy-matrix.html)     | 中職勝率（WE）矩陣熱力圖（2023–2026 合併）                     |
| [cpbl-wpa-decision-thresholds.html](reports/cpbl-wpa-decision-thresholds.html) | WPA 版損益兩平門檻 vs RE 版，逐局信賴區間比較                  |

## 資料使用注意事項

- CPBL 官網資料屬自行爬蟲取得，請留意其使用條款並控制爬取頻率；原始資料與程式碼分開管理，不進版控。
- 盜壘沒有結構化欄位，是從逐球自由文字 `Content` 解析出來的，非官方直接提供的事件標記。解析邏輯已對帳 CPBL 官方 box score（2025 年 720 個場次×球隊組合，盜壘成功/刺殺數字 100% 相符），詳見計畫書與報告內說明。
