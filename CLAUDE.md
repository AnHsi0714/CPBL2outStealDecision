# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案性質

2026 台灣棒球數據分析競賽參賽專案（現場分析戰術組）。研究「第 1–8 局、兩出局、僅一壘有人」情境下發動盜壘的**損益兩平成功率門檻**，以及該門檻如何隨棒次與打者類型變化。

四份必讀文件（`方法說明.md` 說明 RE24、蒙地卡羅、WE、WPA 各自的作用，改動模型前先看）：
- `兩出局一壘有人盜壘決策_專案計畫書.md`：研究定位、方法論、13 週工作分解（用 checkbox 追蹤進度）。**checkbox 項目只寫任務描述與一句話結論，不放完整數字**，改動程式碼後同步更新對應項目即可，不必補回數字
- `分析發現.md`：計畫書各項分析的完整數字、結論與方法細節。**新增或更新分析結果一律寫進這裡，不要寫回計畫書**，計畫書要留給評審看，太多數字會拖累可讀性
- `README.md`：專案簡介、安裝步驟、線上報告入口與文件導覽，不放分析數字
- `方法說明.md`：RE24、蒙地卡羅、WE、WPA 各自做什麼、如何串成門檻

## 程式碼目錄結構

腳本依功能分成 6 個資料夾，`templates/`、`tests/`、`data/`、`outputs/`、`reports/` 維持在根目錄不變：

- `scrapers/`：三個聯盟爬蟲、`find_2out_first_base.py`、`combine_leagues.py`、`cpbl_row_filters.py`
- `pipeline/`：主管線 step 2–7（`model_batter_decisions.py` 到 `generate_decision_report.py`）
- `re24/`、`win_expectancy/`、`wpa/`：對應同名分析區塊（見下方「主管線之外的分析腳本」）
- `analysis/`：主管線之外、不屬於上述三類的獨立分析／驗證腳本
- 根目錄：僅 `generate_all_leagues_report.py`（把 CPBL／MLB／KBO 的既有報告整合成單一入口 `reports/all-leagues-report.html`，右上角標籤切換聯盟；重用 `generate_full_report.py` 的分類掃描與 `templates/full_report.*`，不屬於單一功能分類）、`generate_full_report.py`、`league_relabel.py` 與本檔案、README 等文件

各資料夾內的腳本仍用原本扁平的 `from find_2out_first_base import x` 這類寫法互相 import，**不是** Python package（沒有 `__init__.py` 賦予的套件語意）。能這樣運作是因為根目錄的 `pathsetup.py` 會把六個資料夾都加進 `sys.path`；每支被搬動過的腳本與 `tests/` 下的測試檔開頭都有一行 `import pathsetup` 觸發這件事。**新增腳本或測試檔時比照既有檔案在檔案最前面（`from __future__ import annotations` 之後、其餘 import 之前）加上同一行**，否則 cross-folder import 會找不到模組。執行方式不變，一律 `python <資料夾>/<script>.py --參數`（例如 `python pipeline/model_batter_decisions.py ...`），不要用 `python -m`。

## 環境與執行

Python 3.11+，純標準庫為主，僅兩個外部相依：

```bash
pip install requests scipy
```

`requests` 只有爬蟲（`scrapers/CPBL_steal_getData.py`、`scrapers/KBO_steal_getData.py`、`scrapers/MLB_steal_getData.py`、`scrapers/find_2out_first_base.py`）需要；`scipy.stats`（Mann-Whitney U）只有 `pipeline/compare_groups.py` 需要。**刻意不使用 pandas/numpy**（計畫書第 2–3 週技術堆疊），目前資料量下標準庫足夠；新增分析時請沿用 `csv.DictReader` / `statistics` 的寫法。

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

1. `scrapers/find_2out_first_base.py` → `cpbl_2out_first_base_{tag}.csv` + `_summary.json`
   爬 CPBL 官網 `getlive` 逐球 JSON（快取於 `data/raw/cpbl/{year}_{kind_code}/game_XXXX.json`），篩出目標情境、判定盜壘成功/失敗/不跑，並算出各分支的剩餘得分。
2. `pipeline/model_batter_decisions.py` → `cpbl_batter_profiles_{tag}.csv`、`cpbl_decision_model_{tag}.csv` + `_summary.json`
   蒙地卡羅模擬三分支（成功／失敗／不跑）價值，得出每筆決策的 `BreakEvenSuccessRate`。讀的是 **raw JSON 快取 + 上一步的決策 CSV**，不是重爬。
3. `pipeline/analyze_batter_types.py` → `cpbl_batter_types_{tag}.csv`（PA ≥ `--min-pa`，預設 100）
4. `pipeline/join_decision_batter_types.py` → `cpbl_decision_with_types_{tag}.csv`
5. `pipeline/flag_lineup_substitutions.py` → `cpbl_decision_with_starter_flag_{tag}.csv`
6. `pipeline/compare_groups.py` → `cpbl_group_comparison_{tag}.json`（注意：預設 `--input` 是 step 4 的檔案，要納入先發/代打欄位須顯式指定 step 5 的輸出）
7. `pipeline/generate_decision_report.py` → `reports/cpbl-steal-decision-{year}.html`（單檔互動報告，payload 內嵌 JSON）

完整指令範例（以 2025 為例，各步驟都帶滿 `--year/--start/--end`）：

```bash
python scrapers/find_2out_first_base.py --year 2025 --start 1 --end 360
python pipeline/model_batter_decisions.py --year 2025 --start 1 --end 360
python pipeline/analyze_batter_types.py --year 2025 --start 1 --end 360
python pipeline/join_decision_batter_types.py --year 2025 --start 1 --end 360
python pipeline/flag_lineup_substitutions.py --year 2025 --start 1 --end 360
python pipeline/compare_groups.py --year 2025 --start 1 --end 360   --input outputs/cpbl_decision_with_starter_flag_2025_A_1-360.csv
python pipeline/generate_decision_report.py --year 2025 --start 1 --end 360
```

全新 clone 沒有原始資料快取（`data/raw/` 不進版控），第一次跑步驟 1 會逐場請求 CPBL 官網，360 場約需數十分鐘。

`scrapers/CPBL_steal_getData.py`（原名 `getData.py`，跨聯盟整併時改名）是獨立的通用逐球匯出（playbyplay / scoreboard / batting CSV），不在上述管線內；參數寫死在檔案最下方，非 argparse。`scrapers/KBO_steal_getData.py`／`scrapers/MLB_steal_getData.py` 是同模式的另兩個聯盟爬蟲，`scrapers/combine_leagues.py` 把三份 playbyplay 統一欄位後合併（合併檔本身沒有往下用；MLB／KBO 的門檻結果是走各自的並行管線跑出來的，見下方「跨聯盟（MLB／KBO）並行腳本」）。

### 主管線之外的分析腳本

都讀 `outputs/` 既有輸出，可獨立執行，結果會被 `pipeline/generate_decision_report.py` 自動吸收進報告（找不到對應 JSON 時略過該區塊）：

- `re24/build_re24_matrix.py` → `re24/generate_re24_report.py`：中職 RE24 24 格矩陣與互動熱力圖
- `win_expectancy/build_win_expectancy_matrix.py` → `win_expectancy/validate_win_expectancy_matrix.py` → `win_expectancy/generate_we_report.py`：中職 WE（勝率增值）矩陣：(局數桶 1-6/7/8/9+ × 攻守方 × 分差桶 ±5 × 出局數 × 壘包) → 進攻方最終獲勝機率，全部從逐球紀錄推回最終比分（不查 box score 總分欄位）。跟 RE24 不同，預設一次合併四季（`--seasons` 可覆寫），因為格子數（2112）遠多於 RE24 的 24 格；validate 腳本做單調性與目標情境（2 出局、一/二壘有人、第 7–8 局）涵蓋度檢查，因為沒有獨立模擬引擎可對照
- `wpa/model_wpa_decisions.py` → `wpa/bootstrap_wpa_threshold_ci.py` → `wpa/generate_wpa_report.py`（`reports/cpbl-wpa-decision-thresholds.html`，四季逐局信賴區間比較圖）：把 WE 矩陣接回三分支模型算 WPA 版損益兩平門檻。V成功／V失敗直接查 WE 表（WE 每格本來就是「這個狀態到比賽結束」的經驗值，不必再模擬），V不跑用打者個人機率分布做「一步」蒙地卡羅落到新狀態後查表：關鍵是 V失敗必須換算成**對手視角**（`1 - WE(對手下一次進攻)`），RE 版模型完全沒有這個機制（RE 版失敗分支只模擬「自己隊下一次進攻」，因為 RE 不是零和的）。門檻是比值，分母很小時對雜訊極敏感，所以 bootstrap 腳本對每筆決策的三個 V 值各自用其標準誤（WE 格子二項標準誤＋一步模擬標準誤）加雜訊再 case resampling，算 95% CI。`wpa/analyze_wpa_runner_reclassification.py` 把門檻接回實際跑者名單，`wpa/compare_wpa_groups.py` 把棒次×打者類型分組換成 WPA 重算。**四季結果與完整數字見 `分析發現.md`**
- `analysis/analyze_team_decisions.py`：六隊決策品質，用二項檢定判「跑對／跑錯」，不顯著就標「無法判定」
- `analysis/analyze_runner_steal_rates.py`：符合門檻的跑者名單，**逐棒次比對而非比單一門檻**（門檻本身隨棒次變是核心發現，比單一中位數等於丟掉這個結論）
- `re24/validate_re24_simulation.py`：模擬 RE24 vs 真實 RE24 逐格比較。**引擎若無法重現真實 RE24 就不可繼續往下做**
- `analysis/validate_steal_parsing.py`：文字判讀的盜壘數 vs CPBL 官方 box score 逐場逐隊對帳。**四季 2,760 個（場次,球隊）組合全部 0 筆不符。** 達到這個結果補過兩個樣式缺口：單獨盜本壘「三壘跑者X 盜壘回本壘得分」（原本只認「雙盜壘回本壘得分」，四季僅 1 筆，2026 第 106 場）與未標壘包的盜壘刺「跑者X出局-盜壘刺」（三振＋盜壘刺雙殺，四季僅 1 筆，2023 第 35 場）。注意 `scrapers/find_2out_first_base.py` 的 `is_steal_failure` **刻意不跟著放寬**：研究範圍只取一壘跑者，沒標壘包的無法確認是哪一壘，保守排除才正確
- `analysis/analyze_pitcher_handedness.py`：**左右投對跑者**的影響。只看投手慣用手如何改變跑者盜二壘的實際成功率，**不涉及打者**。加 `--pool-years 2023,2024,2025,2026` 合併四季做逐跑者拆分（單季拆完多數跑者樣本不足）

### 左右投：必須分清楚的兩件事

- **投手慣用手影響的是「跑不跑得掉」（實際成功率），不是門檻。** 門檻由打者的打擊結果分布決定，模型裡完全沒有用到投手。所以把現有結果按投手左右投分兩堆比較，門檻會幾乎一樣，那是算法造成的，不是真的沒差異。
- 若真要讓門檻隨投手變，必須把打者成績依對戰關係分開建檔，而且**platoon 效應是「打者手 × 投手手」的對戰關係，不是投手手別本身**：把所有打者合起來看「對左投的成績」，右打者（逆向有利）與左打者（同手不利）會互相抵銷，得到「幾乎沒差異」的假結論。這條路因樣本不足（要湊 100 個對左投打席需全年 400 打席，四季只有 17/22/15/0 位打者達標）目前未採用。

以下兩支只吃 `cpbl_decision_model_*.csv`（`analysis/analyze_batter_threshold_correlations.py` 另吃 `cpbl_batter_profiles_*.csv`），輸出 CSV＋文字結論寫進 `分析發現.md`，**不會**被 `pipeline/generate_decision_report.py` 吸收進互動報告：

- `analysis/analyze_retention_contribution.py`：逐棒次的保留效應貢獻（pp）。反事實直接重用 `pipeline/model_batter_decisions.py` 每筆決策已算好但原本沒用上的 `ModelVIfBatterOut`（正常出局、下一局改由下一棒開局），不必重跑模擬
- `analysis/analyze_batter_threshold_correlations.py`：打者層級門檻（該打者所有決策點 `BreakEvenSuccessRate` 中位數）跟 HR/長打/保送/單打率、打擊率、出局率的 Pearson 相關係數
- `analysis/bootstrap_threshold_ci.py`：整體/逐棒次/四組打者類型比較的 95% bootstrap 信賴區間。case resampling 之外，額外用 `ModelV*SE`（模擬標準誤，原本沒用上）對 V 值加常態雜訊，一次涵蓋樣本誤差與模擬雜訊兩種來源，不必重跑模擬
- `analysis/analyze_hyperparameter_sensitivity.py`：讀「模擬次數/`prior_pa`/`minimum_transition_cell` 各變體」重跑出來的 `cpbl_decision_model_*_summary.json`（各自獨立 `--output-dir`，不寫回 `outputs/`）與「`min-pa` 各變體」的 `cpbl_group_comparison_*.json`，跟基準情境比較門檻中位數與顯著性判定是否翻轉；這三個模擬類超參數需要先用 `pipeline/model_batter_decisions.py --output-dir <變體目錄>` 各跑一次，`min-pa` 則用 `pipeline/analyze_batter_types.py`→`pipeline/join_decision_batter_types.py`→`pipeline/compare_groups.py` 三支串起來、同樣指到各自 `--output-dir`／`--output`

### 跨聯盟（MLB／KBO）並行腳本

MLB、KBO 沿用 `mlb_`／`kbo_` 前綴的並行腳本，數學部分（模擬引擎、分組比較、保留效應、bootstrap 等）直接 import CPBL 版，只換資料來源；**不改 CPBL 腳本**。結果與數字見 `分析發現.md` 的「跨聯盟擴充」，過程與每個 bug 見 `跨聯盟擴充進度.md`。

- MLB：`scrapers/mlb_find_2out_first_base.py`（Gumbo 快取 `data/raw/mlb/{start}_{end}/`）→ `pipeline/mlb_model_batter_decisions.py` → `bash pipeline/run_mlb_season.sh <年>`（類型、join、先發標記、分組比較、各隊決策、保留效應、WPA、跑者名單、決策報告一次跑完）。檔名標籤是日期區間 `YYYY-03-15_YYYY-10-10`。
- KBO：`scrapers/KBO_crawl_seasons.py`（HTML 快取 `data/raw/kbo/{年}/`）→ `scrapers/kbo_find_2out_first_base.py` → `pipeline/kbo_model_batter_decisions.py` → `bash pipeline/run_kbo_season.sh <年>`。檔名標籤是年份。
- RE24／WE：`re24/{mlb,kbo}_build_re24_matrix.py`、`re24/{mlb,kbo}_validate_re24_simulation.py`、`win_expectancy/{mlb,kbo}_build_win_expectancy_matrix.py`（四季合併）。**引擎驗證（模擬 RE24 對真實 RE24）是 MLB／KBO 解析正確性的檢查點**，每次動解析邏輯後都要重跑。
- 報告：決策／RE24／WE 報告用 CPBL 版產生器產出後以 `league_relabel.py` 換標籤；WPA 報告用 `wpa/generate_league_wpa_report.py`（CPBL 版模板寫死 CPBL 結論，不可直接換標籤）；入口頁只有 `reports/all-leagues-report.html`（`python generate_all_leagues_report.py` 產生），不再有各聯盟自己的 `*-full-report.html`。
- 通用腳本（`join_decision_batter_types.py`、`compare_groups.py`、`analyze_team_decisions.py` 等）只吃 CPBL 的 `{year}_{kind}_{start}-{end}` 標籤、輸出 `cpbl_` 檔名；`run_*_season.sh` 會輸出到暫存目錄再改名成 `mlb_`／`kbo_`，不要直接對它們傳 MLB／KBO 檔案後留在 `outputs/`。

必須知道的陷阱：

- **MLB**：`playEvents[].count.outs` 對投球事件是事件前、對非投球事件（牽制盜壘）是事件後，出局數一律用 `runners[].movement.isOut` 逐事件累加；盜壘標記在投球事件上時只出現在 `runners[].details.event`；半局第一個打席的得分要數 `runners[]` 的 `end=="score"`，不能用比分相減；延長賽第 10 局起二壘有人（placed runner）；延期賽在 schedule 裡會出現兩次（用 gamePk 去重）。
- **KBO**：沒有比分、沒有球員 ID（主鍵 `球隊:姓名`）；三振同時阻殺（打者出局列之後接跑者阻殺列）不是兩出局決策；狀態機的殘餘誤差使 RE24 驗證 r 只有 0.98。
- **記憶體**：MLB 單季模型載入全部 Gumbo JSON 約 6GB，同時跑超過 2 個季會把 32GB 吃光。

### 資料品質：公告列過濾（必讀）

CPBL 逐球資料混有「換投手／代打／代跑／守備」等純公告列，其 `OutCnt` 與壘包欄位是殘留舊值，約佔全部列數 3%，未過濾會嚴重污染「兩出局、空壘」這格的 RE24。過濾邏輯在 `scrapers/cpbl_row_filters.py`（獨立成模組是為避免與 `scrapers/CPBL_steal_getData.py` 循環 import）。

**所有球季的檔名 tag 一律用 `1-360`**（含 2023，雖然該季只有 300 場）：`find_2out_first_base.py` 當初以排程範圍命名，核心產出都是 `2023_A_1-360`。曾有幾支腳本寫死 `2023:A:1:300`／`2026:A:1:240`，導致找不到決策 CSV 或只讀半季，已全部統一為 360。實際場次數看 summary 的 `games_processed`。

**任何新增的原始列解析都必須套用 `remove_administrative_rows`**，否則會重蹈這個 bug。2026-08-29 的 commit `28321aa` 修正此問題後，四季結果全部重跑過；若看到 `outputs/` 與 git 歷史對不上的數字，先確認是不是修正前的殘留。

### 各腳本預設年份不一致（常見陷阱）

`scrapers/find_2out_first_base.py` 與 `pipeline/model_batter_decisions.py` 預設 `--year 2026 --start 1 --end 360`；其餘腳本預設 `--year 2025 --start 1 --end 360`。年份仍不一致，場次範圍已統一為 360。**跑任何一年都應顯式帶滿 `--year/--start/--end`**，否則會出現「找不到決策樣本」或悄悄讀到另一年的檔案。

### 已抓取的原始資料

四季原始資料均已在本機快取：`2023_A`（300 場，五隊制）、`2024_A`／`2025_A`／`2026_A`（各 360 場）。2026 例行賽已打完，四季皆為完整球季。重跑管線不需重爬；只有補新場次時才會發網路請求（`--refresh` 會忽略快取全部重抓，慎用）。

`data/raw/`、`outputs/`、`*.csv`、`*.json` 都在 `.gitignore` 內：**分析輸出不進版控**，只有程式碼、文件與 `reports/*.html` 進。

## 方法論不可違反的約束

這些在計畫書裡有專節，改程式時最容易踩到：

- **得分歸屬起算點是「盜壘成功的那一球」**，不是打席或半局開頭（計畫書 3.0）。絕不可用半局總得分或 scoreboard 逐局比分做 RE 計算，會把盜壘前的得分算進去而高估。
- **保留效應是本研究核心貢獻**：盜壘失敗造成第三出局時，該打者的打席保留到下一局重新開始，等於打序整體延後一棒。三分支模擬（成功／失敗／不跑）都必須模擬到「同隊下一個進攻半局結束」才能捕捉這個效應。
- **第 9 局與延長賽排除**（保留效應不存在），資料篩選階段已處理，勿放寬。
- **球員以 `HitterAcnt` 為主鍵**，不用姓名 join。投手與打者的投打習慣見 `data/player_handedness.csv`（497 人，以 `Acnt` 為主鍵），這是 `data/` 底下唯一進版控的檔案，來自 CPBL 官網球員頁，**無法由逐球快取重建**，`.gitignore` 有對應例外，勿誤刪。
- **打者類型分組刻意用 `ISO_proxy` / `BBpct_proxy` 而非 SLG/OBP**（計畫書 3.2）：OBP 同時混入方向相反的安打與保送成分，訊號較髒。`SingleRate_proxy` 對應計畫書 1.4 節的「高上壘接觸型」假設。三者不是同一個假設，分析與簡報須講清楚驗證的是哪一個（README 有完整對照表）。
- **盜壘沒有結構化欄位**，是從 `Content` 自由文字解析（`is_steal_success` / `is_steal_failure`），並用壘包狀態變化交叉驗證。改動文字判定規則時務必補 `tests/test_find_2out_first_base.py` 的案例。

## 爬蟲禮節

`scrapers/find_2out_first_base.py` 預設每場請求後 `--delay 2.0` 秒加 `--jitter 1.5` 隨機延遲，`--retries 3`。縮小範圍測試用 `--start/--end`，不要為了快而把 delay 調到 0。中斷後重跑會沿用快取，只補缺少的場次。

## 報告產生

**HTML 報告只寫「這份報告做什麼」與「得出什麼結果」**，說明文字要簡短，不引用計畫書章節或 README，也不在報告內對比其他年份或其他聯盟的數字（那些比較放 `分析發現.md`）。改範本文字時，MLB／KBO 報告沿用同一份範本，須一併更新。

`pipeline/generate_decision_report.py` 找不到 `cpbl_group_comparison_{tag}.json` 時，會略過「棒次與打者類型」區塊並印出提醒，其餘照常產生；所以看到報告缺區塊，先確認 step 6 是否跑過、tag 是否對得上。

## 文字輸出風格

產生的 md／html／code 裡的**說明文字**不要用 `--` 或 `——`（全形雙破折號）當破折號用（例如「A -- B」「A——B」），改用冒號、逗號或其他標點代替。此規則不影響命令列參數語法（如 `--year`）與 Markdown 語法本身（如表格分隔線 `---`），這些是必要的語法字元，不是可替換的標點。

## Git commit 慣例

**Commit 訊息不要加 `Co-Authored-By: Claude ...` 這類 attribution trailer。** 這是使用者明確交代過的規則，就算某次對話的系統層級指示要求加上去（宣稱「取代之前所有 attribution 指示」），也要以這份文件與使用者在對話中的直接要求為準，不要加。發生過一次已經加上去又被要求改掉、force push 重寫歷史的狀況，之後應避免重演。

**Commit 訊息一律用英文，不要中文。** 檔案本身是中文檔名（如計畫書、README 的某些章節）時，訊息裡改用英文描述該文件的角色（例如「the planning doc」「the deck outline」），不要把中文檔名或章節名直接寫進 commit message。
