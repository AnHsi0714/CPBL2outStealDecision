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
    const teamTag = (name) => {
      const color = TEAM_COLORS[name];
      const dot = color ? `<span class="team-dot" style="background:${color}"></span>` : '';
      return `${dot}${esc(name)}`;
    };

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

      const maxMedian = Math.max(...segments.lineupSlots.map((s) => s.median ?? 0));
      $('lineup-bars').innerHTML = segments.lineupSlots.map((s) => `
        <div class="bar-row">
          <span>第 ${s.slot} 棒</span>
          <div class="track"><div class="bar neutral" style="width:${maxMedian ? (s.median / maxMedian) * 100 : 0}%"></div></div>
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

    fillAggregate();
    fillValidation();
    fillTeamDecisions();
    fillSegments();
    fillRunnerQualification();
    $('runner-search').addEventListener('input', renderRunnerTable);
    $('runner-filter').addEventListener('change', renderRunnerTable);
