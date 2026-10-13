    const REPORT = JSON.parse(document.getElementById('report-data').textContent);
    const $ = (id) => document.getElementById(id);
    const fmt = (value, digits = 3) => Number(value).toFixed(digits);
    const pct = (value, digits = 1) => `${(Number(value) * 100).toFixed(digits)}%`;
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    })[char]);

    // 隊色只當色塊，文字仍用一般文字色，確保對比。名稱對應各聯盟資料中的寫法。
    const TEAM_COLORS = {
      '中信兄弟': '#f2c200', '統一7-ELEVEn獅': '#f26a21', '樂天桃猿': '#8b1c3f', '富邦悍將': '#0b5cab', '味全龍': '#d6001c', '台鋼雄鷹': '#00793a',
      'KIA': '#ea0029', 'KT': '#000000', 'LG': '#c30452', 'NC': '#315288', 'SSG': '#ce0e2d', '두산': '#131230', '롯데': '#041e42', '삼성': '#074ca1', '키움': '#820024', '한화': '#fc4e00',
      'Arizona Diamondbacks': '#a71930', 'Athletics': '#003831', 'Oakland Athletics': '#003831', 'Atlanta Braves': '#ce1141', 'Baltimore Orioles': '#df4601',
      'Boston Red Sox': '#bd3039', 'Chicago Cubs': '#0e3386', 'Chicago White Sox': '#27251f', 'Cincinnati Reds': '#c6011f', 'Cleveland Guardians': '#e31937',
      'Colorado Rockies': '#33006f', 'Detroit Tigers': '#0c2340', 'Houston Astros': '#eb6e1f', 'Kansas City Royals': '#004687', 'Los Angeles Angels': '#ba0021',
      'Los Angeles Dodgers': '#005a9c', 'Miami Marlins': '#00a3e0', 'Milwaukee Brewers': '#12284b', 'Minnesota Twins': '#002b5c', 'New York Mets': '#ff5910',
      'New York Yankees': '#0c2340', 'Philadelphia Phillies': '#e81828', 'Pittsburgh Pirates': '#fdb827', 'San Diego Padres': '#2f241d', 'San Francisco Giants': '#fd5a1e',
      'Seattle Mariners': '#005c5c', 'St. Louis Cardinals': '#c41e3a', 'Tampa Bay Rays': '#092c5c', 'Texas Rangers': '#003278', 'Toronto Blue Jays': '#134a8e',
      'Washington Nationals': '#ab0003',
    };
    // 英文、韓文隊名顯示成中文，原文放在 hover 提示。
    const TEAM_ZH = {
      'KIA': '起亞老虎', 'KT': 'KT巫師', 'LG': 'LG雙子', 'NC': 'NC恐龍', 'SSG': 'SSG登陸者', '두산': '斗山熊', '롯데': '樂天巨人', '삼성': '三星獅', '키움': '啟動英雄', '한화': '韓華鷹',
      'Arizona Diamondbacks': '亞利桑那響尾蛇', 'Athletics': '運動家', 'Oakland Athletics': '奧克蘭運動家', 'Atlanta Braves': '亞特蘭大勇士', 'Baltimore Orioles': '巴爾的摩金鶯',
      'Boston Red Sox': '波士頓紅襪', 'Chicago Cubs': '芝加哥小熊', 'Chicago White Sox': '芝加哥白襪', 'Cincinnati Reds': '辛辛那提紅人', 'Cleveland Guardians': '克里夫蘭守護者',
      'Colorado Rockies': '科羅拉多洛磯', 'Detroit Tigers': '底特律老虎', 'Houston Astros': '休士頓太空人', 'Kansas City Royals': '堪薩斯皇家', 'Los Angeles Angels': '洛杉磯天使',
      'Los Angeles Dodgers': '洛杉磯道奇', 'Miami Marlins': '邁阿密馬林魚', 'Milwaukee Brewers': '密爾瓦基釀酒人', 'Minnesota Twins': '明尼蘇達雙城', 'New York Mets': '紐約大都會',
      'New York Yankees': '紐約洋基', 'Philadelphia Phillies': '費城費城人', 'Pittsburgh Pirates': '匹茲堡海盜', 'San Diego Padres': '聖地牙哥教士', 'San Francisco Giants': '舊金山巨人',
      'Seattle Mariners': '西雅圖水手', 'St. Louis Cardinals': '聖路易紅雀', 'Tampa Bay Rays': '坦帕灣光芒', 'Texas Rangers': '德州遊騎兵', 'Toronto Blue Jays': '多倫多藍鳥',
      'Washington Nationals': '華盛頓國民',
    };
    const teamZh = (name) => TEAM_ZH[name] || name;
    const teamTag = (name) => {
      const color = TEAM_COLORS[name];
      const dot = color ? `<span class="team-dot" style="background:${color}"></span>` : '';
      const zh = teamZh(name);
      const label = zh !== name ? `<span class="team-name" title="${esc(name)}">${esc(zh)}<span class="sr-only">（${esc(name)}）</span></span>` : esc(name);
      return `${dot}${label}`;
    };

    const outcomeLabel = { steal_success: '實際：盜壘成功', steal_failure: '實際：盜壘失敗', no_steal: '實際：不盜壘' };

    function fillValidation() {
      const v = REPORT.validation;
      if (!v || (!v.re24 && !v.steal)) return;
      $('validation-section').hidden = false;
      const cards = [];
      if (v.re24) {
        cards.push(`
          <article class="stat"><small>模擬 vs 真實 RE24（24格）</small><strong>r = ${v.re24.correlation.toFixed(3)}</strong><span>加權平均誤差 ${fmt(v.re24.weightedMae)} 分</span></article>
        `);
      }
      if (v.steal) {
        const s = v.steal;
        const allMatch = s.parsedSuccess === s.officialSuccess && s.parsedCaught === s.officialCaught;
        cards.push(`
          <article class="stat"><small>盜壘文字判讀 vs CPBL 官方統計</small><strong>${s.parsedSuccess}/${s.officialSuccess} 成功・${s.parsedCaught}/${s.officialCaught} 刺殺</strong><span>${s.combos.toLocaleString()} 個場次×球隊組合，${allMatch ? '完全相符' : `${s.mismatches} 組不相符`}</span></article>
        `);
      }
      $('validation-stats').innerHTML = cards.join('');
      $('validation-note').textContent = '';
    }

    function verdictColor(verdict) {
      if (verdict === '跑對') return 'var(--success)';
      if (verdict === '跑錯') return 'var(--failure)';
      return 'var(--muted)';
    }

    function pValueText(row) {
      if (row.pValue === null) return '無';
      return row.pValue < 0.001 ? '< 0.001' : row.pValue.toFixed(3);
    }

    function teamRowHtml(teamName, row, extraLabel) {
      const rate = row.actualSuccessRate === null ? '無嘗試' : pct(row.actualSuccessRate);
      const threshold = row.thresholdMedian === null ? '無資料' : pct(row.thresholdMedian);
      return `<tr><td>${teamTag(teamName)}</td><td>${extraLabel}</td><td>${row.attempts.toLocaleString()}</td><td>${rate}</td><td>${threshold}</td><td>${pValueText(row)}</td><td style="color:${verdictColor(row.verdict)}; font-weight:650">${row.verdict}</td></tr>`;
    }

    function fillTeamDecisions() {
      const t = REPORT.teamDecisions;
      if (!t) return;
      $('team-decisions-section').hidden = false;
      const league = t.league;
      $('team-league-summary').textContent =
        `${league.attempts.toLocaleString()} 次嘗試，實際成功率 ${pct(league.actualSuccessRate)}，門檻中位數 ${pct(league.thresholdMedian)}`;
      $('team-decisions-table').innerHTML = t.teams.map((row) => {
        const opp = `<td>${row.opportunities.toLocaleString()}</td>`;
        const rate = row.actualSuccessRate === null ? '無嘗試' : pct(row.actualSuccessRate);
        const ci = row.ci95Low === null ? '無' : `${pct(row.ci95Low)} – ${pct(row.ci95High)}`;
        const threshold = row.thresholdMedian === null ? '無資料' : pct(row.thresholdMedian);
        return `<tr><td>${teamTag(row.team)}</td>${opp}<td>${row.attempts.toLocaleString()}</td><td>${rate}</td><td>${ci}</td><td>${threshold}</td><td>${pValueText(row)}</td><td style="color:${verdictColor(row.verdict)}; font-weight:650">${row.verdict}</td></tr>`;
      }).join('');
      const halfLabels = { front_1_5: '前段(1-5)', back_6_9: '後段(6-9)' };
      const halfRows = [];
      for (const row of t.teams) {
        const halves = t.teamsByLineupHalf[row.team];
        if (!halves) continue;
        for (const key of ['front_1_5', 'back_6_9']) {
          halfRows.push(teamRowHtml(row.team, halves[key], halfLabels[key]));
        }
      }
      $('team-decisions-lineup-table').innerHTML = halfRows.join('');
    }

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
      $('aggregate-formula').textContent = `(${fmt(a.vNoSteal)} − ${fmt(a.vFailure)}) ÷ (${fmt(a.vSuccess)} − ${fmt(a.vFailure)}) = ${pct(a.aggregateThreshold)}`;
      $('aggregate-threshold').textContent = pct(a.aggregateThreshold);
      $('median-threshold').textContent = pct(a.medianThreshold);
      $('out-cost').textContent = `${fmt(a.conditionalOutCost)} 分`;
      $('out-penalty').textContent = `${fmt(a.expectedOutPenalty)} 分`;
      $('retention').textContent = `${a.retentionValue >= 0 ? '+' : ''}${fmt(a.retentionValue)} 分`;
      $('prior-pa').textContent = `${m.priorPA} PA`;
      $('prior-pa-text').textContent = m.priorPA;
      $('generated-at').textContent = new Date(m.generatedAt).toLocaleString('zh-TW');
    }

    const GROUP_LABELS = {
      front_1_5: '前段(1-5)', back_6_9: '後段(6-9)',
      high_ISO: '高長打', low_ISO: '低長打',
      high_BB: '高選球', low_BB: '低選球',
      high_OBP: '高上壘率', low_OBP: '低上壘率',
      high_1B: '高單打率(接觸型)', low_1B: '低單打率',
      high_TTO: '高TTO型', low_TTO: '低TTO型',
    };

    function renderCaseTypeBadges(c) {
      // 這排標籤是「這位打者本人」的固定球員類型，跟這筆決策剛好排第幾棒（見上方 case-heading）無關。
      let badges;
      if (c.batterTypeQualified) {
        badges = [GROUP_LABELS[c.typicalLineupGroup], GROUP_LABELS[c.powerGroup], GROUP_LABELS[c.patienceGroup], GROUP_LABELS[c.obpGroup], GROUP_LABELS[c.contactGroup], GROUP_LABELS[c.ttoGroup]];
      } else {
        badges = ['打席數不足(PA<100)，無球員類型資料'];
      }
      $('case-type-badges').innerHTML = badges.filter(Boolean).map((label) => `<span class="pill">${esc(label)}</span>`).join('');
    }

    const comparisonLabels = {
      lineup_front_vs_back: ['前段(1-5)', '後段(6-9)'],
      power_high_vs_low_ISO: ['高長打', '低長打'],
      patience_high_vs_low_BB: ['高選球', '低選球'],
      obp_high_vs_low_OBP: ['高上壘率', '低上壘率'],
      contact_high_vs_low_1B: ['高單打率(接觸型)', '低單打率'],
      tto_high_vs_low_TTO: ['高TTO型', '低TTO型'],
    };

    function fillSegments() {
      const segments = REPORT.segments;
      if (!segments) return;
      $('segment-section').hidden = false;
      $('segment-qualified').textContent = segments.qualifiedRows.toLocaleString();

      const sub = segments.substitution;
      if (sub) {
        const slotEntries = Object.entries(sub.bySlot).sort((a, b) => Number(a[0]) - Number(b[0]));
        const lowestStarterSlot = slotEntries.reduce((worst, [slot, s]) =>
          (s.starterRate !== null && (!worst || s.starterRate < worst[1].starterRate)) ? [slot, s] : worst, null);
        $('substitution-stats').innerHTML = `
          <article class="stat"><small>決策當下為該棒次先發打者</small><strong>${pct(sub.starterRate)}</strong><span>${sub.starterDecisions.toLocaleString()} / ${sub.totalDecisions.toLocaleString()} 筆</span></article>
          <article class="stat"><small>代打／換人後才上場</small><strong>${pct(1 - sub.starterRate)}</strong><span>${sub.substituteDecisions.toLocaleString()} 筆</span></article>
          <article class="stat"><small>代打比例最高的棒次</small><strong>第 ${lowestStarterSlot[0]} 棒</strong><span>先發比例 ${pct(lowestStarterSlot[1].starterRate)}（n=${lowestStarterSlot[1].n}）</span></article>
        `;
      }

      const medians = segments.lineupSlots.map((s) => s.median).filter((v) => v !== null);
      const hi = Math.max(...medians);
      const lo = Math.max(0, Math.floor((Math.min(...medians) - 0.03) * 20) / 20);
      $('bar-axis-note').textContent = `長條從 ${pct(lo, 0)} 起算，方便看出棒次間的差異。`;
      $('lineup-bars').innerHTML = segments.lineupSlots.map((s) => `
        <div class="bar-row">
          <span>第 ${s.slot} 棒</span>
          <div class="track"><div class="bar neutral" style="width:${s.median === null ? 0 : Math.max(4, ((s.median - lo) / (hi - lo)) * 100)}%"></div></div>
          <strong>${s.median === null ? '無' : pct(s.median)}</strong>
        </div>
      `).join('');

      $('segment-table').innerHTML = segments.comparisons.map((c) => {
        const [labelA, labelB] = comparisonLabels[c.comparison] || [c.comparison, ''];
        const keys = Object.keys(c).filter((k) => !['comparison', 'mann_whitney_u', 'p_value'].includes(k));
        const a = c[keys[0]];
        const b = c[keys[1]];
        const diff = a.median - b.median;
        const pText = c.p_value === null ? '無' : (c.p_value < 0.001 ? '< 0.001' : c.p_value.toFixed(4));
        return `<tr><td>${labelA} vs ${labelB}</td><td>${pct(a.median)}（n=${a.n}）</td><td>${pct(b.median)}（n=${b.n}）</td><td>${diff >= 0 ? '+' : ''}${pct(diff)}</td><td>${pText}</td></tr>`;
      }).join('');

      const slots = segments.lineupSlots.filter((s) => s.median !== null);
      if (slots.length) {
        const sorted = [...slots].sort((a, b) => b.median - a.median);
        const peak = sorted[0];
        const trough = sorted[sorted.length - 1];
        $('peak-slot').textContent = peak.slot;
        $('peak-value').textContent = pct(peak.median);
        $('trough-slot').textContent = trough.slot;
        $('trough-value').textContent = pct(trough.median);
      }
    }

    function runnerTierColor(tier) {
      if (tier === '任一棒次都可跑') return 'var(--success)';
      if (tier === '任一棒次都不建議跑') return 'var(--failure)';
      if (tier === '視下一棒棒次而定') return 'var(--accent)';
      return 'var(--muted)';
    }

    function slotGridHtml(row, slots) {
      const qualifying = new Set(row.qualifyingSlots);
      const known = new Set([...row.qualifyingSlots, ...row.nonQualifyingSlots]);
      return `<div style="display:flex; gap:3px">${slots.map((slot) => {
        const has = known.has(slot);
        const ok = qualifying.has(slot);
        const bg = !has ? 'var(--line)' : (ok ? 'var(--success)' : 'var(--failure)');
        const title = !has ? `第 ${slot} 棒：無門檻資料` : `第 ${slot} 棒門檻 ${pct(row.slotThresholds ? row.slotThresholds[slot] : 0)}：${ok ? '可跑' : '不建議'}`;
        return `<span title="${esc(title)}" style="width:16px;height:16px;border-radius:4px;background:${bg};display:inline-flex;align-items:center;justify-content:center;font-size:.62rem;color:#fff;font-weight:700">${slot}</span>`;
      }).join('')}</div>`;
    }

    function runnerTypeBadgesHtml(row) {
      // 跑者本人的固定球員類型（前段/後段棒次型＋長打/選球/上壘/接觸/TTO），
      // 純供辨識這位跑者是什麼樣的打者，跟左邊的逐棒次門檻判定是兩件事。
      if (!row.batterTypeQualified) {
        return `<span class="pill" style="font-size:.68rem; opacity:.65">打席數不足，無類型資料</span>`;
      }
      return [row.typicalLineupGroup, row.powerGroup, row.patienceGroup, row.obpGroup, row.contactGroup, row.ttoGroup]
        .map((key) => GROUP_LABELS[key])
        .filter(Boolean)
        .map((label) => `<span class="pill" style="font-size:.68rem">${esc(label)}</span>`)
        .join('');
    }

    function renderRunnerTable() {
      const r = REPORT.runnerQualification;
      if (!r) return;
      const query = $('runner-search').value.trim().toLowerCase();
      const filter = $('runner-filter').value;
      const slots = Object.keys(r.thresholds.bySlot).map(Number).sort((a, b) => a - b);
      const rows = r.runners.filter((row) => {
        if (filter && row.tier !== filter) return false;
        if (!query) return true;
        return `${row.hitterName} ${row.team}`.toLowerCase().includes(query);
      });
      $('runner-table').innerHTML = rows.map((row) => {
        const rate = row.successRate === null ? '無嘗試' : pct(row.successRate);
        return `<tr><td><div>${esc(row.hitterName)}</div><div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:5px">${runnerTypeBadgesHtml(row)}</div></td><td>${teamTag(row.team)}</td><td>${row.attempts}</td><td>${rate}</td><td style="color:${runnerTierColor(row.tier)}; font-weight:650">${esc(row.tier)}</td><td>${slotGridHtml({ ...row, slotThresholds: r.thresholds.bySlot }, slots)}</td></tr>`;
      }).join('') || '<tr><td colspan="6">找不到符合條件的跑者</td></tr>';
    }

    function fillRunnerQualification() {
      const r = REPORT.runnerQualification;
      if (!r) return;
      $('runner-section').hidden = false;
      const slotValues = Object.values(r.thresholds.bySlot);
      $('runner-threshold-min').textContent = slotValues.length ? pct(Math.min(...slotValues)) : '無資料';
      $('runner-threshold-max').textContent = slotValues.length ? pct(Math.max(...slotValues)) : '無資料';
      $('runner-season-label').textContent = `${r.year} 年`;
      $('runner-min-attempts').textContent = r.minAttempts;
      $('runner-min-attempts-note').textContent = `嘗試 < ${r.minAttempts} 次`;
      $('runner-count-all').textContent = (r.tierCounts['任一棒次都可跑'] || 0).toLocaleString();
      $('runner-count-depends').textContent = (r.tierCounts['視下一棒棒次而定'] || 0).toLocaleString();
      $('runner-count-none').textContent = (r.tierCounts['任一棒次都不建議跑'] || 0).toLocaleString();
      $('runner-count-insufficient').textContent = (r.tierCounts['樣本不足'] || 0).toLocaleString();
      $('runner-total-count').textContent = r.runners.length.toLocaleString();
      $('runner-unresolved-note').textContent = r.eventsUnresolved
        ? `另有 ${r.eventsUnresolved} 次盜壘事件無法解析出跑者身分，未列入統計。`
        : `全季 ${r.eventsTotal.toLocaleString()} 次一壘盜二壘事件全數成功解析出跑者身分。`;
      renderRunnerTable();
    }

    // ---- 代表情境：還原壓縮後的個案、搜尋與篩選 ----
    const CASES = (() => {
      const c = REPORT.cases;
      return c.rows.map((row, id) => {
        const o = { id };
        c.fields.forEach((key, j) => {
          const v = row[j];
          o[key] = j < c.strFields ? (v === null ? null : c.strings[v]) : v;
        });
        o.batterTypeQualified = Boolean(o.powerGroup);
        return o;
      });
    })();
    let currentCase = CASES[REPORT.defaultCase] || CASES[0];

    function caseLabel(c) {
      return `${c.hitter}｜第 ${c.lineup} 棒｜${c.inning} 局｜${teamZh(c.team)}（${teamZh(c.away)} vs ${teamZh(c.home)}）`;
    }

    function renderCase(c) {
      if (!c) return;
      currentCase = c;
      $('case-heading').textContent = `${c.hitter}｜第 ${c.lineup} 棒｜${c.inning} 局`;
      $('case-subheading').textContent = `${c.date} · 場次 ${c.game} · ${teamZh(c.away)} vs ${teamZh(c.home)} · 一壘跑者 ${c.runner || '未記錄'} · 投手 ${c.pitcher || '未記錄'}`;
      $('case-actual').textContent = outcomeLabel[c.actual] || c.actual;
      renderCaseTypeBadges(c);
      $('case-values').innerHTML = `<tr><td>${esc(c.hitter)}</td><td>${fmt(c.ModelVSuccess)}</td><td>${fmt(c.ModelVFailure)}</td><td>${fmt(c.ModelVNoSteal)}</td><td>${c.BreakEvenSuccessRate === null ? '無' : pct(c.BreakEvenSuccessRate)}</td><td>${fmt(c.ConditionalOutCostNoSteal)}</td><td>${fmt(c.ExpectedOutPenaltyNoSteal)}</td></tr>`;
      $('case-profile').innerHTML = `<tr><td>${esc(c.hitter)}</td><td>${Math.round(c.ProfilePA)}</td><td>${pct(c.ModelP_1B)}</td><td>${pct(c.ModelP_2B)}</td><td>${pct(c.ModelP_3B)}</td><td>${pct(c.ModelP_HR)}</td><td>${pct(c.ModelP_BB_HBP)}</td><td>${pct(c.ModelP_REACH)}</td><td>${pct(c.ModelP_OUT)}</td></tr>`;
      const threshold = c.BreakEvenSuccessRate === null ? REPORT.aggregate.medianThreshold : c.BreakEvenSuccessRate;
      $('success-rate').value = String(Math.min(100, Math.max(0, threshold * 100)));
      updateDecision(c);
    }

    function updateDecision(c = currentCase) {
      if (!c) return;
      const p = Number($('success-rate').value) / 100;
      const stealEV = p * c.ModelVSuccess + (1 - p) * c.ModelVFailure;
      const delta = stealEV - c.ModelVNoSteal;
      $('success-rate-value').textContent = pct(p);
      $('decision-label').textContent = delta >= 0 ? '這個成功率下：盜壘較有利' : '這個成功率下：不跑較有利';
      $('decision-math').textContent = `EV(盜壘) ${fmt(stealEV)} − EV(不跑) ${fmt(c.ModelVNoSteal)} = ${delta >= 0 ? '+' : ''}${fmt(delta)} 分`;
      $('decision-readout').className = `decision-readout ${delta >= 0 ? 'good' : 'bad'}`;
    }

    // 篩選器：選項由資料產生，標籤沿用分組名稱
    const FILTERS = [
      ['f-team', 'team', '全部球隊', (v) => teamZh(v)],
      ['f-actual', 'actual', '全部結果', (v) => (outcomeLabel[v] || v).replace('實際：', '')],
      ['f-slot', 'lineup', '全部棒次', (v) => `第 ${v} 棒`],
      ['f-inning', 'inning', '全部局數', (v) => `第 ${v} 局`],
      ['f-lineup', 'typicalLineupGroup', '不限', (v) => GROUP_LABELS[v] || v],
      ['f-power', 'powerGroup', '不限', (v) => GROUP_LABELS[v] || v],
      ['f-patience', 'patienceGroup', '不限', (v) => GROUP_LABELS[v] || v],
      ['f-obp', 'obpGroup', '不限', (v) => GROUP_LABELS[v] || v],
      ['f-contact', 'contactGroup', '不限', (v) => GROUP_LABELS[v] || v],
      ['f-tto', 'ttoGroup', '不限', (v) => GROUP_LABELS[v] || v],
    ];

    function fillFilterOptions() {
      FILTERS.forEach(([id, key, allLabel, labeler]) => {
        const values = [...new Set(CASES.map((c) => c[key]).filter((v) => v !== null && v !== undefined))];
        values.sort((a, b) => (typeof a === 'number' ? a - b : String(labeler(a)).localeCompare(String(labeler(b)), 'zh-Hant')));
        $(id).innerHTML = `<option value="">${allLabel}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(labeler(v))}</option>`).join('');
      });
    }

    function applyCaseFilters() {
      const query = $('case-search').value.trim().toLowerCase();
      const active = FILTERS.map(([id, key]) => [key, $(id).value]).filter(([, v]) => v !== '');
      const matches = CASES.filter((c) => {
        for (const [key, value] of active) if (String(c[key]) !== value) return false;
        if (!query) return true;
        const hay = `${c.hitter} ${c.team} ${teamZh(c.team)} ${c.away} ${teamZh(c.away)} ${c.home} ${teamZh(c.home)} ${c.game} ${c.date}`.toLowerCase();
        return hay.includes(query);
      });
      const LIMIT = 300;
      const shown = matches.slice(0, LIMIT);
      const cur = matches.find((c) => c.id === currentCase.id);
      if (cur && !shown.includes(cur)) shown.unshift(cur);
      $('case-count').textContent = matches.length
        ? `共 ${matches.length.toLocaleString()} 筆符合${matches.length > LIMIT ? `，清單只列前 ${LIMIT} 筆，請再縮小條件` : ''}`
        : '沒有符合的決策，請放寬條件';
      const select = $('case-select');
      select.innerHTML = shown.map((c) => `<option value="${c.id}">${esc(caseLabel(c))}</option>`).join('');
      const keep = shown.find((c) => c.id === currentCase.id);
      const target = keep || shown[0];
      if (target) {
        select.value = String(target.id);
        if (!keep) renderCase(target);
      }
    }

    function fillTakeaway() {
      const a = REPORT.aggregate;
      const attempts = a.outcomes.steal_success + a.outcomes.steal_failure;
      if (!attempts) return;
      const rate = a.outcomes.steal_success / attempts;
      const above = rate >= a.medianThreshold;
      $('key-takeaway').innerHTML = `<strong>重點：</strong>實際成功率 ${pct(rate)}（${attempts.toLocaleString()} 次嘗試）${above ? '高於' : '低於'}情境門檻中位數 ${pct(a.medianThreshold)}，${above ? '這個情境下盜壘整體划算；真正要看的是哪些棒次、哪些打者更適合跑，往下看。' : '整體而言，這個情境下盜壘不夠划算；往下看哪些棒次與打者例外。'}`;
    }

    function fillHandedness() {
      const h = REPORT.handedness;
      if (!h) return;
      $('handedness-section').hidden = false;
      const L = h.LHP, R = h.RHP;
      const gap = (R.successRate - L.successRate) * 100;
      $('handedness-cards').innerHTML = `
        <article class="stat"><small>對左投成功率</small><strong>${pct(L.successRate)}</strong><span>${L.success} 成功／${L.attempts} 次嘗試</span></article>
        <article class="stat"><small>對右投成功率</small><strong>${pct(R.successRate)}</strong><span>${R.success} 成功／${R.attempts} 次嘗試</span></article>
        <article class="stat"><small>成功率差距</small><strong>${gap >= 0 ? '+' : ''}${gap.toFixed(1)} pp</strong><span>右投減左投，單位為百分點</span></article>
        <article class="stat"><small>每球嘗試率（左／右）</small><strong>${pct(L.attemptRatePerPitch, 2)}／${pct(R.attemptRatePerPitch, 2)}</strong><span>一壘有人時，每球發動盜壘的比例</span></article>`;
      const thr = REPORT.aggregate.medianThreshold;
      const cmp = (name, row) => {
        const diff = row.successRate - thr;
        const rel = Math.abs(diff) < 0.01 ? '與' : (diff > 0 ? '高於' : '低於');
        return `${name}成功率 ${pct(row.successRate)} ${rel}門檻中位數${Math.abs(diff) < 0.01 ? '相當' : ''}`;
      };
      $('handedness-note').textContent = `對照門檻中位數 ${pct(thr)}：${cmp('對右投', R)}，${cmp('對左投', L)}。左投面對一壘跑者是正面朝向，牽制與起跑時機都比較難抓。`;
    }

    fillAggregate();
    fillTakeaway();
    fillValidation();
    fillTeamDecisions();
    fillSegments();
    fillRunnerQualification();
    fillHandedness();
    $('runner-search').addEventListener('input', renderRunnerTable);
    $('runner-filter').addEventListener('change', renderRunnerTable);
    fillFilterOptions();
    applyCaseFilters();
    $('case-select').value = String(currentCase.id);
    renderCase(currentCase);
    $('case-search').addEventListener('input', applyCaseFilters);
    FILTERS.forEach(([id]) => $(id).addEventListener('change', applyCaseFilters));
    $('f-clear').addEventListener('click', () => {
      $('case-search').value = '';
      FILTERS.forEach(([id]) => { $(id).value = ''; });
      applyCaseFilters();
    });
    $('case-select').addEventListener('change', (event) => renderCase(CASES[Number(event.target.value)]));
    $('success-rate').addEventListener('input', () => updateDecision());
