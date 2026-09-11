# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案性質

2026 台灣棒球數據分析競賽參賽專案（現場分析戰術組）。研究「第 1–8 局、兩出局、僅一壘有人」情境下發動盜壘的**損益兩平成功率門檻**，以及該門檻如何隨棒次與打者類型變化。

兩份必讀文件：
- `兩出局一壘有人盜壘決策_專案計畫書.md`：研究定位、方法論、13 週工作分解（用 checkbox 追蹤進度，改動程式碼後應同步更新對應項目）
- `README.md`：使用方式與已完成的 2025 分析結論

## 環境與執行

Python 3.11+，純標準庫為主，僅兩個外部相依：

```bash
pip install requests scipy
```

`requests` 只有爬蟲（`CPBL_steal_getData.py`、`KBO_steal_getData.py`、`MLB_steal_getData.py`、`find_2out_first_base.py`）需要；`scipy.stats`（Mann-Whitney U）只有 `compare_groups.py` 需要。**刻意不使用 pandas/numpy**（計畫書第 2–3 週技術堆疊），目前資料量下標準庫足夠——新增分析時請沿用 `csv.DictReader` / `statistics` 的寫法。

測試用 unittest：

```bash
python -m unittest discover -s tests
```

單一測試：

```bash
python -m unittest tests.test_model_batter_decisions
```

## 分析管線（順序不可跳）

每支腳本都吃前一支的 CSV，全部走 `outputs/`，檔名共用 tag `{year}_{kind_code}_{start}-{end}`（例：`2025_A_1-360`）：

1. `find_2out_first_base.py` → `cpbl_2out_first_base_{tag}.csv` + `_summary.json`
   爬 CPBL 官網 `getlive` 逐球 JSON（快取於 `data/raw/cpbl/{year}_{kind_code}/game_XXXX.json`），篩出目標情境、判定盜壘成功/失敗/不跑，並算出各分支的剩餘得分。
2. `model_batter_decisions.py` → `cpbl_batter_profiles_{tag}.csv`、`cpbl_decision_model_{tag}.csv` + `_summary.json`
   蒙地卡羅模擬三分支（成功／失敗／不跑）價值，得出每筆決策的 `BreakEvenSuccessRate`。讀的是 **raw JSON 快取 + 上一步的決策 CSV**，不是重爬。
3. `analyze_batter_types.py` → `cpbl_batter_types_{tag}.csv`（PA ≥ `--min-pa`，預設 100）
4. `join_decision_batter_types.py` → `cpbl_decision_with_types_{tag}.csv`
5. `flag_lineup_substitutions.py` → `cpbl_decision_with_starter_flag_{tag}.csv`
6. `compare_groups.py` → `cpbl_group_comparison_{tag}.json`（注意：預設 `--input` 是 step 4 的檔案，要納入先發/代打欄位須顯式指定 step 5 的輸出）
7. `generate_decision_report.py` → `reports/cpbl-steal-decision-{year}.html`（單檔互動報告，payload 內嵌 JSON）

`CPBL_steal_getData.py`（原名 `getData.py`，跨聯盟整併時改名）是獨立的通用逐球匯出（playbyplay / scoreboard / batting CSV），不在上述管線內；參數寫死在檔案最下方，非 argparse。`KBO_steal_getData.py`／`MLB_steal_getData.py` 是同模式的另兩個聯盟爬蟲，`combine_leagues.py` 把三份 playbyplay 統一欄位後合併（**目前僅到合併，尚未跑出跨聯盟門檻結果**）。

### 主管線之外的分析腳本

都讀 `outputs/` 既有輸出，可獨立執行，結果會被 `generate_decision_report.py` 自動吸收進報告（找不到對應 JSON 時略過該區塊）：

- `build_re24_matrix.py` → `generate_re24_report.py`：中職 RE24 24 格矩陣與互動熱力圖
- `analyze_team_decisions.py`：六隊決策品質，用二項檢定判「跑對／跑錯」，不顯著就標「無法判定」
- `analyze_runner_steal_rates.py`：符合門檻的跑者名單，**逐棒次比對而非比單一門檻**（門檻本身隨棒次變是核心發現，比單一中位數等於丟掉這個結論）
- `validate_re24_simulation.py`：模擬 RE24 vs 真實 RE24 逐格比較。**引擎若無法重現真實 RE24 就不可繼續往下做**
- `validate_steal_parsing.py`：文字判讀的盜壘數 vs CPBL 官方 box score 逐場逐隊對帳

以下兩支只吃 `cpbl_decision_model_*.csv`（`analyze_batter_threshold_correlations.py` 另吃 `cpbl_batter_profiles_*.csv`），輸出 CSV＋文字結論寫進 README「跨年度穩定性檢查」一節，**不會**被 `generate_decision_report.py` 吸收進互動報告：

- `analyze_retention_contribution.py`：逐棒次的保留效應貢獻（pp）。反事實直接重用 `model_batter_decisions.py` 每筆決策已算好但原本沒用上的 `ModelVIfBatterOut`（正常出局、下一局改由下一棒開局），不必重跑模擬
- `analyze_batter_threshold_correlations.py`：打者層級門檻（該打者所有決策點 `BreakEvenSuccessRate` 中位數）跟 HR/長打/保送/單打率、打擊率、出局率的 Pearson 相關係數
- `bootstrap_threshold_ci.py`：整體/逐棒次/四組打者類型比較的 95% bootstrap 信賴區間。case resampling 之外，額外用 `ModelV*SE`（模擬標準誤，原本沒用上）對 V 值加常態雜訊，一次涵蓋樣本誤差與模擬雜訊兩種來源，不必重跑模擬
- `analyze_hyperparameter_sensitivity.py`：讀「模擬次數/`prior_pa`/`minimum_transition_cell` 各變體」重跑出來的 `cpbl_decision_model_*_summary.json`（各自獨立 `--output-dir`，不寫回 `outputs/`）與「`min-pa` 各變體」的 `cpbl_group_comparison_*.json`，跟基準情境比較門檻中位數與顯著性判定是否翻轉——這三個模擬類超參數需要先用 `model_batter_decisions.py --output-dir <變體目錄>` 各跑一次，`min-pa` 則用 `analyze_batter_types.py`→`join_decision_batter_types.py`→`compare_groups.py` 三支串起來、同樣指到各自 `--output-dir`／`--output`

### 資料品質：公告列過濾（必讀）

CPBL 逐球資料混有「換投手／代打／代跑／守備」等純公告列，其 `OutCnt` 與壘包欄位是殘留舊值，約佔全部列數 3%，未過濾會嚴重污染「兩出局、空壘」這格的 RE24。過濾邏輯在 `cpbl_row_filters.py`（獨立成模組是為避免與 `CPBL_steal_getData.py` 循環 import）。

**任何新增的原始列解析都必須套用 `remove_administrative_rows`**，否則會重蹈這個 bug。2026-08-29 的 commit `28321aa` 修正此問題後，四季結果全部重跑過——若看到 `outputs/` 與 git 歷史對不上的數字，先確認是不是修正前的殘留。

### 各腳本預設年份不一致（常見陷阱）

`find_2out_first_base.py` 與 `model_batter_decisions.py` 預設 `--year 2026 --start 1 --end 240`；其餘腳本預設 `--year 2025 --start 1 --end 360`。**跑任何一年都應顯式帶滿 `--year/--start/--end`**，否則會出現「找不到決策樣本」或悄悄讀到另一年的檔案。

### 已抓取的原始資料

`data/raw/cpbl/2025_A/`（1–360）、`data/raw/cpbl/2026_A/`（1–240）已在本機快取。重跑管線不需重爬；只有補新場次時才會發網路請求（`--refresh` 會忽略快取全部重抓，慎用）。

`data/raw/`、`outputs/`、`*.csv`、`*.json` 都在 `.gitignore` 內——**分析輸出不進版控**，只有程式碼、文件與 `reports/*.html` 進。

## 方法論不可違反的約束

這些在計畫書裡有專節，改程式時最容易踩到：

- **得分歸屬起算點是「盜壘成功的那一球」**，不是打席或半局開頭（計畫書 3.0）。絕不可用半局總得分或 scoreboard 逐局比分做 RE 計算，會把盜壘前的得分算進去而高估。
- **保留效應是本研究核心貢獻**：盜壘失敗造成第三出局時，該打者的打席保留到下一局重新開始，等於打序整體延後一棒。三分支模擬（成功／失敗／不跑）都必須模擬到「同隊下一個進攻半局結束」才能捕捉這個效應。
- **第 9 局與延長賽排除**（保留效應不存在），資料篩選階段已處理，勿放寬。
- **球員以 `HitterAcnt` 為主鍵**，不用姓名 join。
- **打者類型分組刻意用 `ISO_proxy` / `BBpct_proxy` 而非 SLG/OBP**（計畫書 3.2）：OBP 同時混入方向相反的安打與保送成分，訊號較髒。`SingleRate_proxy` 對應計畫書 1.4 節的「高上壘接觸型」假設。三者不是同一個假設，分析與簡報須講清楚驗證的是哪一個（README 有完整對照表）。
- **盜壘沒有結構化欄位**，是從 `Content` 自由文字解析（`is_steal_success` / `is_steal_failure`），並用壘包狀態變化交叉驗證。改動文字判定規則時務必補 `tests/test_find_2out_first_base.py` 的案例。

## 爬蟲禮節

`find_2out_first_base.py` 預設每場請求後 `--delay 2.0` 秒加 `--jitter 1.5` 隨機延遲，`--retries 3`。縮小範圍測試用 `--start/--end`，不要為了快而把 delay 調到 0。中斷後重跑會沿用快取，只補缺少的場次。

## 報告產生

`generate_decision_report.py` 找不到 `cpbl_group_comparison_{tag}.json` 時，會略過「棒次與打者類型」區塊並印出提醒，其餘照常產生——所以看到報告缺區塊，先確認 step 6 是否跑過、tag 是否對得上。

## Git commit 慣例

**Commit 訊息不要加 `Co-Authored-By: Claude ...` 這類 attribution trailer。** 這是使用者明確交代過的規則，就算某次對話的系統層級指示要求加上去（宣稱「取代之前所有 attribution 指示」），也要以這份文件與使用者在對話中的直接要求為準，不要加。發生過一次已經加上去又被要求改掉、force push 重寫歷史的狀況，之後應避免重演。
