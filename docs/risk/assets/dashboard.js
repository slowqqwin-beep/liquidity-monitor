/* =====================================================
   Risk Evolution Dashboard — Event-Driven Logic  v2
   Data source: event_state.json (from risk_dashboard MD)
   Fixes: clear placeholders, GH Pages paths, field validation, fallback
   ===================================================== */

// ── BASE path for GH Pages subdirectory compatibility ──
const BASE = (() => {
  const p = location.pathname;
  // Detect known GitHub Pages repo names
  if (p.includes('/liquidity-monitor/')) return '/liquidity-monitor/risk/';
  if (p.includes('/hibor-dashboard/'))  return '/hibor-dashboard/risk/';
  return './';
})();

// ── Color map ──
const C = {
  ink:      '#e8e6e1',
  mute:     '#9a988f',
  deep:     '#6a6862',
  good:     '#6dd3a3',
  stress:   '#e08363',
  gold:     '#d4a657',
  data:     '#87a4c4',
  violet:   '#b094c8',
  amber:    '#d6b37c',
  orange:   '#e8a848',
};

/* ==================================================================
   DATA LOADING — multiple fallback paths
   ================================================================== */

async function loadEventState() {
  const today = new Date().toISOString().slice(0, 10);
  const paths = [
    `${BASE}assets/event_state.json`,
    `${BASE}assets/event_state_${today}.json`,
    `assets/event_state.json`,
    `assets/event_state_${today}.json`,
  ];

  for (const url of paths) {
    try {
      const resp = await fetch(url);
      if (resp.ok) {
        console.log('[dashboard] loaded:', url);
        return resp.json();
      }
    } catch (e) {
      console.warn('[dashboard] fetch failed:', url, e.message);
    }
  }

  console.error('[dashboard] All fetch paths failed. Tried:', paths);
  return null;
}

/* ==================================================================
   FIELD VALIDATION
   ================================================================== */

function validateEventState(es) {
  if (!es) return { valid: false, missing: ['root: null/undefined'] };

  const topRequired = ['date', 'regime', 'event_state', 'transmission_state', 'trigger_state', 'stage_assessment'];
  const missing = topRequired.filter(k => es[k] === undefined || es[k] === null);

  // Substructure checks
  const subChecks = {
    'event_state':        ['near_event_active', 'front_risk_label', 'front_risk_intensity'],
    'transmission_state': ['rate_shock_active', 'real_yield_pressure'],
    'trigger_state':      ['credit_trigger', 'liquidity_trigger', 'cross_asset_trigger', 'any_triggered', 'all_triggered'],
    'stage_assessment':   ['current_stage', 'final_judgement'],
  };

  for (const [key, subs] of Object.entries(subChecks)) {
    const obj = es[key];
    if (obj === undefined || obj === null) continue;
    for (const sub of subs) {
      if (obj[sub] === undefined) missing.push(`${key}.${sub}`);
    }
  }

  return { valid: missing.length === 0, missing };
}

/* ==================================================================
   HELPERS
   ================================================================== */

const fmtNum = (n, dp) =>
  n == null || isNaN(n) ? '—' : Number(n).toLocaleString('en-US', {
    minimumFractionDigits: dp, maximumFractionDigits: dp,
  });

function lightColor(state) {
  if (state === 'red' || state === 'stress')  return C.stress;
  if (state === 'orange' || state === 'partial') return C.orange;
  if (state === 'green' || state === 'good')   return C.good;
  if (state === 'gold') return C.gold;
  return C.mute;
}

function lightLabel(state, text) {
  return `<span style="color:${lightColor(state)}">${text}</span>`;
}

/** Clear a grid by ID, removing all placeholder children. */
function clearGrid(id) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = '';
}

/** Show a single fallback card inside a grid. */
function showGridFallback(gridId, msg) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  grid.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'card fallback-card';
  card.innerHTML = `<div class="card-label fallback-label">${msg}</div>`;
  grid.appendChild(card);
}

/** Show fallback line for conclusion sections inline. */
function showFallback(elId, msg) {
  const el = document.getElementById(elId);
  if (el) el.textContent = msg;
}

/* ==================================================================
   MASTHEAD
   ================================================================== */

function renderMasthead(es) {
  const regime = es.regime || '—';
  const date   = es.date   || '—';
  const pos    = es.positions || {};
  const stage  = es.stage_assessment || {};
  const cross  = es.cross_domain_signals ?? '—';
  const red    = es.red_count ?? '—';

  document.getElementById('mast-date').textContent   = date;
  document.getElementById('mast-regime').textContent  = regime;
  document.getElementById('mast-cross').textContent   = cross;
  document.getElementById('mast-red').textContent     = red;

  document.getElementById('pos-primary').textContent = pos.primary || '—';
  document.getElementById('pos-hedge').textContent   = pos.hedge   || '—';
  document.getElementById('pos-cash').textContent    = pos.cash    || '—';

  const conclusion = document.getElementById('hero-conclusion');

  // ── NOT-SYSTEMIC guard: if final_judgement or risk_character says "非系统性",
  //     never output "系统性风险" as the current conclusion ──
  let notYet = stage.not_yet_stage || '—';
  const fj = (stage.final_judgement || '') + (stage.risk_character || '');
  if (/非系统/.test(fj) && /系统/.test(notYet)) {
    notYet = '尚未进入系统性风险';
  }
  conclusion.textContent = `${regime}：${stage.current_stage || ''}，${notYet}。`;
}

/* ==================================================================
   ROW 1 — FIVE CORE CARDS
   ================================================================== */

function renderCoreCards(es) {
  const grid = document.getElementById('core-cards');
  if (!grid) return;
  clearGrid('core-cards');

  const v = validateEventState(es);
  if (!es.event_state || !es.transmission_state) {
    showGridFallback('core-cards',
      v.valid ? '—' : `核心信号数据缺失：${v.missing.filter(m => m.startsWith('event_state') || m.startsWith('transmission_state')).join('，') || 'event_state / transmission_state 不可用'}`);
    return;
  }

  const ev = es.event_state || {};
  const tr = es.transmission_state || {};
  const tg = es.trigger_state || {};
  const st = es.stage_assessment || {};

  // 1 — 近端事件风险
  buildCard(grid, {
    accent: ev.front_risk_intensity === 'orange' ? 'stress-left glow-stress' : 'good-left',
    light:  ev.front_risk_intensity === 'orange' ? 'red' : 'green',
    label:  '近端事件风险',
    status: ev.front_risk_label || '—',
    statusColor: ev.front_risk_intensity === 'orange' ? 'stress' : 'good',
    detail: ev.near_event_active
      ? `VIX9D/VIX=${ev.evidence?.vix9d_vix_ratio || '—'}，${(ev.event_sources || []).join('；')}`
      : '无近端事件信号',
  });

  // 2 — 实际利率 / 估值挤压（独立卡片）
  const dfii10   = tr.evidence?.dfii10_pct;
  const nowcast  = tr.evidence?.real_yield_nowcast;
  const realActive = tr.real_yield_pressure;
  buildCard(grid, {
    accent: realActive ? 'stress-left glow-stress' : 'good-left',
    light:  realActive ? 'red' : 'green',
    label:  '实际利率 / 估值挤压',
    value:  dfii10 != null ? `DFII10 ${dfii10}%` : '—',
    status: realActive ? '🔴 高压 · 估值压缩' : '○ 正常区间',
    statusColor: realActive ? 'stress' : 'good',
    detail: `Real Yield Nowcast ${nowcast != null ? nowcast + '%' : '—'}${realActive ? ' — 贴现率持续压制估值' : ''}`,
  });

  // 3 — 第一层传导
  const mainPath = tr.main_path || '';
  buildCard(grid, {
    accent: tr.rate_shock_active ? 'orange-left glow-orange' : '',
    light:  tr.rate_shock_active ? 'orange' : 'green',
    label:  '第一层传导',
    status: tr.rate_shock_active ? '活跃传导' : '无显著传导',
    statusColor: tr.rate_shock_active ? 'orange' : 'mute',
    detail: mainPath ? `${mainPath}\n${tr.summary || ''}` : '四端无显著传导压力',
  });

  // 4 — 系统性风险触发器
  const triggered = [
    tg.credit_trigger?.active ? 'T1' : null,
    tg.liquidity_trigger?.active ? 'T2' : null,
    tg.cross_asset_trigger?.active ? 'T3' : null,
  ].filter(Boolean);
  const trigSummary = triggered.length > 0 ? `${triggered.join('+')} 已触发` : '三重皆未触发';
  const trigColor = tg.all_triggered ? 'stress' : tg.any_triggered ? 'orange' : 'good';
  buildCard(grid, {
    accent: trigColor === 'stress' ? 'stress-left glow-stress'
          : trigColor === 'orange' ? 'orange-left glow-orange' : 'good-left',
    light:  trigColor,
    label:  '系统性风险触发器',
    status: trigSummary,
    statusColor: trigColor,
    detail: `T1信用:${tg.credit_trigger?.label || '—'} / T2流动:${tg.liquidity_trigger?.label || '—'} / T3跨资产:${tg.cross_asset_trigger?.label || '—'}`,
  });

  // 5 — 当前阶段判断
  buildCard(grid, {
    accent: 'accent-left glow-gold',
    light:  'gold',
    label:  '当前阶段判断',
    status: st.current_stage || '—',
    statusColor: 'gold',
    detail: st.final_judgement
      ? st.final_judgement.slice(0, 140) + (st.final_judgement.length > 140 ? '…' : '')
      : '—',
  });
}

function buildCard(grid, opts) {
  const card = document.createElement('div');
  card.className = `card ${opts.accent || ''}`;

  let html = '';
  if (opts.light) {
    html += `<div class="card-light ${opts.light}"></div>`;
  }
  html += `<div class="card-label">${opts.label}</div>`;
  if (opts.value) {
    html += `<div class="card-value">${opts.value}</div>`;
  }
  html += `<div class="card-status ${opts.statusColor || 'mute'}">${opts.status || ''}</div>`;
  html += `<div class="card-detail">${(opts.detail || '').replace(/\n/g, '<br>')}</div>`;

  card.innerHTML = html;
  grid.appendChild(card);
}

/* ==================================================================
   ROW 2 — FOUR AUXILIARY CARDS
   ================================================================== */

function renderAuxCards(es) {
  const grid = document.getElementById('aux-cards');
  if (!grid) return;
  clearGrid('aux-cards');

  if (!es.transmission_state || !es.trigger_state) {
    showGridFallback('aux-cards', '辅助判断数据缺失：transmission_state / trigger_state 不可用');
    return;
  }

  const tr = es.transmission_state || {};
  const tg = es.trigger_state || {};

  // Fed鸽派 / 流动性缓冲
  const buffText = tr.rate_shock_active
    ? '鸽派缓冲存在，但不能抵消实际利率高压'
    : '流动性缓冲充裕，Fed尚有空间';
  buildCard(grid, {
    accent: tr.rate_shock_active ? 'orange-left' : 'good-left',
    label: 'Fed鸽派 / 流动性缓冲',
    status: tr.rate_shock_active ? '缓冲存在·被高压盖过' : '缓冲充裕',
    statusColor: tr.rate_shock_active ? 'orange' : 'good',
    detail: buffText,
  });

  // 资产反应链
  const vts = (es.stage_assessment?.evidence?.vts_regime) || 'contango';
  const rcv = es.stage_assessment?.evidence?.rcv_tilt || '—';
  buildCard(grid, {
    label: '资产反应链',
    status: `VTS=${vts} · RCV tilt=${rcv}`,
    statusColor: vts === 'backwardated' ? 'stress' : 'mute',
    detail: vts === 'backwardated'
      ? '⚠️ VTS倒挂 — 远期对冲成本急剧上升'
      : '近端事件主导，远期结构正常',
  });

  // 抄底条件
  let dipText;
  if (tg.all_triggered) {
    dipText = '❌ 三重触发器全亮 — 不抄底，等risk-off结束';
  } else if (!tg.any_triggered) {
    dipText = '✅ 三重触发器全灭 — 结构性支撑完好，逢低可考虑';
  } else {
    dipText = '⚠️ 部分触发 — 仅轻仓试探，等T1信用转绿';
  }
  buildCard(grid, {
    label: '重新考虑抄底的条件',
    status: tg.all_triggered ? '暂不考虑' : tg.any_triggered ? '轻仓试探' : '逢低可考虑',
    statusColor: tg.all_triggered ? 'stress' : tg.any_triggered ? 'orange' : 'good',
    detail: dipText,
  });

  // 下一步观察点
  const watches = (es.stage_assessment?.next_watch || []).slice(0, 3);
  const watchLines = watches.length > 0
    ? watches.map((w, i) => `${i + 1}. ${w}`).join('\n')
    : '等待新信号';
  buildCard(grid, {
    accent: 'accent-left',
    label: '下一步观察点',
    detail: watchLines,
  });
}

/* ==================================================================
   ROW 3 — TRIGGER EXPANSION CARDS
   ================================================================== */

function renderTriggerCards(es) {
  const grid = document.getElementById('trigger-cards');
  if (!grid) return;
  clearGrid('trigger-cards');

  const tg = es.trigger_state;
  if (!tg || !tg.credit_trigger) {
    showGridFallback('trigger-cards', '触发器数据缺失：trigger_state 不可用');
    return;
  }

  buildTriggerCard(grid, {
    id: 'T1', name: 'T1 信用 (B端)',
    condition: 'HY OAS > 300bp 或 IG OAS > 85bp',
    active: tg.credit_trigger?.active || false,
    label: tg.credit_trigger?.label || '未触发',
    evidence: tg.credit_trigger?.evidence || '—',
  });

  const t2 = tg.liquidity_trigger || {};
  buildTriggerCard(grid, {
    id: 'T2', name: 'T2 流动性 (A端)',
    condition: 'EFFR–IORB > −3bp + DUR5 ≥ 5',
    active: t2.active || false,
    partial: t2.partial || false,
    label: t2.label || '未触发',
    evidence: t2.evidence || '—',
  });

  buildTriggerCard(grid, {
    id: 'T3', name: 'T3 跨资产 / 跨境',
    condition: 'CASC ≥ 2 + VTS + RCV 互锁',
    active: tg.cross_asset_trigger?.active || false,
    label: tg.cross_asset_trigger?.label || '未触发',
    evidence: tg.cross_asset_trigger?.evidence || '—',
  });
}

function buildTriggerCard(grid, opts) {
  const card = document.createElement('div');
  card.className = 'trigger-card';

  let stateClass = 'good';
  if (opts.partial) stateClass = 'orange';
  else if (opts.active) stateClass = 'stress';

  card.innerHTML = `
    <div class="trigger-header">
      <span class="trigger-badge ${stateClass}">${opts.label}</span>
      <span class="trigger-name">${opts.name}</span>
    </div>
    <div class="trigger-condition">条件：${opts.condition}</div>
    <div class="trigger-evidence">${opts.evidence}</div>
  `;
  grid.appendChild(card);
}

/* ==================================================================
   ROW 4 — AUTO-INTERPRETATION
   ================================================================== */

function renderInterpretation(es) {
  const grid = document.getElementById('interp-cards');
  if (!grid) return;
  clearGrid('interp-cards');

  // ── Validate required fields ──
  const ev = es.event_state;
  const tr = es.transmission_state;
  const tg = es.trigger_state;
  const st = es.stage_assessment;

  if (!ev || !tr || !tg || !st) {
    const missing = [];
    if (!ev) missing.push('event_state');
    if (!tr) missing.push('transmission_state');
    if (!tg) missing.push('trigger_state');
    if (!st) missing.push('stage_assessment');
    showGridFallback('interp-cards',
      `解读数据缺失：缺少 ${missing.join('、')}。请检查 event_state.json 是否由 extract_risk_events.py 生成。`);
    return;
  }

  if (ev.near_event_active === undefined && !st.current_stage) {
    showGridFallback('interp-cards',
      '解读数据缺失：near_event_active 和 current_stage 均为空。请检查 event_state.json 是否生成。');
    return;
  }

  const items = [
    { title: '为什么当前是近端事件风险？',   body: _whyNearEvent(ev, st) },
    { title: '为什么尚非系统性？',           body: _whyNotSystemic(ev, tg, st) },
    { title: '实际利率为何是主矛盾？',       body: _whyRealYield(tr) },
    { title: '哪些变化会推动升级？',         body: _whatUpgrades(st) },
  ];

  items.forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'interp-card';
    div.innerHTML = `
      <div class="interp-num">${i + 1}</div>
      <div class="interp-body">
        <h4>${item.title}</h4>
        <p>${item.body}</p>
      </div>
    `;
    grid.appendChild(div);
  });
}

function _whyNearEvent(ev, st) {
  const ratio   = ev.evidence?.vix9d_vix_ratio;
  const confirm = ev.evidence?.cross_asset_confirm;
  const dgs2    = ev.evidence?.dgs2_iorb_bp;
  if (ratio != null && ratio > 0.95 && confirm === 0) {
    return `前端VIX9D/VIX=${ratio}偏紧，VIX曲线前端陡峭，但跨资产确认=${confirm}/4 — 无广泛传染信号。${dgs2 != null ? `DGS2−IORB=${dgs2}bp，市场在定价具体近端利率事件而非系统性恐慌。` : ''}`;
  }
  return `当前市场信号集中在前端利率预期调整上，近端事件（FOMC/CPI）是主要定价因素，尚未扩散为广泛风险规避。`;
}

function _whyNotSystemic(ev, tg, st) {
  const creditOk  = !tg.credit_trigger?.active;
  const crossOk   = !tg.cross_asset_trigger?.active;
  const vts       = st.evidence?.vts_regime || 'contango';
  if (creditOk && crossOk) {
    return `三重触发器中，信用端（T1）仍在自满区，跨资产端（T3）未触发。仅流动性端（T2）出现部分压力，不符合系统性风险"三端同亮"的定义。VTS=${vts}，远期结构正常，非危机定价。`;
  }
  return `当前触发信号不足以确认系统性风险转换。`;
}

function _whyRealYield(tr) {
  const dfii = tr.evidence?.dfii10_pct;
  const nc   = tr.evidence?.real_yield_nowcast;
  if (dfii != null && dfii > 2.0) {
    return `DFII10=${dfii}%远高于2.0%舒适区，实际利率直接压制定价模型分母端。${nc != null ? `Real Yield Nowcast=${nc}%确认这一趋势。` : ''}在高实际利率环境下，所有风险资产的现值都被系统性压缩，这是当前最核心的传导机制。`;
  }
  return `实际利率仍在正常区间，非当前主矛盾。`;
}

function _whatUpgrades(st) {
  const watches = st.next_watch || [];
  if (watches.length > 0) {
    return watches.slice(0, 4).map(w => `→ ${w}`).join('<br>');
  }
  return `→ 监控 RCV / VTS / OAS / FX 四条路径的联动变化`;
}

/* ==================================================================
   BOTTOM — COMPREHENSIVE CONCLUSION
   ================================================================== */

function renderConclusion(es) {
  const el = document.getElementById('conclusion');
  if (!el) return;

  const regime  = es.regime || '—';
  const st      = es.stage_assessment || {};

  document.getElementById('conclusion-judgement').textContent = st.final_judgement || '—';

  let notYetBottom = st.not_yet_stage || '—';
  const fj2 = (st.final_judgement || '') + (st.risk_character || '');
  if (/非系统/.test(fj2) && /系统/.test(notYetBottom)) {
    notYetBottom = '尚未进入系统性风险';
  }
  document.getElementById('conclusion-stage').textContent =
    `${regime} · ${st.current_stage || '—'} · ${notYetBottom}`;

  const watchList = document.getElementById('conclusion-watch');
  if (watchList) {
    const watches = st.next_watch || [];
    if (watches.length === 0) {
      watchList.innerHTML = '<li>等待新信号…</li>';
    } else {
      watchList.innerHTML = watches.map(w => `<li>${w}</li>`).join('');
    }
  }
}

/* ==================================================================
   MAIN — validate, then render or show fallback
   ================================================================== */

async function main() {
  // ── Step 1: Load data ──
  const es = await loadEventState();

  // ── Step 2: If completely missing, show banner + fallbacks everywhere ──
  if (!es) {
    const msg = '解读数据缺失：无法加载 event_state.json。请确认已执行 daily_report.py --md。';
    showError(msg);
    showGridFallback('core-cards', msg);
    showGridFallback('aux-cards', msg);
    showGridFallback('trigger-cards', msg);
    showGridFallback('interp-cards', msg);
    showFallback('conclusion-judgement', msg);
    showFallback('conclusion-stage', '—');
    document.getElementById('hero-conclusion').textContent = msg;
    return;
  }

  // ── Step 3: Validate fields ──
  const v = validateEventState(es);
  if (!v.valid) {
    console.warn('[dashboard] Field validation warnings:', v.missing);
    // Don't block rendering — just log warnings and let each section handle its own fallbacks
  }

  // ── Step 4: Render all sections ──
  renderMasthead(es);
  renderCoreCards(es);
  renderAuxCards(es);
  renderTriggerCards(es);
  renderInterpretation(es);
  renderConclusion(es);

  console.log('[dashboard] Render complete.', {
    date: es.date,
    valid: v.valid,
    warnings: v.missing.length > 0 ? v.missing : 'none',
  });
}

function showError(msg) {
  // Remove existing error banner if any
  const existing = document.querySelector('.error-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.className = 'error-banner';
  banner.textContent = msg;
  const main = document.querySelector('main');
  if (main) main.prepend(banner);
}

main().catch(err => {
  console.error('[dashboard] Fatal load error:', err);
  showError(`看板加载失败：${err.message}`);
  showGridFallback('interp-cards', `运行时错误：${err.message}`);
});
