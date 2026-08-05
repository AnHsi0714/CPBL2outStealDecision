# 兩出局該不該跑？——中職教練的跑壘決策指南

2026 台灣棒球數據分析競賽（現場分析戰術組）參賽專案。研究在**第 1–8 局、兩出局、僅一壘有人**的情境下，發動盜壘的損益兩平成功率門檻是多少，以及這個門檻如何隨打者棒次與打者類型改變。

完整研究背景、方法論、時程與分工，請見計畫書：[兩出局一壘有人盜壘決策_專案計畫書.md](./兩出局一壘有人盜壘決策_專案計畫書.md)。

## 核心概念

盜壘失敗（第三出局）會讓該打者的打席保留到下一局重新開始，等於用「打序整體往後延一棒」換取當下的出局風險。傳統 RE24 分析只看當半局的損益，忽略了這個保留效應——這是本研究的核心貢獻。詳見計畫書 1.3、1.4 節。

**重要方法論提醒**：計算「盜壘後的剩餘得分」時，起算點是**盜壘成功的那一球**，不是打席開始或該半局開始；不能直接使用半局總得分，否則會把盜壘之前已發生的得分也算進去，高估 RE。詳見計畫書 3.0 節。

## 專案結構

```
.
├── getData.py                              # CPBL 官網逐場資料爬蟲（補充 2025-2026 資料用）
├── 兩出局一壘有人盜壘決策_專案計畫書.md      # 完整計畫書
└── README.md
```

## 資料來源

| 來源 | 內容 | 涵蓋期間 |
|-----|------|--------|
| 野球革命 Open Data（主要） | game / batterBox / pitcherBox / PA / event / runner 六表 | 2023–2024 |
| CPBL 官網（`getData.py`，補充） | 逐場逐球紀錄、逐局比分、球員盒分 | 2025–2026 |

詳細欄位需求與已知限制見計畫書「二、資料來源」。

## 快速開始

```bash
pip install requests

python find_2out_first_base.py
```

`find_2out_first_base.py` 預設抓取 2026 年例行賽 GameSno 1–240，篩出第 1–8 局、
兩出局且僅一壘有人的打席，輸出：

- `Outcome=steal_success`：`RequestedRE` 是盜壘成功事件後至當半局結束的剩餘得分。
- `Outcome=steal_failure`：`RequestedRE` 是同隊下一個半局的得分。
- `Outcome=no_steal`：`RequestedRE` 是同隊下一個半局的得分。

逐場原始回應快取於 `data/raw/cpbl/`，分析結果寫入 `outputs/`。若途中中斷，重跑
同一指令會沿用已完成的快取，只重抓缺少的場次。可用參數縮小範圍做測試：

```bash
python find_2out_first_base.py --start 226 --end 240 --delay 1
```

CSV 同時保留當半局剩餘得分、下一半局得分與兩半局合計，方便後續依研究定義調整。

抓取完成後，可執行第一版打者與打序模型：

```bash
python model_batter_decisions.py --simulations 2000
```

若要處理完整 2025 球季：

```bash
python find_2out_first_base.py --year 2025 --start 1 --end 360
python model_batter_decisions.py --year 2025 --start 1 --end 360 --simulations 2000
```

模型使用打者個人的 `1B/2B/3B/HR/BB-HBP/REACH/OUT` 機率，同時模擬：

- 成功：二壘、兩出局、當前打者繼續打，再算到下一個進攻半局結束。
- 失敗：當局結束，下一局保留當前打者開頭。
- 不跑：一壘、兩出局、當前打者繼續打，再算到下一個進攻半局結束。

壘包推進暫時使用聯盟整體、相同 base-out state 與打席結果的經驗分布，尚未加入
個別跑者速度。輸出包含三分支價值、打者出局傷害、打者保留價值與損益兩平成功率。
出局傷害另拆成「非出局時的分支價值」「一次出局的條件成本」與「依打者 OUT%
加權後的預期損失」，避免把高出局率和單次第三出局的傷害混為同一件事。

原本的通用逐球資料匯出仍可執行：

```bash
python getData.py
```

`getData.py` 預設抓 2026 年例行賽 GameSno 226–240，每抓完一場比賽會隨機延遲數秒再抓下一場，避免對 CPBL 官網造成過大負擔。輸出三張 CSV：

- `cpbl_playbyplay_*.csv`：逐球紀錄（含壘包狀態、累積比分、打序）
- `cpbl_scoreboard_*.csv`：逐局比分（僅供總覽/核對，不可用於 RE 計算，見計畫書 3.0）
- `cpbl_batting_*.csv`：球員整場盒分（含盜壘成功/失敗次數，可用於 QA 對帳）

要換抓其他場次，修改檔案最下方的 `YEAR` / `KIND_CODE` / `GAME_SNO_START` / `GAME_SNO_END`。

## 資料使用注意事項

- 野球革命 Open Data 依 **ODC-By** 授權，使用時須標註來源。
- CPBL 官網資料屬自行爬蟲取得，請留意其使用條款並控制爬取頻率；原始資料與程式碼分開管理，**不建議把大型原始資料檔（CSV/JSON）進版控**。
- Open Data 與 CPBL 官網資料均含部分人工紀錄成分，盜壘等事件性紀錄須留意判讀誤差，詳見計畫書「已知限制」。

## 2025 互動報告

可直接用瀏覽器開啟 [reports/cpbl-steal-decision-2025.html](reports/cpbl-steal-decision-2025.html)。報告包含三種決策路線的計算流程、2025 整體結果、損益兩平公式，以及 1,877 筆情境的逐筆查詢與成功率試算。

模型結果更新後可重新產生報告：

```bash
python generate_decision_report.py
```

也可指定其他球季或輸出位置：

```bash
python generate_decision_report.py --year 2025 --start 1 --end 360 --output reports/cpbl-steal-decision-2025.html
```
