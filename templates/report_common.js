(function () {
  'use strict';
  var doc = document;
  var embedded = window.parent !== window;

  /* ---------- 專有名詞提示 ---------- */
  var G = {
    '單調性違反': '分差對進攻方愈有利，勝率理應愈高；這是違反這個規律的格子數，越少越好（多半來自樣本太少）',
    '目標情境涵蓋度': '盜壘決策最常遇到的情境（2 出局、一二壘有人、第 7–8 局）中，樣本數足夠的格子比例',
    '決策當下為該棒次先發打者': '決策時站在打擊區的是該棒次的先發球員，不是代打或換人',
    '代打／換人後才上場': '決策時站在打擊區的是代打或換人後才上場的球員',
    '代打比例最高的棒次': '該棒次的決策中，非先發球員的比例最高',
    'N': '樣本數：這個格子實際觀測到的次數，越少數字越不穩定',
    'n': '樣本數：這個格子實際觀測到的次數，越少數字越不穩定',
    'SD': '標準差：同一局面下得分的分散程度，越大代表結果越難預測',
    '平均 RE': 'RE（得分期望值）：從這個局面起算，到半局結束平均還能再拿幾分',
    '出局數': '目前有幾人出局',
    '壘包狀態': '目前壘上有誰',
    '勝率': '進攻方最後贏下這場比賽的機率',
    '分差': '進攻方領先（正）或落後（負）的分數',
    '局': '第幾局',
    '年度': '球季',
    'V成功': '盜壘成功時的價值：得分版是期望得分，勝率版是贏球機率',
    'V失敗': '盜壘失敗時的價值：跑者出局、半局結束，該打者下一局先打',
    'V不跑': '不盜壘、讓打者正常打完打席時的價值',
    '損益兩平': '盜壘成功率至少要達到這個數字才划算：(V不跑 − V失敗) ÷ (V成功 − V失敗)',
    '出局成本': '打者出局相對於沒出局，少掉的期望得分',
    '期望出局懲罰': '出局成本 × 該打者的出局率，也就是平均每次打席因出局損失的期望得分',
    '條件式出局成本': '打者出局相對於沒出局，少掉的期望得分',
    '保留打者平均差異': '盜壘失敗後同一打者下一局先打，相對於正常出局由下一棒開局的期望得分差',
    '平滑先驗': '打席少的打者先用聯盟平均補上這麼多打席再算機率，避免數字被少量打席帶偏',
    '情境損益兩平中位數': '每個情境各自算出損益兩平成功率，再取中位數',
    '符合條件的決策機會': '第 1–8 局、2 出局、僅一壘有人的情境數',
    '實際盜壘成功': '這些情境中，跑者實際發動並成功盜壘的次數',
    '實際盜壘失敗': '這些情境中，跑者實際發動但被刺殺的次數',
    '此情境': '這筆決策的打者',
    '打者模型': '這位打者的個人打擊結果機率（已用聯盟平均平滑）',
    'PA': '打席數（Plate Appearances）',
    '1B': '單安打機率',
    '2B': '二壘安打機率',
    '3B': '三壘安打機率',
    'HR': '全壘打機率',
    'BB/HBP': '保送與觸身球機率',
    '其他上壘': '因失誤等其他方式上壘的機率',
    'OUT': '出局機率',
    '比較': '兩組打者門檻中位數的比較',
    '組一': '第一組的門檻中位數與樣本數（n）',
    '組二': '第二組的門檻中位數與樣本數（n）',
    '差異（組一－組二）': '兩組門檻中位數相差幾個百分點',
    'p 值（Mann-Whitney U）': '兩組差異只是巧合的機率，越小越不像巧合，低於 0.05 通常視為顯著。Mann-Whitney U 是不假設常態分布的檢定',
    '球隊': '球隊',
    '決策機會': '該隊兩出局、一壘有人的情境數（不論有沒有跑）',
    '盜壘嘗試': '實際發動盜壘的次數',
    '嘗試': '實際發動盜壘的次數',
    '實際成功率': '嘗試次數中成功的比例',
    '成功率': '嘗試次數中成功的比例',
    '95% 信賴區間': '重複抽樣下，真實值有 95% 機會落在的範圍',
    '該隊門檻': '該隊所有決策機會的損益兩平門檻中位數',
    'p 值': '實際成功率與門檻的差異只是巧合的機率，低於 0.05 才判定跑對或跑錯',
    '判定': '成功率顯著高於門檻判跑對，顯著低於判跑錯，其餘標無法判定',
    '棒次': '打者排在打線第幾棒',
    '跑者': '一壘上的跑者',
    'RE 門檻中位數': '用得分期望值（RE）算出的損益兩平門檻中位數',
    'WPA 門檻中位數': '用勝率增值（WPA）算出的損益兩平門檻中位數',
    'WPA 95% CI': '勝率版門檻中位數的 95% 信賴區間',
    '與 RE 重疊': '勝率版信賴區間是否碰到得分版門檻；沒重疊代表兩者差異不是雜訊',
    'RE 成功率': '該跑者的實際盜壘成功率',
    '嘗試次數': '實際發動盜壘的次數',
    'WPA 下夠格的局數': '用勝率版門檻重新判定，成功率達標的局數',
    '1–9 棒：可跑（綠）／不建議（紅）': '依該跑者成功率逐棒次比對門檻，綠色表示成功率達標',
    '任一棒次都可跑': '成功率高過全部 9 個棒次的門檻',
    '視下一棒棒次而定': '部分棒次的門檻達標，部分不達標',
    '任一棒次都不建議跑': '連門檻最低的棒次都沒達標',
    '樣本不足': '嘗試次數太少，不做判定'
  };
  var P = [
    [/^\d+ · 盜壘成功/, '盜壘成功的路線：跑者上二壘，打者繼續打席，模擬到下一個進攻半局結束'],
    [/^\d+ · 盜壘失敗/, '盜壘失敗的路線：跑者成為第三個出局，半局立刻結束，打者留到下一局先打'],
    [/^\d+ · 不盜壘/, '不盜壘的路線：維持兩出局、一壘有人，打者正常打完打席，若出局則下一局由下一棒開始'],
    [/^盜壘損益兩平成功率/, '盜壘成功率至少要達到這個數字才划算，低於它不如不跑'],
    [/無類型資料/, '打席數不足 100，無法歸類打者類型'],
    [/^低樣本格/, '樣本數低於門檻的格子，數字雜訊較大，解讀時要保守'],
    [/RE\(一壘\)／RE\(二壘\)/, '不含打者個人差異與保留效應的基礎損益兩平門檻：RE(一壘) ÷ RE(二壘)'],
    [/(領先|落後) 1 分時的勝率/, '該局進攻方領先（或落後）1 分時最後贏球的機率，用來看一分的份量隨局數變重'],
    [/^模擬 vs 真實 RE24/, 'r 是相關係數，越接近 1 代表模擬的 RE24 與真實比賽越吻合；誤差單位是分'],
    [/^盜壘文字判讀/, '把文字紀錄判讀出的盜壘成功與刺殺，與官方統計逐場逐隊比對'],
    [/^高長打/, 'ISO（長打率 − 打擊率）高於聯盟中位數的打者'],
    [/^低長打/, 'ISO（長打率 − 打擊率）低於聯盟中位數的打者'],
    [/^高選球/, '保送與觸身率（BB%）高於聯盟中位數的打者'],
    [/^低選球/, '保送與觸身率（BB%）低於聯盟中位數的打者'],
    [/^高上壘率/, '真上壘率（OBP，安打＋保送）高於聯盟中位數的打者'],
    [/^低上壘率/, '真上壘率（OBP，安打＋保送）低於聯盟中位數的打者'],
    [/^高單打率/, '單打占打席比例高於聯盟中位數，靠單打上壘的接觸型打者'],
    [/^低單打率/, '單打占打席比例低於聯盟中位數的打者'],
    [/^高\s*TTO/, 'TTO（三振＋全壘打＋保送）機率合計高於聯盟中位數，打席結果較不受守備影響'],
    [/^低\s*TTO/, 'TTO（三振＋全壘打＋保送）機率合計低於聯盟中位數'],
    [/^前段/, '該打者最常排在打線第 1–5 棒'],
    [/^後段/, '該打者最常排在打線第 6–9 棒'],
    [/^實際：盜壘成功/, '這筆決策實際發生的結果'],
    [/^實際：盜壘失敗/, '這筆決策實際發生的結果'],
    [/^實際：不盜壘/, '這筆決策實際發生的結果'],
    [/ISO.*選球|BB%|OBP|單打率|TTO|長打/, '打者類型分組的比較：以聯盟中位數把打者切成高低兩組，比較兩組的門檻中位數']
  ];
  function lookup(text) {
    text = text.replace(/\s+/g, ' ').trim();
    if (!text) return null;
    if (Object.prototype.hasOwnProperty.call(G, text)) return G[text];
    for (var i = 0; i < P.length; i++) if (P[i][0].test(text)) return P[i][1];
    return null;
  }
  var tipEl = null;
  function ensureTip() {
    if (!tipEl) {
      tipEl = doc.createElement('div');
      tipEl.className = 'rc-tip';
      tipEl.setAttribute('role', 'tooltip');
      doc.body.appendChild(tipEl);
    }
    return tipEl;
  }
  var TIP_TARGETS = 'th, .stat small, .pill, #segment-table td:first-child, .branch-head h3, .formula > strong';
  var currentTarget = null;
  doc.addEventListener('mouseover', function (e) {
    var t = e.target.closest && e.target.closest(TIP_TARGETS);
    if (!t || t === currentTarget) return;
    var text = lookup(t.textContent);
    if (!text) return;
    currentTarget = t;
    var tip = ensureTip();
    tip.textContent = text;
    var r = t.getBoundingClientRect();
    tip.style.left = '0px'; tip.style.top = '0px';
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    var top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 8);
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    tip.classList.add('show');
  });
  doc.addEventListener('mouseout', function (e) {
    if (!currentTarget) return;
    var to = e.relatedTarget;
    if (to && currentTarget.contains(to)) return;
    currentTarget = null;
    if (tipEl) tipEl.classList.remove('show');
  });
  doc.addEventListener('scroll', function () { if (tipEl) tipEl.classList.remove('show'); currentTarget = null; }, true);

  /* ---------- 目錄（漢堡按鈕＋側邊抽屜） ---------- */
  function mountToc(items, opts) {
    opts = opts || {};
    var old = doc.getElementById('rc-toc-root');
    if (old) old.remove();
    var oldBtn = doc.querySelector('.rc-btn.inline');
    if (oldBtn) oldBtn.remove();
    doc.documentElement.classList.remove('rc-toc-open');
    var root = doc.createElement('div');
    root.id = 'rc-toc-root';
    var btn = doc.createElement('button');
    btn.type = 'button';
    btn.className = 'rc-btn';
    btn.setAttribute('aria-label', '目錄');
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-controls', 'rc-drawer');
    btn.setAttribute('data-tip', '目錄');
    btn.innerHTML = '<span class="rc-icon"></span>';
    if (opts.top) btn.style.setProperty('--rc-top', opts.top);
    var scrim = doc.createElement('div');
    scrim.className = 'rc-scrim';
    var drawer = doc.createElement('nav');
    drawer.className = 'rc-drawer';
    drawer.id = 'rc-drawer';
    drawer.setAttribute('aria-label', '目錄');
    drawer.innerHTML = '<h2>目錄</h2>' + items.map(function (it) {
      return '<a href="#' + it.id + '" data-id="' + it.id + '">' + it.title.replace(/[&<>]/g, '') + '</a>';
    }).join('');
    root.appendChild(scrim); root.appendChild(drawer);
    doc.body.appendChild(root);
    if (opts.inline) { btn.classList.add('inline'); opts.inline.insertBefore(btn, opts.inline.firstChild); }
    else root.insertBefore(btn, root.firstChild);
    function set(open) {
      drawer.classList.toggle('open', open);
      scrim.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      doc.documentElement.classList.toggle('rc-toc-open', open);
    }
    btn.addEventListener('click', function () { set(!drawer.classList.contains('open')); });
    scrim.addEventListener('click', function () { set(false); });
    doc.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
    drawer.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      e.preventDefault();
      set(false);
      if (opts.onGo) opts.onGo(a.getAttribute('data-id'));
    });
    return {
      setActive: function (id) {
        drawer.querySelectorAll('a').forEach(function (a) {
          if (a.getAttribute('data-id') === id) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
        });
      }
    };
  }
  window.ReportCommon = { mountToc: mountToc };

  /* ---------- 以下只在報告頁（有 main section）執行 ---------- */
  function sections() {
    return [].filter.call(doc.querySelectorAll('main section[aria-labelledby]'), function (s) { return !s.hidden && s.offsetParent !== null; });
  }
  if (!doc.querySelector('main section[aria-labelledby]')) return;

  function secTop(sec) { return sec.getBoundingClientRect().top + window.scrollY; }
  function anchorAt(y) {
    var found = null;
    sections().forEach(function (sec) {
      var top = secTop(sec);
      if (top <= y + 80) found = { id: sec.getAttribute('aria-labelledby'), offset: y - top };
    });
    return { y: y, section: found };
  }
  function tocItems() {
    return sections().map(function (sec) {
      var h = doc.getElementById(sec.getAttribute('aria-labelledby'));
      return { id: sec.getAttribute('aria-labelledby'), title: (h ? h.textContent : '').trim() };
    }).filter(function (it) { return it.title; });
  }
  function scrollable() { return doc.documentElement.scrollHeight > window.innerHeight + 2; }
  function targetY(a) {
    if (a.section) {
      var h = doc.getElementById(a.section.id);
      var sec = h && h.closest('section');
      if (sec && !sec.hidden) return Math.max(0, secTop(sec) + Math.min(a.section.offset, sec.offsetHeight - 80));
    }
    return a.y;
  }
  function post(msg) { parent.postMessage(msg, '*'); }
  function goTo(y) {
    if (scrollable() || !embedded) window.scrollTo(0, y); else post({ type: 'report-scroll-to', y: y });
  }

  var toc = null;
  if (!embedded) {
    toc = mountToc(tocItems(), {
      onGo: function (id) {
        var h = doc.getElementById(id), sec = h && h.closest('section');
        if (sec) window.scrollTo({ top: secTop(sec) - 8, behavior: 'smooth' });
      }
    });
  }
  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    setTimeout(function () {
      ticking = false;
      var a = anchorAt(window.scrollY);
      if (toc) toc.setActive(a.section && a.section.id);
      if (embedded) post({ type: 'report-anchor', anchor: a });
    }, 50);
  });
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || !embedded) return;
    if (d.type === 'report-restore' && d.anchor) {
      var go = function () { goTo(targetY(d.anchor)); };
      go();
      setTimeout(go, 150);
    } else if (d.type === 'report-query') {
      post({ type: 'report-anchor', anchor: anchorAt(d.y) });
    } else if (d.type === 'report-goto') {
      var h = doc.getElementById(d.id), sec = h && h.closest('section');
      if (sec) {
        if (scrollable()) window.scrollTo({ top: secTop(sec) - 8, behavior: 'smooth' });
        else post({ type: 'report-scroll-to', y: secTop(sec) - 8 });
      }
    }
  });
  if (embedded) {
    var lastH = 0;
    var sendHeight = function () {
      var h = doc.documentElement.scrollHeight;
      if (Math.abs(h - lastH) > 2) { lastH = h; post({ type: 'report-height', height: h }); }
    };
    if ('ResizeObserver' in window) new ResizeObserver(sendHeight).observe(doc.body);
    window.addEventListener('load', sendHeight);
    post({ type: 'report-ready', items: tocItems(), height: doc.documentElement.scrollHeight });
  }

  /* 報告內的「看某分類」連結：嵌在入口頁時請入口頁切換分頁，單獨開啟時照一般連結走 */
  doc.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-category]');
    if (!a || !embedded) return;
    e.preventDefault();
    post({ type: 'report-goto-category', id: a.getAttribute('data-category') });
  });

  /* ---------- 區塊與長條：第一次捲動到時才播放進場動畫 ---------- */
  if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var fired = false;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      fired = true;
      entry.target.classList.add('in');
      io.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0 });
  doc.querySelectorAll('main section').forEach(function (el) { el.classList.add('reveal'); io.observe(el); });
  doc.querySelectorAll('.bar').forEach(function (el) { el.classList.add('barr'); io.observe(el); });
  doc.documentElement.classList.add('js-reveal');
  // 保險：觀察器一直沒有回報（例如被瀏覽器節流）時，直接顯示全部內容，避免頁面空白。
  setTimeout(function () { if (!fired) doc.documentElement.classList.remove('js-reveal'); }, 1500);
})();
