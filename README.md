# 兩出局一壘有人，該不該跑？中職教練的跑壘決策指南

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

`requests` 只有爬蟲腳本需要；`scipy.stats` 只有 `pipeline/compare_groups.py` 需要，其餘分析刻意只用標準庫（`csv.DictReader` / `statistics`）。

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
| ① | `scrapers/find_2out_first_base.py` | 爬取＋篩出目標情境 | `cpbl_2out_first_base_{tag}.csv` |
| ② | `pipeline/model_batter_decisions.py` | 模擬三分支，算損益兩平門檻 | `cpbl_decision_model_{tag}.csv` |
| ③ | `pipeline/analyze_batter_types.py` | 打者類型分組 | `cpbl_batter_types_{tag}.csv` |
| ④ | `pipeline/join_decision_batter_types.py` | 貼上棒次與打者類型 | `cpbl_decision_with_types_{tag}.csv` |
| ⑤ | `pipeline/flag_lineup_substitutions.py` | 標記先發/代打 | `cpbl_decision_with_starter_flag_{tag}.csv` |
| ⑥ | `pipeline/compare_groups.py` | 分組檢定 | `cpbl_group_comparison_{tag}.json` |
| ⑦ | `pipeline/generate_decision_report.py` | 產出互動 HTML 報告 | `reports/cpbl-steal-decision-{year}.html` |

```bash
python scrapers/find_2out_first_base.py --year 2025 --start 1 --end 360
python pipeline/model_batter_decisions.py --year 2025 --start 1 --end 360
python pipeline/analyze_batter_types.py --year 2025 --start 1 --end 360
python pipeline/join_decision_batter_types.py --year 2025 --start 1 --end 360
python pipeline/flag_lineup_substitutions.py --year 2025 --start 1 --end 360
python pipeline/compare_groups.py --year 2025 --start 1 --end 360 \
  --input outputs/cpbl_decision_with_starter_flag_2025_A_1-360.csv
python pipeline/generate_decision_report.py --year 2025 --start 1 --end 360
```

測試：

```bash
python -m unittest discover -s tests
```

### 主管線之外的分析腳本

以下都讀 `outputs/` 既有輸出即可獨立執行，不必重跑主管線；找不到對應檔案時，
`pipeline/generate_decision_report.py` 只會略過該區塊，不影響其餘內容產生。各腳本詳細參數
見腳本內說明，完整結果數字見 [分析發現.md](./分析發現.md)。

| 分析 | 腳本 | 結果 |
|---|---|---|
| RE24 矩陣熱力圖 | `re24/build_re24_matrix.py` → `re24/generate_re24_report.py` | `reports/cpbl-re24-matrix-{year}.html` |
| WE 勝率矩陣熱力圖 | `win_expectancy/build_win_expectancy_matrix.py` → `win_expectancy/validate_win_expectancy_matrix.py` → `win_expectancy/generate_we_report.py` | `reports/cpbl-win-expectancy-matrix.html` |
| WPA 版損益兩平門檻 | `wpa/model_wpa_decisions.py` → `wpa/bootstrap_wpa_threshold_ci.py` → `wpa/generate_wpa_report.py` | `reports/cpbl-wpa-decision-thresholds.html` |
| 六隊決策品質、符合門檻的跑者名單 | `analysis/analyze_team_decisions.py`、`analysis/analyze_runner_steal_rates.py` | 併入 `reports/cpbl-steal-decision-{year}.html` |
| bootstrap 信賴區間、超參數敏感度 | `analysis/bootstrap_threshold_ci.py`、`analysis/analyze_hyperparameter_sensitivity.py` 等 | 無獨立報告，結論見 [分析發現.md](./分析發現.md) |
| 左右投對跑者的影響 | `analysis/analyze_pitcher_handedness.py` | `outputs/cpbl_runner_handedness_{tag}.csv`／`_summary.json` |

### 左右投對跑者的影響

`analysis/analyze_pitcher_handedness.py` 只回答一件事：**投手慣用手如何影響跑者盜二壘**。
左投面對一壘跑者是正面朝向，牽制視野好、起跑時機難抓。

**這影響的是跑者跑不跑得掉（實際成功率），不是門檻**：門檻由打者的打擊結果分布決定，
跟投手是誰無關。簡報上把「面對左投門檻要調高」跟「面對左投比較難跑」混為一談會被問倒，
正確說法是**門檻不動，是你達不達得到門檻在變**。

```bash
# 單季（逐跑者拆左右投後多數人樣本不足，主要看聯盟層級數字）
python analysis/analyze_pitcher_handedness.py --year 2025 --start 1 --end 360

# 合併四季（逐跑者名單用這個；門檻仍取 --year 指定球季）
python analysis/analyze_pitcher_handedness.py --year 2025 --start 1 --end 360 \
  --pool-years 2023,2024,2025,2026
```

範圍與 `analysis/analyze_runner_steal_rates.py` 一致（只算一壘跑者盜二壘，不含盜三壘、雙盜壘），
但**不限兩出局**：跑者能力與出局數無關，用全部一壘有人的球數才有足夠樣本做逐跑者拆分
（四季 2,228 次嘗試 vs 兩出局子集的 772 次）。慣用手來自 `data/player_handedness.csv`。

四季結果：

| 球季 | 對左投成功率 (n) | 對右投成功率 (n) | 差距 | p |
|---|---|---|---|---|
| 2023 | 60.2% (103) | 71.3% (432) | +11.1pp | 0.033 |
| 2024 | 66.5% (164) | 70.4% (419) | +3.9pp | 0.370 |
| 2025 | 58.6% (222) | 69.9% (459) | +11.4pp | 0.004 |
| 2026 | 62.9% (89) | 69.7% (340) | +6.8pp | 0.250 |
| **四季合計** | **61.8% (578)** | **70.4% (1650)** | **+8.6pp** | **0.00018** |

方向四季一致，合併後高度顯著；個別球季只有 2023、2025 顯著，因為每季每手別只有
89–222 次嘗試。**跑者幾乎沒有因應調整**：每球嘗試率對左投 1.57%、對右投 1.73%
（p=0.038），只收斂約 9%，遠不足以抵銷 8.6pp 的成功率落差。

把這個對上門檻（55–59%）就是直接的教練結論：**對右投跑，70.4% 遠高於門檻，划算；
對左投跑，61.8% 幾乎卡在門檻上，等於白忙。**

合併四季、左右投各 ≥5 次嘗試的 36 位跑者中，**11 位只建議對右投跑**
（對右投過門檻、對左投不過），例如李凱威（52.4% vs 73.8%）、王博玄（53.3% vs 79.1%）。
個別差異很大，邱智呈反而是對左投更好（88.2% vs 67.7%），不能一律假設左投必然不利。

附帶觀察：牽制投球率在 2026 明顯下降（左投 4.17%／右投 4.98%，前三季為 6.0–8.0%），
與 2026 牽制次數限制新規的方向一致。

## 分析報告

以下連結指向 GitHub Pages 線上版，點了直接看到渲染後的頁面（GitHub 檔案檢視預設只會顯示 HTML 原始碼，不會執行）。
本機 clone 後也可以直接用瀏覽器開同一份 `reports/*.html`，效果相同。

| 報告                                                                                                                       | 內容                                                           |
| --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| [cpbl-full-report.html（整合入口）](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-full-report.html)         | 單頁整合以下全部報告，上方分類＋年份頁籤切換                   |
| [cpbl-steal-decision-2023.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-steal-decision-2023.html)   | 2023 年損益兩平門檻、棒次/打者類型分組                         |
| [cpbl-steal-decision-2024.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-steal-decision-2024.html)   | 2024 年損益兩平門檻、棒次/打者類型分組                         |
| [cpbl-steal-decision-2025.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-steal-decision-2025.html)   | 2025 年損益兩平門檻、棒次/打者類型分組、球隊決策品質、跑者名單 |
| [cpbl-steal-decision-2026.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-steal-decision-2026.html)   | 2026 年（球季進行中）損益兩平門檻                              |
| [cpbl-re24-matrix-2023.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-re24-matrix-2023.html)         | 2023 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2024.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-re24-matrix-2024.html)         | 2024 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2025.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-re24-matrix-2025.html)         | 2025 中職 RE24 矩陣熱力圖                                      |
| [cpbl-re24-matrix-2026.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-re24-matrix-2026.html)         | 2026 中職 RE24 矩陣熱力圖                                      |
| [cpbl-win-expectancy-matrix.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-win-expectancy-matrix.html) | 中職勝率（WE）矩陣熱力圖（2023–2026 合併）                     |
| [cpbl-wpa-decision-thresholds.html](https://anhsi0714.github.io/CPBL2outStealDecision/reports/cpbl-wpa-decision-thresholds.html) | WPA 版損益兩平門檻 vs RE 版，逐局信賴區間比較                  |

## 資料使用注意事項

- CPBL 官網資料屬自行爬蟲取得，請留意其使用條款並控制爬取頻率；原始資料與程式碼分開管理，不進版控。
- 球員投打習慣（`data/player_handedness.csv`，497 人）取自 CPBL 官網球員頁的「投打習慣」欄位，逐球資料本身沒有這個欄位。這份對照表無法由逐球快取重建，因此是 `data/` 底下唯一進版控的檔案（`.gitignore` 有對應例外）。以 `Acnt` 為主鍵，不用姓名 join。
- 盜壘沒有結構化欄位，是從逐球自由文字 `Content` 解析出來的，非官方直接提供的事件標記。解析邏輯已對帳 CPBL 官方 box score（2025 年 720 個場次×球隊組合，盜壘成功/刺殺數字 100% 相符），詳見 [分析發現.md](./分析發現.md) 與報告內說明。
