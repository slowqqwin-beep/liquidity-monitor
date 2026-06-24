/* =====================================================
   Risk Evolution Dashboard — Event-Driven Logic  v4
   Data source: event_state.json (from Risk OS Orchestrator v2.0 — SSoT)
   Schema: risk_os_final + _detail_inputs
   Rules: all final values read from risk_os_final; detail layers are inputs only
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

  // v2 schema: detail layers live under _detail_inputs; top-level always has risk_os_final
  const topRequired = ['date', 'regime', 'regime_key', 'systemic_classification', 'stage_assessment'];
  const missing = topRequired.filter(k => es[k] === undefined || es[k] === null);

  // Check detail layers — accept either top-level or _detail_inputs
  const detailSrc = (es._detail_inputs && Object.keys(es._detail_inputs).length > 0)
    ? es._detail_inputs : es;
  const subChecks = {
    'front_event_risk':        ['active', 'label', 'intensity'],
    'rate_shock':              ['active', 'dfii10_official', 'dfii10_nowcast'],
    'first_layer_transmission':['active', 'real_yield_pressure', 'main_path'],
    'systemic_triggers':       ['credit', 'liquidity', 'cross_asset', 'any_triggered', 'all_triggered'],
  };

  for (const [key, subs] of Object.entries(subChecks)) {
    const obj = detailSrc[key];
    if (obj === undefined || obj === null) { missing.push(`${key} (missing)`); continue; }
    for (const sub of subs) {
      if (obj[sub] === undefined) missing.push(`${key}.${sub}`);
    }
  }

  return { valid: missing.length === 0, missing };
}

/** Read detail layers from _detail_inputs (v2) or top-level (v1 fallback). */
function _details(es) {
  return (es._detail_inputs && Object.keys(es._detail_inputs).length > 0)
    ? es._detail_inputs : es;
}

/** Read risk_os_final if present (v2); fallback to top-level aliases. */
function _final(es) {
  return es.risk_os_final || es;
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
  const rf     = _final(es);
  const regime = rf.final_regime || es.regime || '—';
  const date   = es.date || '—';
  const pos    = rf.final_position || es.positions || {};
  const stage  = es.stage_assessment || {};
  const cross  = es.cross_domain_signals ?? '—';
  const red    = es.red_count ?? '—';
  const sysCls = rf.final_systemic_classification || es.systemic_classification || '—';
  const hero   = rf.final_hero || '';

  document.getElementById('mast-date').textContent    = date;
  document.getElementById('mast-regime').textContent  = regime;

  // Systemic badge: 4-level mapping
  const sysEl = document.getElementById('mast-systemic');
  if (sysEl) {
    let sysLabel = sysCls;
    let sysColor = C.good;
    if (/SYSTEMIC CONFIRMED/i.test(sysCls)) {
      sysColor = C.stress;
    } else if (/SYSTEMIC WATCH/i.test(sysCls)) {
      sysColor = C.stress;
      sysLabel = sysCls;
    } else if (/NON-SYSTEMIC WATCH|WATCH/i.test(sysCls)) {
      sysColor = C.orange;
      sysLabel = 'NON-SYSTEMIC WATCH';
    }
    sysEl.textContent = sysLabel;
    sysEl.style.color = sysColor;
  }
  document.getElementById('mast-cross').textContent   = cross;
  document.getElementById('mast-red').textContent     = red;

  document.getElementById('pos-primary').textContent = pos.primary || '—';
  document.getElementById('pos-hedge').textContent   = pos.hedge   || '—';
  document.getElementById('pos-cash').textContent    = pos.cash    || '—';

  const conclusion = document.getElementById('hero-conclusion');
  // Use risk_os_final hero if available, else construct from stage
  if (hero) {
    conclusion.textContent = hero;
  } else {
    let notYet = stage.not_yet_stage || '—';
    if (/非系统/.test(stage.final_judgement || '') && /系统/.test(notYet)) {
      notYet = '尚未进入系统性风险';
    }
    conclusion.textContent = `${regime}：${stage.current_stage || ''}，${notYet}。`;
  }
}

/* ==================================================================
   ROW 1 — FIVE CORE CARDS
   ================================================================== */

function renderCoreCards(es) {
  const grid = document.getElementById('core-cards');
  if (!grid) return;
  clearGrid('core-cards');

  const d = _details(es);
  const v = validateEventState(es);
  if (!d.front_event_risk || !d.rate_shock) {
    showGridFallback('core-cards',
      v.valid ? '—' : `核心信号数据缺失：${v.missing.filter(m => /front_event|rate_shock|first_layer/.test(m)).join('，') || 'front_event_risk / rate_shock 不可用'}`);
    return;
  }

  const fe = d.front_event_risk || {};
  const rs = d.rate_shock || {};
  const tx = d.first_layer_transmission || {};
  const tg = d.systemic_triggers || {};
  const st = es.stage_assessment || {};

  // 1 — 近端事件风险
  const feIntensity = fe.intensity || 'green';
  buildCard(grid, {
    accent: feIntensity === 'red' ? 'stress-left glow-stress' : feIntensity === 'orange' ? 'orange-left glow-orange' : 'good-left',
    light:  feIntensity,
    label:  '近端事件风险',
    status: fe.label || '前端平稳',
    statusColor: feIntensity === 'red' ? 'stress' : feIntensity === 'orange' ? 'orange' : 'good',
    detail: fe.active
      ? `US02Y−IORB=${fe.evidence?.dgs2_iorb_bp || '—'}bp，VIX=${fe.evidence?.vix || '—'}。${(fe.sources || []).join('；')}`
      : '无近端事件信号。US02Y−IORB 未倒挂，VIX 处于低位。',
  });

  // 2 — 实际利率 / 估值挤压（独立卡片）
  const dfii10   = rs.dfii10_official;
  const nowcast  = rs.dfii10_nowcast;
  const realActive = rs.active;

  // ── build detail with method, spread, direction, quality note ──
  let realDetail = `官方 DFII10 ${dfii10 != null ? dfii10.toFixed(2) + '%' : '—'}`;
  if (dfii10 != null && nowcast != null) {
    const spreadBp = rs.gap_bp != null ? rs.gap_bp : Math.round((nowcast - dfii10) * 100);
    const sign = spreadBp >= 0 ? '+' : '';
    const direction = rs.direction || 'N/A';
    realDetail += `\nReal Yield Nowcast ${nowcast.toFixed(2)}%（US10Y − T10YIE）`;
    realDetail += `\n差值 ${sign}${spreadBp}bp，${direction}`;
  } else if (nowcast != null) {
    realDetail += `\nReal Yield Nowcast ${nowcast.toFixed(2)}%（US10Y − T10YIE）`;
  }
  realDetail += `\n⚠️ 官方 DFII10 滞后修正，Nowcast 更实时`;
  if (rs.dur5_confirmed) realDetail += `\nDUR5=${rs.dur5_dfii}/5 已确认`;
  if (realActive) realDetail += `\n— 贴现率持续压制估值`;

  buildCard(grid, {
    accent: realActive ? 'stress-left glow-stress' : 'good-left',
    light:  realActive ? 'red' : 'green',
    label:  '实际利率 / 估值挤压',
    value:  rs.level_label || (dfii10 != null ? `DFII10 ${dfii10.toFixed(2)}%` : '—'),
    status: rs.level_light ? `${rs.level_light} ${rs.level_label || ''}` : (realActive ? '🔴 高压 · 估值压缩' : '○ 正常区间'),
    statusColor: realActive ? 'stress' : 'good',
    detail: realDetail,
  });

  // 3 — 第一层传导
  const mainPath = tx.main_path || '';
  buildCard(grid, {
    accent: tx.active ? 'orange-left glow-orange' : '',
    light:  tx.active ? 'orange' : 'green',
    label:  '第一层传导',
    status: tx.active ? '活跃传导' : '无显著传导',
    statusColor: tx.active ? 'orange' : 'mute',
    detail: mainPath ? `${mainPath}\n${tx.summary || ''}` : '四端无显著传导压力',
  });

  // 4 — 系统性风险触发器
  const t2Partial = tg.liquidity?.partial || tg.liquidity?.credit_partial;
  const t2Status = tg.liquidity?.active
    ? (t2Partial ? 'T2 已触发·部分压力' : 'T2 已触发')
    : 'T2 未触发';
  const triggeredBits = [
    tg.credit?.active ? 'T1' : null,
    tg.liquidity?.active ? (t2Partial ? 'T2(部分)' : 'T2') : null,
    tg.cross_asset?.active ? 'T3' : null,
  ].filter(Boolean);
  const trigSummary = triggeredBits.length > 0 ? `${triggeredBits.join('+')} 已触发` : '三重皆未触发';
  const trigColor = tg.all_triggered ? 'stress' : tg.any_triggered ? 'orange' : 'good';
  buildCard(grid, {
    accent: trigColor === 'stress' ? 'stress-left glow-stress'
          : trigColor === 'orange' ? 'orange-left glow-orange' : 'good-left',
    light:  trigColor,
    label:  '系统性风险触发器',
    status: trigSummary,
    statusColor: trigColor,
    detail: `T1信用:${tg.credit?.label || '—'} / T2流动:${t2Status} / T3跨资产:${tg.cross_asset?.label || '—'}`,
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

  const d = _details(es);
  if (!d.first_layer_transmission || !d.systemic_triggers) {
    showGridFallback('aux-cards', '辅助判断数据缺失：first_layer_transmission / systemic_triggers 不可用');
    return;
  }

  const tx = d.first_layer_transmission || {};
  const tg = d.systemic_triggers || {};
  const st = es.stage_assessment || {};
  const rs = d.rate_shock || {};

  // Fed鸽派 / 流动性缓冲
  const buffText = rs.active
    ? '鸽派缓冲存在，但不能抵消实际利率高压'
    : '流动性缓冲充裕，Fed尚有空间';
  buildCard(grid, {
    accent: rs.active ? 'orange-left' : 'good-left',
    label: 'Fed鸽派 / 流动性缓冲',
    status: rs.active ? '缓冲存在·被高压盖过' : '缓冲充裕',
    statusColor: rs.active ? 'orange' : 'good',
    detail: buffText,
  });

  // 资产反应链
  const cascCnt = tg.casc_count ?? 0;
  buildCard(grid, {
    label: '资产反应链',
    status: `${cascCnt}/4 跨资产信号`,
    statusColor: cascCnt >= 2 ? 'stress' : 'mute',
    detail: cascCnt >= 2
      ? '⚠️ 多资产共振 — 跨市场压力扩散'
      : cascCnt === 1
        ? '单一资产信号，未形成跨市场共振'
        : '各资产端平静，无跨资产共振',
  });

  // 抄底条件
  let dipText;
  if (tg.all_triggered) {
    dipText = '❌ 三重触发器全亮 — 不抄底，等risk-off结束';
  } else if (!tg.any_triggered) {
    dipText = '✅ 三重触发器全灭 — 结构性支撑完好，逢低可考虑';
  } else {
    const t2Active = tg.liquidity?.active;
    const t2Partial = tg.liquidity?.partial || tg.liquidity?.credit_partial;
    const t1Active = tg.credit?.active;
    const t3Active = tg.cross_asset?.active;
    if (t2Active && t2Partial && !t1Active && !t3Active) {
      dipText = '⚠️ T2 流动性已触发·部分压力 — 但 T1 信用未确认、T3 跨资产未共振，仅轻仓试探';
    } else if (t2Active && !t2Partial && !t1Active) {
      dipText = '⚠️ T2 流动性已触发 — 但 T1 信用未确认，仅轻仓试探';
    } else {
      dipText = '⚠️ 部分触发 — 仅轻仓试探，等 T1 信用转绿';
    }
  }
  buildCard(grid, {
    label: '重新考虑抄底的条件',
    status: tg.all_triggered ? '暂不考虑' : tg.any_triggered ? '轻仓试探' : '逢低可考虑',
    statusColor: tg.all_triggered ? 'stress' : tg.any_triggered ? 'orange' : 'good',
    detail: dipText,
  });

  // 下一步观察点
  const watches = (st.next_watch || []).slice(0, 3);
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

  const d = _details(es);
  const tg = d.systemic_triggers;
  if (!tg || !tg.credit) {
    showGridFallback('trigger-cards', '触发器数据缺失：systemic_triggers 不可用');
    return;
  }

  buildTriggerCard(grid, {
    id: 'T1', name: 'T1 信用 (B端)',
    condition: 'HY OAS > 300bp',
    active: tg.credit?.active || false,
    label: tg.credit?.label || '未触发',
    evidence: tg.credit?.evidence || '—',
  });

  const t2 = tg.liquidity || {};
  const t2Partial = t2.partial || t2.credit_partial;
  buildTriggerCard(grid, {
    id: 'T2', name: 'T2 流动性 (A端)',
    condition: 'EFFR–IORB ≥ −3bp + DUR5 ≥ 3',
    active: t2.active || false,
    partial: t2Partial,
    label: t2.active && t2Partial ? '已触发·部分压力' : (t2.label || '未触发'),
    evidence: t2.evidence || '—',
  });

  buildTriggerCard(grid, {
    id: 'T3', name: 'T3 跨资产 / 跨境',
    condition: 'CASC ≥ 2/4 (VIX>25 + MOVE>120 + HY 20dΔ>20bp + FXY 5d>2.5%)',
    active: tg.cross_asset?.active || false,
    label: tg.cross_asset?.label || '未触发',
    evidence: tg.cross_asset?.evidence || '—',
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
  const d = _details(es);
  const fe = d.front_event_risk;
  const rs = d.rate_shock;
  const tx = d.first_layer_transmission;
  const tg = d.systemic_triggers;
  const st = es.stage_assessment;

  if (!fe || !rs || !tx || !tg || !st) {
    const missing = [];
    if (!fe) missing.push('front_event_risk');
    if (!rs) missing.push('rate_shock');
    if (!tx) missing.push('first_layer_transmission');
    if (!tg) missing.push('systemic_triggers');
    if (!st) missing.push('stage_assessment');
    showGridFallback('interp-cards',
      `解读数据缺失：缺少 ${missing.join('、')}。请检查 event_state.json 是否由 risk_os_state_machine.py 生成。`);
    return;
  }

  if (fe.active === undefined && !st.current_stage) {
    showGridFallback('interp-cards',
      '解读数据缺失：front_event_risk.active 和 current_stage 均为空。请检查 event_state.json 是否生成。');
    return;
  }

  const items = [
    { title: '为什么当前是近端事件风险？',   body: _whyNearEvent(fe, rs) },
    { title: '为什么尚非系统性？',           body: _whyNotSystemic(fe, tg) },
    { title: '实际利率为何是主矛盾？',       body: _whyRealYield(rs) },
    { title: '哪些变化会推动升级？',         body: _whatUpgrades(st, tg) },
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

function _whyNearEvent(fe, rs) {
  const dgs2 = fe.evidence?.dgs2_iorb_bp;
  const vix  = fe.evidence?.vix;
  if (fe.active && dgs2 != null && dgs2 > 0) {
    return `前端US02Y−IORB=${dgs2}bp，市场在定价具体近端利率事件（FOMC/CPI）而非系统性恐慌。VIX=${vix || '—'}，波动率未扩散至远期结构。${rs.active && rs.dfii10_official ? `实际利率DFII10=${rs.dfii10_official}%，估值端承压但非信用主导。` : ''}`;
  }
  return `当前市场信号集中在前端利率预期调整上，近端事件（FOMC/CPI）是主要定价因素，尚未扩散为广泛风险规避。`;
}

function _whyNotSystemic(fe, tg) {
  const creditOk  = !tg.credit?.active;
  const crossOk   = !tg.cross_asset?.active;
  const t2Active  = tg.liquidity?.active;
  const t2Partial = tg.liquidity?.partial || tg.liquidity?.credit_partial;
  if (creditOk && crossOk) {
    if (t2Active) {
      const t2Detail = t2Partial
        ? `T2 流动性：已触发·部分压力（${tg.liquidity?.evidence || '—'}）`
        : `T2 流动性：已触发（${tg.liquidity?.evidence || '—'}）`;
      return `${t2Detail}，但 T1 信用未触发、T3 跨资产未触发，不满足系统性风险"三端共振"定义。当前仅为单端（流动性）部分压力，尚非系统性风险。`;
    }
    return 'T1 信用未触发、T2 流动性未触发、T3 跨资产未触发，三重触发器全灭，无系统性风险迹象。';
  }
  return `当前触发信号不足以确认系统性风险转换。`;
}

function _whyRealYield(rs) {
  const dfii = rs.dfii10_official;
  const nc   = rs.dfii10_nowcast;
  if (dfii != null && dfii >= 2.0) {
    return `DFII10=${dfii}%远高于2.0%舒适区，实际利率直接压制定价模型分母端。${nc != null ? `Real Yield Nowcast=${nc}%确认这一趋势。` : ''}在高实际利率环境下，所有风险资产的现值都被系统性压缩，这是当前最核心的传导机制。${rs.dur5_confirmed ? `DUR5=${rs.dur5_dfii}/5已确认持续高压。` : ''}`;
  }
  return `实际利率仍在正常区间，非当前主矛盾。`;
}

function _whatUpgrades(st, tg) {
  const watches = st.next_watch || [];
  const conds = st.systemic_upgrade_conditions || {};
  let summary = '';
  if (conds.all_met) {
    summary = '⚠️ 三条件已全部满足，系统已进入系统性风险。\n';
  } else {
    const flags = [];
    if (conds.credit_widening) flags.push('✅ 信用已走阔');
    else flags.push('❌ 信用未走阔（HY OAS需>300bp）');
    if (conds.liquidity_sustained) flags.push('✅ 流动性压力持续');
    else flags.push('❌ 流动性压力未持续');
    if (conds.cross_asset_resonance) flags.push('✅ 跨资产共振');
    else flags.push('❌ 跨资产未共振（CASC需≥2/4）');
    summary = flags.join(' | ') + '\n';
  }
  if (watches.length > 0) {
    return summary + watches.slice(0, 4).map(w => `→ ${w}`).join('<br>');
  }
  return summary + `→ 监控 RCV / VTS / OAS / FX 四条路径的联动变化`;
}

/* ==================================================================
   BOTTOM — COMPREHENSIVE CONCLUSION
   ================================================================== */

function renderConclusion(es) {
  const el = document.getElementById('conclusion');
  if (!el) return;

  const rf     = _final(es);
  const regime = rf.final_regime || es.regime || '—';
  const st     = es.stage_assessment || {};

  document.getElementById('conclusion-judgement').textContent =
    rf.final_judgement || st.final_judgement || '—';

  let notYetBottom = st.not_yet_stage || '—';
  if (/非系统/.test(st.final_judgement || '') && /系统/.test(notYetBottom)) {
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
    const msg = '解读数据缺失：无法加载 event_state.json。请确认已执行 risk_os_state_machine.py。';
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

  // ── Step 3.5: Detect signal conflicts ──
  if (es.signal_conflicts && es.signal_conflicts.length > 0) {
    const msgs = es.signal_conflicts.map(c => c.detail).join('；');
    showError(`⚠️ 信号冲突：${msgs}`);
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
