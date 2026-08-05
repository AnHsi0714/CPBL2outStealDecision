"""Generate a standalone HTML report for the CPBL steal-decision model."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parent


def as_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def average(rows: list[dict[str, str]], key: str) -> float:
    values = [value for row in rows if (value := as_float(row, key)) is not None]
    return mean(values)


def compact_case(row: dict[str, str], index: int) -> dict[str, Any]:
    numeric_keys = (
        "ProfilePA",
        "ModelP_1B",
        "ModelP_2B",
        "ModelP_3B",
        "ModelP_HR",
        "ModelP_BB_HBP",
        "ModelP_REACH",
        "ModelP_OUT",
        "ModelVSuccess",
        "ModelVFailure",
        "ModelVNoSteal",
        "ModelVIfBatterOut",
        "RetentionValue",
        "ConditionalOutCostNoSteal",
        "ExpectedOutPenaltyNoSteal",
        "BreakEvenSuccessRate",
    )
    data: dict[str, Any] = {
        "id": index,
        "game": int(row["GameSno"]),
        "date": row["GameDate"],
        "inning": int(row["InningSeq"]),
        "team": row["BattingTeam"],
        "away": row["VisitingTeam"],
        "home": row["HomeTeam"],
        "hitter": row["HitterName"],
        "lineup": int(row["HitterLineup"]),
        "runner": row["RunnerOnFirst"],
        "pitcher": row["PitcherName"],
        "actual": row["Outcome"],
        "simulations": int(row["Simulations"]),
        "thresholdStatus": row["ThresholdStatus"],
    }
    for key in numeric_keys:
        value = as_float(row, key)
        data[key] = None if value is None else round(value, 6)
    return data


def build_payload(rows: list[dict[str, str]], summary: dict[str, Any]) -> dict[str, Any]:
    outcome_counts = {"steal_success": 0, "steal_failure": 0, "no_steal": 0}
    for row in rows:
        outcome = row.get("Outcome", "")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    valid_thresholds = [
        value
        for row in rows
        if (value := as_float(row, "BreakEvenSuccessRate")) is not None
        and 0 <= value <= 1
    ]
    cases = [compact_case(row, index) for index, row in enumerate(rows)]
    threshold_median = median(valid_thresholds)
    default_case = min(
        range(len(cases)),
        key=lambda index: abs(
            (cases[index]["BreakEvenSuccessRate"] or threshold_median) - threshold_median
        ),
    )

    v_success = average(rows, "ModelVSuccess")
    v_failure = average(rows, "ModelVFailure")
    v_no_steal = average(rows, "ModelVNoSteal")
    aggregate_threshold = (v_no_steal - v_failure) / (v_success - v_failure)

    return {
        "meta": {
            "year": int(summary["year"]),
            "games": int(summary["games_with_raw_data"]),
            "samples": len(rows),
            "completedPA": int(summary["completed_pa_for_profiles"]),
            "batters": int(summary["batter_profiles"]),
            "simulations": int(summary["simulations_per_context"]),
            "priorPA": float(summary["prior_pa"]),
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "aggregate": {
            "vSuccess": round(v_success, 6),
            "vFailure": round(v_failure, 6),
            "vNoSteal": round(v_no_steal, 6),
            "successGain": round(v_success - v_no_steal, 6),
            "failureCost": round(v_no_steal - v_failure, 6),
            "aggregateThreshold": round(aggregate_threshold, 6),
            "medianThreshold": round(threshold_median, 6),
            "retentionValue": round(average(rows, "RetentionValue"), 6),
            "conditionalOutCost": round(average(rows, "ConditionalOutCostNoSteal"), 6),
            "expectedOutPenalty": round(average(rows, "ExpectedOutPenaltyNoSteal"), 6),
            "outcomes": outcome_counts,
        },
        "defaultCase": default_case,
        "cases": cases,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>2025 CPBL 兩出局僅一壘有人：盜壘決策報告</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f4f1ea;
      --surface: #fffdf8;
      --text: #18201c;
      --muted: #65706a;
      --line: #d9d4c9;
      --success: #147d62;
      --failure: #b34a3c;
      --neutral: #456582;
      --accent: #d59c25;
      --soft-success: #dff2ea;
      --soft-failure: #f7e3df;
      --soft-neutral: #e4edf5;
      --shadow: 0 14px 35px rgba(43, 49, 45, .09);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111512;
        --surface: #1a201c;
        --text: #edf2ee;
        --muted: #aab5ae;
        --line: #39423c;
        --success: #54c9a5;
        --failure: #ef8f82;
        --neutral: #8db4d6;
        --accent: #efbd55;
        --soft-success: #173a30;
        --soft-failure: #452824;
        --soft-neutral: #203747;
        --shadow: none;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      line-height: 1.65;
    }
    .wrap { width: min(1120px, calc(100% - 32px)); margin: 0 auto; }
    header { padding: 64px 0 30px; border-bottom: 1px solid var(--line); }
    .eyebrow { color: var(--success); font-weight: 700; letter-spacing: .08em; }
    h1 { max-width: 850px; margin: 8px 0 12px; font-size: clamp(2rem, 5vw, 4.2rem); line-height: 1.08; letter-spacing: -.035em; }
    h2 { margin: 0 0 20px; font-size: clamp(1.45rem, 3vw, 2rem); line-height: 1.25; }
    h3 { margin: 0 0 8px; font-size: 1.05rem; }
    p { margin: 0 0 12px; }
    .lede { max-width: 780px; color: var(--muted); font-size: 1.08rem; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 24px; color: var(--muted); font-size: .9rem; }
    main { padding: 36px 0 80px; }
    section { margin: 0 0 58px; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    .stat, .branch, .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }
    .stat { padding: 18px; }
    .stat small { display: block; color: var(--muted); }
    .stat strong { display: block; margin: 3px 0; font-size: 1.75rem; line-height: 1.2; }
    .stat span { color: var(--muted); font-size: .86rem; }
    .branches { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .branch { overflow: hidden; }
    .branch-head { padding: 18px 20px; }
    .branch.success .branch-head { background: var(--soft-success); }
    .branch.failure .branch-head { background: var(--soft-failure); }
    .branch.neutral .branch-head { background: var(--soft-neutral); }
    .branch-value { font-size: 2rem; font-weight: 750; line-height: 1; }
    .branch-body { padding: 18px 20px 20px; }
    .branch ol { margin: 0; padding-left: 1.25rem; }
    .branch li + li { margin-top: 7px; }
    .bar-row { display: grid; grid-template-columns: 96px 1fr 72px; align-items: center; gap: 12px; margin: 16px 0; }
    .track { height: 18px; background: color-mix(in srgb, var(--line) 70%, transparent); border-radius: 999px; overflow: hidden; }
    .bar { height: 100%; border-radius: inherit; }
    .bar.success { background: var(--success); }
    .bar.failure { background: var(--failure); }
    .bar.neutral { background: var(--neutral); }
    .formula {
      margin-top: 24px;
      padding: 22px;
      border-left: 5px solid var(--accent);
      background: var(--surface);
      border-radius: 0 14px 14px 0;
    }
    code { color: var(--text); font-family: "Cascadia Code", Consolas, monospace; }
    .formula code { display: block; margin: 8px 0; font-size: clamp(.9rem, 2vw, 1.08rem); overflow-wrap: anywhere; }
    .panel { padding: 24px; }
    .controls { display: grid; grid-template-columns: 1fr 1.5fr; gap: 14px; margin-bottom: 22px; }
    label { display: grid; gap: 5px; color: var(--muted); font-size: .88rem; }
    input, select {
      width: 100%;
      min-height: 42px;
      padding: 8px 10px;
      color: var(--text);
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 9px;
      font: inherit;
    }
    input[type="range"] { padding: 0; }
    .case-title { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 20px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
    .case-title strong { font-size: 1.25rem; }
    .case-title span { color: var(--muted); }
    .simulator { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 24px 0; align-items: center; }
    .decision-readout { padding: 20px; border-radius: 14px; background: var(--soft-neutral); }
    .decision-readout.good { background: var(--soft-success); }
    .decision-readout.bad { background: var(--soft-failure); }
    .decision-readout strong { display: block; font-size: 1.45rem; }
    .range-value { color: var(--text); font-weight: 700; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: .92rem; }
    th, td { padding: 10px 9px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
    th:first-child, td:first-child { text-align: left; }
    th { color: var(--muted); font-weight: 650; }
    .note-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 30px; padding-left: 1.2rem; }
    .note-list li { padding-left: 3px; }
    .muted { color: var(--muted); }
    .pill { display: inline-block; padding: 2px 9px; border: 1px solid var(--line); border-radius: 999px; font-size: .78rem; color: var(--muted); }
    footer { padding: 24px 0 50px; border-top: 1px solid var(--line); color: var(--muted); font-size: .88rem; }
    @media (max-width: 820px) {
      .grid { grid-template-columns: repeat(2, 1fr); }
      .branches { grid-template-columns: 1fr; }
      .simulator { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .wrap { width: min(100% - 22px, 1120px); }
      header { padding-top: 38px; }
      .grid, .controls, .note-list { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 82px 1fr 58px; gap: 8px; }
      .panel { padding: 17px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div class="eyebrow">CPBL · 2025 REGULAR SEASON</div>
      <h1>兩出局、僅一壘有人時，盜壘值不值得？</h1>
      <p class="lede">把同一個比賽瞬間拆成「成功、失敗、不跑」三條平行路線，以當前打者及後續打序的個人化打擊分布，估算一致時間範圍內的期望得分。</p>
      <div class="meta">
        <span id="meta-games"></span><span id="meta-pa"></span><span id="meta-batters"></span><span id="meta-sims"></span>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section aria-labelledby="overview-title">
      <h2 id="overview-title">2025 資料概況</h2>
      <div class="grid">
        <article class="stat"><small>符合條件的決策機會</small><strong id="stat-samples"></strong><span>第 1–8 局、2 出局、僅一壘有人</span></article>
        <article class="stat"><small>實際盜壘成功</small><strong id="stat-success-count"></strong><span id="stat-success-rate"></span></article>
        <article class="stat"><small>實際盜壘失敗</small><strong id="stat-failure-count"></strong><span id="stat-failure-rate"></span></article>
        <article class="stat"><small>情境損益兩平中位數</small><strong id="stat-threshold"></strong><span>每個情境先各自計算，再取中位數</span></article>
      </div>
    </section>

    <section aria-labelledby="branches-title">
      <h2 id="branches-title">三種情況怎麼算</h2>
      <div class="branches">
        <article class="branch success">
          <div class="branch-head"><h3>1 · 盜壘成功</h3><div class="branch-value" id="v-success"></div><small>平均期望得分</small></div>
          <div class="branch-body"><ol><li>維持兩出局，跑者移到二壘。</li><li>當前打者繼續完成打席。</li><li>模擬本半局剩餘攻勢。</li><li>再模擬球隊下一次進攻半局。</li></ol></div>
        </article>
        <article class="branch failure">
          <div class="branch-head"><h3>2 · 盜壘失敗</h3><div class="branch-value" id="v-failure"></div><small>平均期望得分</small></div>
          <div class="branch-body"><ol><li>跑者成為第三個出局。</li><li>目前半局立刻結束，得分為 0。</li><li>打席未完成，當前打者被保留。</li><li>下一次進攻由當前打者先打。</li></ol></div>
        </article>
        <article class="branch neutral">
          <div class="branch-head"><h3>3 · 不盜壘</h3><div class="branch-value" id="v-no-steal"></div><small>平均期望得分</small></div>
          <div class="branch-body"><ol><li>維持兩出局、一壘有人。</li><li>當前打者繼續完成打席。</li><li>若打者出局，本半局結束。</li><li>下一次進攻改由下一棒開始。</li></ol></div>
        </article>
      </div>

      <div class="panel" style="margin-top: 18px">
        <div class="bar-row"><span>成功</span><div class="track"><div id="bar-success" class="bar success"></div></div><strong id="bar-success-label"></strong></div>
        <div class="bar-row"><span>失敗</span><div class="track"><div id="bar-failure" class="bar failure"></div></div><strong id="bar-failure-label"></strong></div>
        <div class="bar-row"><span>不跑</span><div class="track"><div id="bar-no-steal" class="bar neutral"></div></div><strong id="bar-no-steal-label"></strong></div>
      </div>

      <div class="formula">
        <strong>盜壘損益兩平成功率</strong>
        <code>p* = (V不跑 − V失敗) ÷ (V成功 − V失敗)</code>
        <code id="aggregate-formula"></code>
        <p class="muted">以三條路線的全體平均值計算為 <strong id="aggregate-threshold"></strong>；逐情境計算後的中位數為 <strong id="median-threshold"></strong>。兩者不同是因為「先平均再相除」不等於「先逐筆相除再取中位數」。</p>
      </div>
    </section>

    <section aria-labelledby="personal-title">
      <h2 id="personal-title">打者沒有被視為同一個人</h2>
      <div class="panel">
        <p>每位打者都有自己的 <code>1B / 2B / 3B / HR / BB-HBP / REACH / OUT</code> 機率。為避免少量打席失真，使用 50 打席的聯盟平均先驗：</p>
        <div class="formula"><code>修正後機率 =（打者實際結果 + 50 打席 × 聯盟平均率）÷（打者實際打席 + 50）</code></div>
        <p style="margin-top:18px">個人化的是打者及打序；目前使用聯盟平均的是同種打擊結果下的跑者推進、投手、守備、跑者速度與捕手阻殺能力。</p>
        <div class="grid" style="margin-top:18px">
          <article class="stat"><small>條件式出局成本</small><strong id="out-cost"></strong><span>非出局分支 EV − 出局分支 EV</span></article>
          <article class="stat"><small>期望出局懲罰</small><strong id="out-penalty"></strong><span>條件式成本 × 該打者出局率</span></article>
          <article class="stat"><small>保留打者平均差異</small><strong id="retention"></strong><span>失敗後同一打者下局先打的打序效果</span></article>
          <article class="stat"><small>平滑先驗</small><strong id="prior-pa"></strong><span>主力打者仍主要由本人數據決定</span></article>
        </div>
      </div>
    </section>

    <section aria-labelledby="explorer-title">
      <h2 id="explorer-title">逐筆重算：換一位打者就會得到不同答案</h2>
      <div class="panel">
        <div class="controls">
          <label>搜尋打者、球隊或場次
            <input id="case-search" type="search" placeholder="例如：林安可、統一、Game 120">
          </label>
          <label>選擇一筆決策機會
            <select id="case-select"></select>
          </label>
        </div>

        <div class="case-title">
          <div><strong id="case-heading"></strong><div id="case-subheading" class="muted"></div></div>
          <div><span class="pill" id="case-actual"></span></div>
        </div>

        <div class="simulator">
          <div>
            <label for="success-rate">假設這次盜壘成功率：<span class="range-value" id="success-rate-value"></span></label>
            <input id="success-rate" type="range" min="0" max="100" step="0.1">
            <p class="muted">EV(盜壘) = p × V成功 + (1 − p) × V失敗</p>
          </div>
          <div id="decision-readout" class="decision-readout" aria-live="polite">
            <strong id="decision-label"></strong>
            <span id="decision-math"></span>
          </div>
        </div>

        <div class="table-wrap">
          <table>
            <thead><tr><th>此情境</th><th>V成功</th><th>V失敗</th><th>V不跑</th><th>損益兩平</th><th>出局成本</th><th>期望出局懲罰</th></tr></thead>
            <tbody id="case-values"></tbody>
          </table>
        </div>
        <div class="table-wrap" style="margin-top:18px">
          <table>
            <thead><tr><th>打者模型</th><th>PA</th><th>1B</th><th>2B</th><th>3B</th><th>HR</th><th>BB/HBP</th><th>其他上壘</th><th>OUT</th></tr></thead>
            <tbody id="case-profile"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section aria-labelledby="scope-title">
      <h2 id="scope-title">解讀邊界</h2>
      <ul class="note-list">
        <li>這是得分期望值（RE），不是勝率增加值（WPA）。</li>
        <li>目前不估盜壘成功率；成功率由使用者或後續模型提供。</li>
        <li>跑者速度、投捕手組合、比分與投手能力尚未個人化。</li>
        <li>第八局下半沒有真實的下一次進攻；模型仍以假想下一半局維持比較尺度一致。</li>
        <li>三條路線皆比較「目前半局剩餘 + 球隊下一次進攻半局」。</li>
        <li>這份頁面是模型結果的可追溯說明，不代表教練當時的選擇一定正確或錯誤。</li>
      </ul>
    </section>
  </main>

  <footer><div class="wrap">資料：CPBL 官網逐球紀錄 · 模型版本 batter-outcome-and-lineup-v1 · 產生時間 <span id="generated-at"></span></div></footer>

  <script id="report-data" type="application/json">__REPORT_DATA__</script>
  <script>
    const REPORT = JSON.parse(document.getElementById('report-data').textContent);
    const $ = (id) => document.getElementById(id);
    const fmt = (value, digits = 3) => Number(value).toFixed(digits);
    const pct = (value, digits = 1) => `${(Number(value) * 100).toFixed(digits)}%`;
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    })[char]);
    const outcomeLabel = { steal_success: '實際：盜壘成功', steal_failure: '實際：盜壘失敗', no_steal: '實際：不盜壘' };

    function fillAggregate() {
      const { meta: m, aggregate: a } = REPORT;
      $('meta-games').textContent = `${m.games} 場完整賽事`;
      $('meta-pa').textContent = `${m.completedPA.toLocaleString()} 個完成打席`;
      $('meta-batters').textContent = `${m.batters} 位打者`;
      $('meta-sims').textContent = `每情境 ${m.simulations.toLocaleString()} 次模擬`;
      $('stat-samples').textContent = m.samples.toLocaleString();
      $('stat-success-count').textContent = a.outcomes.steal_success.toLocaleString();
      $('stat-failure-count').textContent = a.outcomes.steal_failure.toLocaleString();
      const attempts = a.outcomes.steal_success + a.outcomes.steal_failure;
      $('stat-success-rate').textContent = `占 ${attempts} 次實際嘗試的 ${pct(a.outcomes.steal_success / attempts)}`;
      $('stat-failure-rate').textContent = `占 ${attempts} 次實際嘗試的 ${pct(a.outcomes.steal_failure / attempts)}`;
      $('stat-threshold').textContent = pct(a.medianThreshold);
      $('v-success').textContent = fmt(a.vSuccess);
      $('v-failure').textContent = fmt(a.vFailure);
      $('v-no-steal').textContent = fmt(a.vNoSteal);
      const maxValue = Math.max(a.vSuccess, a.vFailure, a.vNoSteal);
      [['success', a.vSuccess], ['failure', a.vFailure], ['no-steal', a.vNoSteal]].forEach(([id, value]) => {
        $(`bar-${id}`).style.width = `${(value / maxValue) * 100}%`;
        $(`bar-${id}-label`).textContent = fmt(value);
      });
      $('aggregate-formula').textContent = `(${fmt(a.vNoSteal)} − ${fmt(a.vFailure)}) ÷ (${fmt(a.vSuccess)} − ${fmt(a.vFailure)}) = ${pct(a.aggregateThreshold)}`;
      $('aggregate-threshold').textContent = pct(a.aggregateThreshold);
      $('median-threshold').textContent = pct(a.medianThreshold);
      $('out-cost').textContent = `${fmt(a.conditionalOutCost)} 分`;
      $('out-penalty').textContent = `${fmt(a.expectedOutPenalty)} 分`;
      $('retention').textContent = `${a.retentionValue >= 0 ? '+' : ''}${fmt(a.retentionValue)} 分`;
      $('prior-pa').textContent = `${m.priorPA} PA`;
      $('generated-at').textContent = new Date(m.generatedAt).toLocaleString('zh-TW');
    }

    function optionText(c) {
      return `Game ${c.game}｜${c.inning}局｜${c.hitter}（${c.team}）`;
    }

    function populateCases(query = '') {
      const select = $('case-select');
      const normalized = query.trim().toLowerCase();
      const selected = Number(select.value);
      select.textContent = '';
      const matches = REPORT.cases.filter((c) => {
        const haystack = `${c.hitter} ${c.team} ${c.away} ${c.home} game ${c.game}`.toLowerCase();
        return !normalized || haystack.includes(normalized);
      });
      for (const c of matches) {
        const option = document.createElement('option');
        option.value = c.id;
        option.textContent = optionText(c);
        select.appendChild(option);
      }
      const desired = matches.some((c) => c.id === selected) ? selected : (matches[0]?.id ?? null);
      if (desired !== null) {
        select.value = String(desired);
        renderCase(desired, true);
      } else {
        const option = document.createElement('option');
        option.textContent = '找不到符合資料';
        select.appendChild(option);
      }
    }

    function renderCase(id, resetRate = false) {
      const c = REPORT.cases[Number(id)];
      if (!c) return;
      $('case-heading').textContent = `${c.hitter}｜第 ${c.lineup} 棒｜${c.inning} 局`;
      $('case-subheading').textContent = `${c.date} · Game ${c.game} · ${c.away} vs ${c.home} · 一壘跑者 ${c.runner || '未記錄'} · 投手 ${c.pitcher || '未記錄'}`;
      $('case-actual').textContent = outcomeLabel[c.actual] || c.actual;
      $('case-values').innerHTML = `<tr><td>${esc(c.hitter)}</td><td>${fmt(c.ModelVSuccess)}</td><td>${fmt(c.ModelVFailure)}</td><td>${fmt(c.ModelVNoSteal)}</td><td>${c.BreakEvenSuccessRate === null ? '無' : pct(c.BreakEvenSuccessRate)}</td><td>${fmt(c.ConditionalOutCostNoSteal)}</td><td>${fmt(c.ExpectedOutPenaltyNoSteal)}</td></tr>`;
      $('case-profile').innerHTML = `<tr><td>${esc(c.hitter)}</td><td>${Math.round(c.ProfilePA)}</td><td>${pct(c.ModelP_1B)}</td><td>${pct(c.ModelP_2B)}</td><td>${pct(c.ModelP_3B)}</td><td>${pct(c.ModelP_HR)}</td><td>${pct(c.ModelP_BB_HBP)}</td><td>${pct(c.ModelP_REACH)}</td><td>${pct(c.ModelP_OUT)}</td></tr>`;
      if (resetRate) {
        const threshold = c.BreakEvenSuccessRate === null ? REPORT.aggregate.medianThreshold : c.BreakEvenSuccessRate;
        $('success-rate').value = String(Math.min(100, Math.max(0, threshold * 100)));
      }
      updateDecision(c);
    }

    function updateDecision(c = REPORT.cases[Number($('case-select').value)]) {
      if (!c) return;
      const p = Number($('success-rate').value) / 100;
      const stealEV = p * c.ModelVSuccess + (1 - p) * c.ModelVFailure;
      const delta = stealEV - c.ModelVNoSteal;
      $('success-rate-value').textContent = pct(p);
      $('decision-label').textContent = delta >= 0 ? '這個成功率下：盜壘較有利' : '這個成功率下：不跑較有利';
      $('decision-math').textContent = `EV(盜壘) ${fmt(stealEV)} − EV(不跑) ${fmt(c.ModelVNoSteal)} = ${delta >= 0 ? '+' : ''}${fmt(delta)} 分`;
      $('decision-readout').className = `decision-readout ${delta >= 0 ? 'good' : 'bad'}`;
    }

    fillAggregate();
    $('case-select').value = String(REPORT.defaultCase);
    populateCases();
    $('case-select').value = String(REPORT.defaultCase);
    renderCase(REPORT.defaultCase, true);
    $('case-search').addEventListener('input', (event) => populateCases(event.target.value));
    $('case-select').addEventListener('change', (event) => renderCase(event.target.value, true));
    $('success-rate').addEventListener('input', () => updateDecision());
  </script>
</body>
</html>
'''


def generate_report(
    model_csv: Path,
    summary_json: Path,
    output: Path,
) -> dict[str, Any]:
    with model_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Model CSV has no rows: {model_csv}")

    with summary_json.open("r", encoding="utf-8-sig") as handle:
        summary = json.load(handle)

    payload = build_payload(rows, summary)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_json = payload_json.replace("</", "<\\/")
    document = HTML_TEMPLATE.replace("__REPORT_DATA__", payload_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--model-csv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stem = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    model_csv = args.model_csv or ROOT / "outputs" / f"cpbl_decision_model_{stem}.csv"
    summary_json = args.summary_json or ROOT / "outputs" / f"cpbl_decision_model_{stem}_summary.json"
    output = args.output or ROOT / "reports" / f"cpbl-steal-decision-{args.year}.html"
    payload = generate_report(model_csv, summary_json, output)
    print(
        f"Wrote {output} with {payload['meta']['samples']} cases; "
        f"median threshold={payload['aggregate']['medianThreshold']:.3%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
