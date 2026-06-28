const JSON_URL = "./data/sr3_repair_watch_latest.json";
const MD_URL = "./data/sr3_repair_watch_latest.md";

const colors = [
  "#7dd3fc", "#60a5fa", "#f59e0b", "#4ade80", "#a78bfa",
  "#fb7185", "#22d3ee", "#facc15", "#c084fc", "#38bdf8"
];

const fallbackData = {
  generated_at: null,
  data_date: null,
  reference_peak: "formal shock",
  status: "Research-Only",
  state: "State 2: Deceleration",
  state_note: "短端预期：已钝化，但尚未出现实质性/持续修复",
  hawkish_impulse: false,
  deceleration: true,
  deceleration_since: "2026-05-28",
  level_repair: false,
  classification: "mixed_repair",
  classification_reason: "Mixed signals, no clear benign/malign pattern",
  repair: true,
  near_rate: 3.8,
  drawdown_from_peak_bp: -7.5,
  daily_change_bp: -1.38,
  five_day_change_bp: 11.88,
  high_plateau: true,
  hy_oas: null,
  dgs10: null,
  real_yield_nowcast: null,
  repair_start_date: "2026-05-28",
  repair_magnitude_bp: 9.25,
  field_warnings: ["数据读取失败，当前展示 fallback 示例数据"],
  mixed_repair_warning: "mixed_repair 不是买入信号；它只表示 SR3 冲击已钝化但尚未完成 level repair，且 benign repair 条件未完全满足。",
  constraints: {
    research_only: true,
    standalone_sr3_watch: true,
    no_risk_os: true,
    no_existing_dashboard_merge: true,
    no_run_all: true,
    no_position_impact: true,
    deceleration_not_buy_signal: true
  },
  reference_peaks: [],
  signal_matrix: [],
  curve_contracts: [
    {code:"Z26", label:"Dec-26", contract:"SR3Z2026"},
    {code:"H27", label:"Mar-27", contract:"SR3H2027"},
    {code:"M27", label:"Jun-27", contract:"SR3M2027"}
  ],
  curve_comparison: [],
  curve_bp_changes: [],
  twos10s_source_file: null,
  twos10s_series: [],
  twos10s_latest: {
    latest_spread_bp: null,
    change_1d_bp: null,
    change_5d_bp: null,
    structure: "N/A",
    structure_note: "未提供 2s10s 数据。"
  },
  twos10s_warning: "未找到 2s10s TradingView CSV。"
};

function $(id){ return document.getElementById(id); }

function fmt(v, suffix = "", digits = 2){
  if(v === null || v === undefined || Number.isNaN(v)) return "N/A";
  if(typeof v === "number") return `${v.toFixed(digits)}${suffix}`;
  return `${v}${suffix}`;
}

function fmtPct(v){
  if(v === null || v === undefined || Number.isNaN(v)) return "N/A";
  return `${Number(v).toFixed(3)}%`;
}

function boolText(v){
  if(v === true) return "是";
  if(v === false) return "否";
  return "N/A";
}

async function loadData(){
  // 优先使用内嵌数据（支持 file:// 协议）
  if(window.SR3_DATA && window.SR3_DATA.data_date){
    console.log("[SR3 Watch] Using embedded window.SR3_DATA");
    return window.SR3_DATA;
  }
  try{
    const res = await fetch(JSON_URL, {cache:"no-store"});
    if(!res.ok) throw new Error(`JSON fetch failed: ${res.status}`);
    return await res.json();
  }catch(err){
    console.warn(err);
    // 回退到内嵌数据（即使上方检查失败也再试一次）
    if(window.SR3_DATA && window.SR3_DATA.data_date){
      console.log("[SR3 Watch] Fallback to embedded window.SR3_DATA");
      return window.SR3_DATA;
    }
    try{
      const res = await fetch(MD_URL, {cache:"no-store"});
      if(res.ok){
        const md = await res.text();
        const data = {...fallbackData};
        data.field_warnings = ["JSON 读取失败，已读取 Markdown，但前端仅展示 fallback 结构。请运行 scripts/build_sr3_watch_dashboard.py 生成 JSON。"];
        data.raw_md = md;
        return data;
      }
    }catch(e){
      console.warn(e);
    }
    return fallbackData;
  }
}

function renderWarnings(data){
  const warnings = [];
  if(data.field_warnings && data.field_warnings.length) warnings.push(...data.field_warnings);
  if(data.curve_warning) warnings.push(data.curve_warning);
  const el = $("warningBanner");
  if(warnings.length){
    el.classList.remove("hidden");
    el.innerHTML = warnings.map(x => `⚠️ ${escapeHtml(x)}`).join("<br>");
  }else{
    el.classList.add("hidden");
  }
}

function renderHero(data){
  $("stateChip").textContent = data.state || "State 2: Deceleration";
  $("heroState").textContent = data.state || "State 2: Deceleration";
  $("heroNote").textContent = data.current_event_note || data.state_note || "SR3 已钝化，但尚未完成 level repair；当前不是买入信号。";
  $("dataDate").textContent = data.data_date || "N/A";
  $("generatedAt").textContent = data.generated_at || "N/A";
  $("referencePeak").textContent = data.event_baseline_date && (data.hike_over_peak_date || data.current_event_peak_date) ? `${data.event_baseline_date} → ${data.hike_over_peak_date || data.current_event_peak_date}` : (data.reference_peak || "N/A");
  $("status").textContent = data.status || "Research-Only";
  $("mixedRepairWarning").textContent = data.mixed_repair_warning || fallbackData.mixed_repair_warning;
}

function renderQuestionCards(data){
  const currentRepairStarted = !!data.current_event_repair_start_date;
  const stillHikeOverImpulse = data.current_event_state === "at_hike_over_peak_or_no_repair" || data.current_event_state === "at_peak_or_no_repair";

  const items = [
    {
      label:"当前事件仍在 hike-over impulse？",
      value:boolText(stillHikeOverImpulse),
      sub:stillHikeOverImpulse ? "仍在峰值附近，尚未回落" : "否 = 已离开当前事件峰值",
      cls:stillHikeOverImpulse ? "red" : "green"
    },
    {
      label:"当前事件修复启动？",
      value:boolText(currentRepairStarted),
      sub:currentRepairStarted ? `起始：${data.current_event_repair_start_date}` : "尚未确认从峰值回落",
      cls:currentRepairStarted ? "yellow" : "gray"
    },
    {
      label:"发生 event level repair？",
      value:boolText(data.event_strict_level_repair || data.event_avg_level_repair),
      sub:(data.event_strict_level_repair || data.event_avg_level_repair) ? "已回到事件前基准" : "未回到 6/16 事件基准",
      cls:(data.event_strict_level_repair || data.event_avg_level_repair) ? "green" : "red"
    },
    {
      label:"修复分类",
      value:data.classification || "N/A",
      sub:"mixed_repair 是原报告分类；当前事件单独看 repair start / level repair",
      cls:"yellow"
    },
  ];
  $("questionCards").innerHTML = items.map(i => `
    <article class="card ${i.cls}">
      <div class="label">${escapeHtml(i.label)}</div>
      <div class="value">${escapeHtml(i.value)}</div>
      <div class="sub">${escapeHtml(i.sub)}</div>
    </article>
  `).join("");
}


function renderKpis(data){
  const kpis = [
    {label:"near_rate", value:fmtPct(data.near_rate), cls:""},
    {label:"Hike-over 已修复", value:data.hike_over_repair_magnitude_bp === null || data.hike_over_repair_magnitude_bp === undefined ? fmt(data.drawdown_from_peak_bp, " bp", 2) : fmt(data.hike_over_repair_magnitude_bp, " bp", 2), cls:"good"},
    {label:"当日变动", value:fmt(data.daily_change_bp, " bp", 2), cls:data.daily_change_bp < 0 ? "good" : "warn", note:data.daily_change_bp < 0 ? "钝化，但不是买点" : ""},
    {label:"5d 累计", value:fmt(data.five_day_change_bp, " bp", 2), cls:data.five_day_change_bp > 5 ? "warn" : ""},
    {label:"高台 >3.5%", value:boolText(data.high_plateau), cls:data.high_plateau ? "warn" : "good"},
    {label:"HY OAS", value:data.hy_oas === null ? "N/A" : fmt(data.hy_oas, " bp", 1), cls:data.hy_oas === null ? "na" : ""},
    {label:"US10Y", value:data.us10y === null ? "N/A" : fmt(data.us10y, "%", 3), cls:data.us10y === null ? "na" : ""},
    {label:"T10YIE", value:data.t10yie === null ? "N/A" : fmt(data.t10yie, "%", 3), cls:data.t10yie === null ? "na" : ""},
    {label:"Real Yield", value:data.real_yield_nowcast === null ? "N/A" : fmt(data.real_yield_nowcast, "%", 3), cls:data.real_yield_nowcast === null ? "na" : ""},
  ];
  $("kpiGrid").innerHTML = kpis.map(k => `
    <div class="kpi ${k.cls}">
      <span>${escapeHtml(k.label)}</span>
      <strong>${escapeHtml(k.value)}</strong>
      ${k.note ? `<small>${escapeHtml(k.note)}</small>` : ""}
    </div>
  `).join("");
}

function renderReferencePeaks(data){
  const table = $("referencePeaksTable");

  const ratio = data.hike_over_repair_ratio === null || data.hike_over_repair_ratio === undefined
    ? "N/A"
    : `${(Number(data.hike_over_repair_ratio) * 100).toFixed(1)}%`;

  const rows = [
    {
      source: "Event Baseline / 事件前基准",
      date: data.event_baseline_date || "N/A",
      role: "FOMC 前回准线",
      rate: data.event_baseline_avg_rate === null || data.event_baseline_avg_rate === undefined ? "N/A" : fmt(data.event_baseline_avg_rate, "%", 4),
      note: "event level repair 以这条线为准"
    },
    {
      source: "Hike-over Peak / 加息预期峰值",
      date: data.hike_over_peak_date || data.current_event_peak_date || "N/A",
      role: "FOMC 后冲击峰值",
      rate: data.hike_over_peak_avg_rate === null || data.hike_over_peak_avg_rate === undefined ? "N/A" : fmt(data.hike_over_peak_avg_rate, "%", 4),
      note: data.hike_over_shock_bp === null || data.hike_over_shock_bp === undefined ? "N/A" : `相对基准 +${Number(data.hike_over_shock_bp).toFixed(1)}bp`
    },
    {
      source: "Repair Start / 当前修复起点",
      date: data.current_event_repair_start_date || "N/A",
      role: "从峰值回落第一天",
      rate: data.hike_over_repair_magnitude_bp === null || data.hike_over_repair_magnitude_bp === undefined ? "N/A" : `已修复 ${Number(data.hike_over_repair_magnitude_bp).toFixed(1)}bp`,
      note: `修复比例 ${ratio}`
    },
    {
      source: "Event Level Repair / 水平修复",
      date: data.event_level_repair_date || "N/A",
      role: "回到事件前基准",
      rate: data.hike_over_remaining_bp === null || data.hike_over_remaining_bp === undefined ? "N/A" : `仍高 ${Number(data.hike_over_remaining_bp).toFixed(1)}bp`,
      note: data.event_strict_level_repair ? "已完成" : "未完成"
    }
  ];

  const oldFormal = (data.reference_peaks || []).find(r => String(r.source || "").toLowerCase().includes("formal"));
  if(oldFormal){
    rows.push({
      source: "Formal Shock / 旧研究审计",
      date: oldFormal.date || "N/A",
      role: "原报告旧参考",
      rate: oldFormal.near_rate === null || oldFormal.near_rate === undefined ? "N/A" : fmt(oldFormal.near_rate, "%", 4),
      note: "不作为本轮 FOMC event level repair 回准线"
    });
  }

  table.innerHTML = `
    <thead><tr><th>参考线</th><th>日期</th><th>用途</th><th>水平 / 进度</th><th>说明</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${escapeHtml(r.source)}</td>
        <td>${escapeHtml(r.date)}</td>
        <td>${escapeHtml(r.role)}</td>
        <td>${escapeHtml(r.rate)}</td>
        <td>${escapeHtml(r.note)}</td>
      </tr>
    `).join("")}</tbody>`;
}


function renderDetails(data){
  const ratio = data.hike_over_repair_ratio === null || data.hike_over_repair_ratio === undefined
    ? "N/A"
    : `${(Number(data.hike_over_repair_ratio) * 100).toFixed(1)}%`;

  const rows = [
    ["分类", data.classification || "N/A", "warn"],
    ["原因", data.classification_reason || "N/A", ""],
    ["level_repair", boolText(data.level_repair), data.level_repair ? "ok" : "bad"],
    ["事件前基准日", data.event_baseline_date || "N/A", ""],
    ["Hike-over 峰值日", data.hike_over_peak_date || data.current_event_peak_date || "N/A", "warn"],
    ["当前修复起始日", data.current_event_repair_start_date || "N/A", data.current_event_repair_start_date ? "ok" : "na"],
    ["Hike-over 冲击", data.hike_over_shock_bp === null || data.hike_over_shock_bp === undefined ? "N/A" : fmt(data.hike_over_shock_bp, " bp", 2), "warn"],
    ["已修复幅度", data.hike_over_repair_magnitude_bp === null || data.hike_over_repair_magnitude_bp === undefined ? "N/A" : fmt(data.hike_over_repair_magnitude_bp, " bp", 2), "warn"],
    ["修复比例", ratio, "warn"],
    ["距离基准仍高", data.hike_over_remaining_bp === null || data.hike_over_remaining_bp === undefined ? "N/A" : fmt(data.hike_over_remaining_bp, " bp", 2), "bad"],
    ["Avg level repair", boolText(data.event_avg_level_repair), data.event_avg_level_repair ? "ok" : "bad"],
    ["Strict level repair", boolText(data.event_strict_level_repair), data.event_strict_level_repair ? "ok" : "bad"],
    ["level repair 日期", data.event_level_repair_date || "N/A", data.event_level_repair_date ? "ok" : "na"],
    ["原报告修复起始日", data.repair_start_date || "N/A", "na"],
  ];
  const eventNote = data.current_event_note ? `<div class="event-note">${escapeHtml(data.current_event_note)}</div>` : "";
  $("classificationDetails").innerHTML = rows.map(([k,v,cls]) => `
    <div class="detail-row"><span>${escapeHtml(k)}</span><strong class="${cls}">${escapeHtml(v)}</strong></div>
  `).join("") + eventNote;
}


function renderConstraints(data){
  const constraints = data.constraints || {};
  const rows = [
    ["Research-Only", constraints.research_only],
    ["独立 SR3 Watch 页面", constraints.standalone_sr3_watch],
    ["不接 Risk OS", constraints.no_risk_os],
    ["不接旧 dashboard", constraints.no_existing_dashboard_merge],
    ["不接 run_all.py", constraints.no_run_all],
    ["不影响仓位", constraints.no_position_impact],
    ["SR3 deceleration ≠ buy signal", constraints.deceleration_not_buy_signal],
  ];
  $("constraintList").innerHTML = rows.map(([k,v]) => `
    <div class="constraint-row"><span>${escapeHtml(k)}</span><strong class="${v ? "ok" : "bad"}">${v ? "✅" : "❌"}</strong></div>
  `).join("");
}

function renderTwo3m(data){
  const series = data.two3m_series || [];
  const latest = data.two3m_latest || {};
  $("two3mLatest").textContent = latest.latest_spread_bp === null || latest.latest_spread_bp === undefined ? "N/A" : `${Number(latest.latest_spread_bp).toFixed(1)} bp`;
  $("two3m1d").textContent = latest.change_1d_bp === null || latest.change_1d_bp === undefined ? "N/A" : `${Number(latest.change_1d_bp).toFixed(1)} bp`;
  $("two3mStructure").textContent = latest.structure || "N/A";
  $("two3mNote").textContent = latest.structure_note || "等待 2Y-3M 数据。";

  const tbl = $("two3mTable");
  const rows = series.slice(-10).reverse();
  if(!rows.length){
    tbl.innerHTML = "<thead><tr><th>日期</th><th>2Y-3M</th><th>2Y</th><th>3M</th></tr></thead><tbody><tr><td colspan='4'>暂无数据</td></tr></tbody>";
    return;
  }
  tbl.innerHTML = `
    <thead><tr><th>日期</th><th>2Y-3M</th><th>2Y</th><th>3M</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${escapeHtml(r.date)}</td>
        <td>${r.spread_bp === null ? "N/A" : `${Number(r.spread_bp).toFixed(1)} bp`}</td>
        <td>${r.two_y === null ? "N/A" : `${Number(r.two_y).toFixed(3)}%`}</td>
        <td>${r.three_m === null ? "N/A" : `${Number(r.three_m).toFixed(3)}%`}</td>
      </tr>`).join("")}</tbody>`;
}

function renderRetracement(data){
  const rows = data.retracement || [];
  const table = $("retracementTable");
  if(!rows.length){
    table.innerHTML = "<thead><tr><th>合约</th><th>Baseline</th><th>Peak</th><th>Now</th><th>Overshoot</th><th>Retraced</th><th>% Repair</th></tr></thead><tbody><tr><td colspan='7'>暂无数据</td></tr></tbody>";
    return;
  }
  const formatR = (v) => v === null || v === undefined ? "—" : v.toFixed(1);
  const maxPct = Math.max(...rows.map(r => r.repair_pct || 0));
  table.innerHTML = `
    <thead><tr><th>合约</th><th>Baseline</th><th>Peak</th><th>Now</th><th>Overshoot</th><th>Retraced</th><th>% Repair</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td><strong>${escapeHtml(r.contract)}</strong></td>
        <td>${r.baseline_pct.toFixed(3)}%</td>
        <td>${r.peak_pct.toFixed(3)}%</td>
        <td>${r.now_pct.toFixed(3)}%</td>
        <td>${r.overshoot_bp > 0 ? "+" : ""}${formatR(r.overshoot_bp)}bp</td>
        <td>${r.retraced_bp > 0 ? "-" : "+"}${formatR(Math.abs(r.retraced_bp))}bp</td>
        <td style="background:linear-gradient(90deg,rgba(74,222,128,${(r.repair_pct||0)/maxPct*0.5}) ${r.repair_pct||0}%,transparent ${r.repair_pct||0}%)">${r.repair_pct === null ? "—" : formatR(r.repair_pct) + "%"}</td>
      </tr>`).join("")}</tbody>`;
}

function renderSignalMatrix(data){
  const rows = data.signal_matrix && data.signal_matrix.length ? data.signal_matrix : [
    {condition:"信用不扩 + SR3 钝化", meaning:"鹰派动能衰竭，但短端预期尚未回落"},
    {condition:"信用不扩 + SR3 level repair + real yield 不再创新高", meaning:"短端预期已明显回落，信用未恶化"},
    {condition:"信用不扩 + SR3 benign repair + 分子兑现", meaning:"软着陆情景：利率回落 + 信用收窄"},
    {condition:"SR3 钝化但不修复", meaning:"暂停后利率继续上行，不构成拐点信号"},
  ];
  $("signalMatrixTable").innerHTML = `
    <thead><tr><th>条件</th><th>信号含义</th></tr></thead>
    <tbody>${rows.map(r => `<tr><td>${escapeHtml(r.condition)}</td><td>${escapeHtml(r.meaning)}</td></tr>`).join("")}</tbody>
  `;
}

function renderTwos10s(data){
  const latest = data.twos10s_latest || {};
  $("twos10sLatest").textContent = latest.latest_spread_bp === null || latest.latest_spread_bp === undefined ? "N/A" : `${Number(latest.latest_spread_bp).toFixed(1)} bp`;
  $("twos10sD10").textContent = latest.d10_1d_bp === null || latest.d10_1d_bp === undefined ? "N/A" : `${Number(latest.d10_1d_bp).toFixed(1)} bp`;
  $("twos10sD2").textContent = latest.d2_1d_bp === null || latest.d2_1d_bp === undefined ? "N/A" : `${Number(latest.d2_1d_bp).toFixed(1)} bp`;
  $("twos10s5d").textContent = latest.change_5d_bp === null || latest.change_5d_bp === undefined ? "N/A" : `${Number(latest.change_5d_bp).toFixed(1)} bp`;
  $("twos10sStructure").textContent = latest.structure || "N/A";
  $("twos10sNote").textContent = latest.structure_note || data.twos10s_warning || "等待数据。";

  // 2Y-3M
  const m3latest = data.two3m_latest || {};
  $("two3mLatest").textContent = m3latest.latest_spread_bp === null || m3latest.latest_spread_bp === undefined ? "N/A" : `${Number(m3latest.latest_spread_bp).toFixed(1)} bp`;
  $("two3mD3m").textContent = m3latest.d3m_1d_bp === null || m3latest.d3m_1d_bp === undefined ? "N/A" : `${Number(m3latest.d3m_1d_bp).toFixed(1)} bp`;
  $("two3mStructure").textContent = m3latest.structure || "N/A";

  renderTwos10sChart(data);
  renderTwos10sTable(data);
}

function renderTwos10sTable(data){
  const rows = (data.twos10s_series || []).slice(-10).reverse();
  const m3Rows = (data.two3m_series || []).slice(-10).reverse();
  // Merge 3M into 2s10s rows by date
  const m3ByDate = {};
  (m3Rows || []).forEach(r => { m3ByDate[r.date] = r; });

  const table = $("twos10sTable");
  if(!rows.length){
    table.innerHTML = `<thead><tr><th>日期</th><th>2s10s</th><th>10Y</th><th>2Y</th><th>3M</th><th>2s3m</th></tr></thead><tbody><tr><td colspan="6">暂无数据</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead><tr><th>日期</th><th>2s10s</th><th>10Y</th><th>2Y</th><th>3M</th><th>2s3m</th></tr></thead>
    <tbody>${rows.map(r => {
      const m3 = m3ByDate[r.date];
      return `
      <tr>
        <td>${escapeHtml(r.date)}</td>
        <td>${r.spread_bp === null || r.spread_bp === undefined ? "N/A" : `${Number(r.spread_bp).toFixed(1)} bp`}</td>
        <td>${r.ten_y === null || r.ten_y === undefined ? "N/A" : `${Number(r.ten_y).toFixed(3)}%`}</td>
        <td>${r.two_y === null || r.two_y === undefined ? "N/A" : `${Number(r.two_y).toFixed(3)}%`}</td>
        <td>${r.three_m === null || r.three_m === undefined ? (m3 ? `${Number(m3.three_m).toFixed(3)}%` : "N/A") : `${Number(r.three_m).toFixed(3)}%`}</td>
        <td>${m3 ? `${Number(m3.spread_bp).toFixed(1)} bp` : "N/A"}</td>
      </tr>`;
    }).join("")}</tbody>`;
}

function renderTwos10sChart(data){
  const svg = $("twos10sChart");
  const rows = (data.twos10s_series || []).slice(-60).filter(r => r.spread_bp !== null && r.spread_bp !== undefined);
  svg.innerHTML = "";
  if(!rows.length){
    svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#92a3bc">暂无 2s10s 数据</text>`;
    return;
  }

  const width = 760, height = 480;
  const margin = {top: 24, right: 38, bottom: 42, left: 58};
  const upper = {top: 34, height: 165};
  const lower1 = {top: 228, height: 55};
  const lower2 = {top: 310, height: 55};
  const lower3 = {top: 392, height: 55};
  const innerW = width - margin.left - margin.right;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const make = (tag, attrs = {}, text = null) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, v));
    if(text !== null) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  const x = i => margin.left + (rows.length === 1 ? innerW / 2 : innerW * i / (rows.length - 1));

  // Background
  make("rect",{x:0,y:0,width,height,rx:18,fill:"rgba(3,7,18,.10)"});
  make("text",{x:margin.left,y:18,fill:"#cfe6ff","font-size":"12","font-weight":"900"},"上：10Y / 2Y / 3M 利率曲线");
  make("text",{x:margin.left,y:214,fill:"#cfe6ff","font-size":"12","font-weight":"900"},"中：2s10s 利差（10Y − 2Y）");
  make("text",{x:margin.left,y:296,fill:"#cfe6ff","font-size":"12","font-weight":"900"},"下：2s3m 利差（2Y − 3M）");
  make("line",{x1:margin.left,y1:217,x2:width-margin.right,y2:217,stroke:"rgba(148,163,184,.28)","stroke-dasharray":"5 6"});
  make("line",{x1:margin.left,y1:299,x2:width-margin.right,y2:299,stroke:"rgba(148,163,184,.28)","stroke-dasharray":"5 6"});

  const hasYields = rows.some(r => r.ten_y !== null && r.ten_y !== undefined && r.two_y !== null && r.two_y !== undefined);

  if(hasYields){
    const yieldVals = [];
    rows.forEach(r => {
      if(r.ten_y !== null && r.ten_y !== undefined) yieldVals.push(Number(r.ten_y));
      if(r.two_y !== null && r.two_y !== undefined) yieldVals.push(Number(r.two_y));
      if(r.three_m !== null && r.three_m !== undefined) yieldVals.push(Number(r.three_m));
    });
    const minY = Math.floor((Math.min(...yieldVals) - 0.03) * 100) / 100;
    const maxY = Math.ceil((Math.max(...yieldVals) + 0.03) * 100) / 100;
    const yYield = v => upper.top + (maxY - v) * upper.height / (maxY - minY || 1);

    for(let i=0;i<=3;i++){
      const val = minY + (maxY-minY)*i/3;
      const yy = yYield(val);
      make("line",{x1:margin.left,y1:yy,x2:width-margin.right,y2:yy,stroke:"rgba(148,163,184,.15)","stroke-dasharray":"4 6"});
      make("text",{x:margin.left-9,y:yy+4,"text-anchor":"end",fill:"#92a3bc","font-size":"10"}, `${val.toFixed(2)}%`);
    }

    const drawLine = (field, color, widthPx, label) => {
      const pts = rows.map((r,i) => {
        const v = r[field];
        return v === null || v === undefined ? null : [x(i), yYield(Number(v)), Number(v)];
      }).filter(Boolean);
      if(pts.length >= 2){
        const d = pts.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p[0]} ${p[1]}`).join(" ");
        make("path",{d,fill:"none",stroke:color,"stroke-width":widthPx,"stroke-linecap":"round","stroke-linejoin":"round"});
      }
      pts.forEach((p, idx)=>make("circle",{cx:p[0],cy:p[1],r:idx===pts.length-1?4.4:3.1,fill:color,stroke:"#07101f","stroke-width":"1.1"}));
      const last = pts[pts.length-1];
      if(last) make("text",{x:last[0]+8,y:last[1]+4,fill:color,"font-size":"11","font-weight":"900"}, `${label} ${last[2].toFixed(3)}%`);
    };

    drawLine("ten_y", "#60a5fa", 2.8, "10Y");
    drawLine("two_y", "#facc15", 2.8, "2Y");
    drawLine("three_m", "#fb7185", 2.2, "3M");

    // Gap lines
    const last = rows[rows.length-1];
    if(last.ten_y !== null && last.two_y !== null && last.ten_y !== undefined && last.two_y !== undefined){
      const xx = x(rows.length-1);
      const y10 = yYield(Number(last.ten_y));
      const y2 = yYield(Number(last.two_y));
      make("line",{x1:xx,y1:y10,x2:xx,y2:y2,stroke:"rgba(87,216,255,.6)","stroke-width":"3","stroke-dasharray":"4 4"});
      make("text",{x:xx-8,y:Math.min(y10,y2)-10,"text-anchor":"end",fill:"#57d8ff","font-size":"11","font-weight":"900"}, `gap ${Number(last.spread_bp).toFixed(1)}bp`);
    }
  }else{
    make("text",{x:"50%",y:upper.top + upper.height/2,"text-anchor":"middle",fill:"#92a3bc","font-size":"13"},"暂无 2Y/10Y/3M 利率曲线");
  }

  // Spread panels: 2s10s + 2s3m
  const spreadVals = rows.map(r => Number(r.spread_bp));
  const minS = Math.floor((Math.min(...spreadVals) - 4) / 5) * 5;
  const maxS = Math.ceil((Math.max(...spreadVals) + 4) / 5) * 5;

  const two3mRows = (data.two3m_series || []).slice(-60);
  const m3Vals = two3mRows.map(r => Number(r.spread_bp));
  const m3min = m3Vals.length ? Math.floor((Math.min(...m3Vals) - 4) / 5) * 5 : 0;
  const m3max = m3Vals.length ? Math.ceil((Math.max(...m3Vals) + 4) / 5) * 5 : 10;

  // 2s10s spread
  const ySpread = v => lower1.top + (maxS - v) * lower1.height / (maxS - minS || 1);
  for(let i=0;i<=2;i++){
    const val = minS + (maxS-minS)*i/2;
    const yy = ySpread(val);
    make("line",{x1:margin.left,y1:yy,x2:width-margin.right,y2:yy,stroke:"rgba(148,163,184,.14)","stroke-dasharray":"4 6"});
    make("text",{x:margin.left-9,y:yy+4,"text-anchor":"end",fill:"#92a3bc","font-size":"10"}, `${val.toFixed(0)}bp`);
  }
  const spreadPath = rows.map((r,i) => `${i===0 ? "M" : "L"} ${x(i)} ${ySpread(Number(r.spread_bp))}`).join(" ");
  make("path",{d:spreadPath,fill:"none",stroke:"#57d8ff","stroke-width":"2.8","stroke-linecap":"round","stroke-linejoin":"round"});
  rows.forEach((r,i)=>{
    const curr = Number(r.spread_bp);
    const prev = i > 0 ? Number(rows[i-1].spread_bp) : curr;
    const fill = curr > prev ? "#54d18a" : curr < prev ? "#ff9d42" : "#57d8ff";
    make("circle",{cx:x(i),cy:ySpread(curr),r:i===rows.length-1 ? 4.6 : 3.1,fill,stroke:"#07101f","stroke-width":"1.1"});
  });

  // 2s3m spread
  if(two3mRows.length > 1){
    const yM3 = v => lower3.top + (m3max - v) * lower3.height / (m3max - m3min || 1);
    for(let i=0;i<=2;i++){
      const val = m3min + (m3max-m3min)*i/2;
      const yy = yM3(val);
      make("line",{x1:margin.left,y1:yy,x2:width-margin.right,y2:yy,stroke:"rgba(148,163,184,.14)","stroke-dasharray":"4 6"});
      make("text",{x:margin.left-9,y:yy+4,"text-anchor":"end",fill:"#92a3bc","font-size":"10"}, `${val.toFixed(0)}bp`);
    }
    const m3Path = two3mRows.map((r,i) => `${i===0 ? "M" : "L"} ${x(i)} ${yM3(Number(r.spread_bp))}`).join(" ");
    make("path",{d:m3Path,fill:"none",stroke:"#a78bfa","stroke-width":"2.8","stroke-linecap":"round","stroke-linejoin":"round"});
    two3mRows.forEach((r,i)=>{
      const curr = Number(r.spread_bp);
      const prev = i > 0 ? Number(two3mRows[i-1].spread_bp) : curr;
      const fill = curr > prev ? "#54d18a" : curr < prev ? "#ff9d42" : "#a78bfa";
      make("circle",{cx:x(i),cy:yM3(curr),r:i===two3mRows.length-1 ? 4.6 : 3.1,fill,stroke:"#07101f","stroke-width":"1.1"});
    });
  }

  // X labels
  const labelIdxs = Array.from(new Set([0, Math.floor((rows.length-1)/2), rows.length-1]));
  labelIdxs.forEach(i => {
    make("line",{x1:x(i),y1:upper.top,x2:x(i),y2:lower3.top+lower3.height,stroke:"rgba(148,163,184,.10)"});
    make("text",{x:x(i),y:height-14,"text-anchor":"middle",fill:"#92a3bc","font-size":"10"}, rows[i].date);
  });

  // Legend
  const legendX = width - 280;
  make("rect",{x:legendX,y:10,width:250,height:28,rx:12,fill:"rgba(7,11,20,.55)",stroke:"rgba(148,163,184,.18)"});
  make("circle",{cx:legendX+16,cy:24,r:4,fill:"#60a5fa"});
  make("text",{x:legendX+25,y:28,fill:"#cbd7ea","font-size":"10"},"10Y");
  make("circle",{cx:legendX+70,cy:24,r:4,fill:"#facc15"});
  make("text",{x:legendX+79,y:28,fill:"#cbd7ea","font-size":"10"},"2Y");
  make("circle",{cx:legendX+118,cy:24,r:4,fill:"#fb7185"});
  make("text",{x:legendX+127,y:28,fill:"#cbd7ea","font-size":"10"},"3M");
  make("circle",{cx:legendX+170,cy:24,r:4,fill:"#57d8ff"});
  make("text",{x:legendX+179,y:28,fill:"#cbd7ea","font-size":"10"},"2s10s");
  make("circle",{cx:legendX+228,cy:24,r:4,fill:"#a78bfa"});
  make("text",{x:legendX+237,y:28,fill:"#cbd7ea","font-size":"10"},"2s3m");

  const last = rows[rows.length-1];
  make("text",{x:width-margin.right,y:lower1.top+lower1.height+16,"text-anchor":"end",fill:"#cfe6ff","font-size":"11","font-weight":"900"}, `2s10s: ${Number(last.spread_bp).toFixed(1)} bp`);
  if(two3mRows.length){
    make("text",{x:width-margin.right,y:lower3.top+lower3.height+16,"text-anchor":"end",fill:"#cfe6ff","font-size":"11","font-weight":"900"}, `2s3m: ${Number(two3mRows[two3mRows.length-1].spread_bp).toFixed(1)} bp`);
  }
}


function renderCurveTable(data){
  const rows = data.curve_comparison || [];
  const table = $("curveTable");
  if(!rows.length){
    table.innerHTML = `<thead><tr><th>日期</th><th>Dec-26 / Z26</th><th>Mar-27 / H27</th><th>Jun-27 / M27</th></tr></thead><tbody><tr><td colspan="4">暂无曲线数据</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead><tr><th>日期</th><th>标记</th><th>Dec-26 / Z26</th><th>Mar-27 / H27</th><th>Jun-27 / M27</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${escapeHtml(r.date)}</td>
        <td>${escapeHtml(r.label || r.date)}</td>
        <td>${fmtPct(r.rates?.Z26)}</td>
        <td>${fmtPct(r.rates?.H27)}</td>
        <td>${fmtPct(r.rates?.M27)}</td>
      </tr>
    `).join("")}</tbody>
  `;
}

function renderCurveSummary(data){
  const changes = data.curve_bp_changes || [];
  $("curveSummary").innerHTML = changes.map(c => `
    <span class="summary-chip">${escapeHtml(c.label)}: ${c.bp_change === null || c.bp_change === undefined ? "N/A" : `${c.bp_change.toFixed(1)}bp`}</span>
  `).join("");
}

function renderLegend(data){
  const rows = data.curve_comparison || [];
  $("curveLegend").innerHTML = rows.map((r, i) => `
    <span class="legend-item"><i class="legend-dot" style="background:${colors[i % colors.length]}"></i>${escapeHtml(r.label || r.date)}</span>
  `).join("");
}

function renderCurveChart(data){
  const svg = $("curveChart");
  const rows = data.curve_comparison || [];
  const contracts = [
    {code:"Z26", label:"Dec-26"},
    {code:"H27", label:"Mar-27"},
    {code:"M27", label:"Jun-27"},
  ];

  svg.innerHTML = "";
  if(!rows.length){
    svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#92a3bc">暂无 Z26-H27-M27 曲线数据</text>`;
    return;
  }

  const width = 1100, height = 440;
  const margin = {top: 36, right: 26, bottom: 70, left: 68};
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const values = [];
  rows.forEach(r => contracts.forEach(c => {
    const v = r.rates && r.rates[c.code];
    if(v !== null && v !== undefined && !Number.isNaN(v)) values.push(Number(v));
  }));

  const minV = Math.floor((Math.min(...values) - 0.05) * 100) / 100;
  const maxV = Math.ceil((Math.max(...values) + 0.05) * 100) / 100;

  const x = idx => margin.left + (innerW * idx / (contracts.length - 1));
  const y = v => margin.top + (maxV - v) * innerH / (maxV - minV);

  const make = (tag, attrs = {}, text = null) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, v));
    if(text !== null) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  // Background
  make("rect", {x:0,y:0,width,height,rx:18,fill:"rgba(3,7,18,.12)"});

  // Grid and y ticks
  const tickCount = 5;
  for(let i=0;i<=tickCount;i++){
    const val = minV + (maxV-minV)*i/tickCount;
    const yy = y(val);
    make("line", {x1:margin.left,y1:yy,x2:width-margin.right,y2:yy,stroke:"rgba(148,163,184,.18)", "stroke-dasharray":"4 6"});
    make("text", {x:margin.left-12,y:yy+4,"text-anchor":"end",fill:"#92a3bc","font-size":"12"}, `${val.toFixed(2)}%`);
  }

  // X axis
  contracts.forEach((c, idx) => {
    const xx = x(idx);
    make("line", {x1:xx,y1:margin.top,x2:xx,y2:height-margin.bottom,stroke:"rgba(148,163,184,.12)"});
    make("text", {x:xx,y:height-34,"text-anchor":"middle",fill:"#cbd7ea","font-size":"13","font-weight":"700"}, c.label);
    make("text", {x:xx,y:height-16,"text-anchor":"middle",fill:"#92a3bc","font-size":"11"}, c.code);
  });

  // Axes
  make("line", {x1:margin.left,y1:margin.top,x2:margin.left,y2:height-margin.bottom,stroke:"rgba(203,215,234,.45)"});
  make("line", {x1:margin.left,y1:height-margin.bottom,x2:width-margin.right,y2:height-margin.bottom,stroke:"rgba(203,215,234,.45)"});
  make("text", {x:20,y:margin.top+innerH/2,fill:"#92a3bc","font-size":"13",transform:`rotate(-90 20 ${margin.top+innerH/2})`}, "Implied Rate (%)");

  // Highlight last curve area
  const last = rows[rows.length - 1];
  const lastRates = contracts.map(c => last.rates?.[c.code]);
  const maxIdx = lastRates.indexOf(Math.max(...lastRates.filter(v => v !== null && v !== undefined)));
  if(maxIdx >= 0){
    const xx = x(maxIdx);
    const yy = y(lastRates[maxIdx]);
    make("line", {x1:xx,y1:yy,x2:xx,y2:height-margin.bottom,stroke:"rgba(245,200,75,.45)","stroke-dasharray":"5 5"});
    make("text", {x:xx+10,y:yy-12,fill:"#ffe49a","font-size":"13","font-weight":"900"}, `最新峰值 ${contracts[maxIdx].label}: ${lastRates[maxIdx].toFixed(3)}%`);
  }

  // Curves
  rows.forEach((r, i) => {
    const color = colors[i % colors.length];
    const pts = contracts.map((c, idx) => {
      const v = r.rates?.[c.code];
      return v === null || v === undefined ? null : [x(idx), y(Number(v)), Number(v)];
    }).filter(Boolean);

    if(pts.length >= 2){
      const d = pts.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p[0]} ${p[1]}`).join(" ");
      make("path", {d, fill:"none", stroke:color, "stroke-width": i === rows.length - 1 ? 3.6 : 2.2, "stroke-linecap":"round", "stroke-linejoin":"round", opacity: i === rows.length - 1 ? 1 : .72});
    }
    pts.forEach(p => {
      make("circle", {cx:p[0], cy:p[1], r:i === rows.length - 1 ? 5.2 : 4, fill:color, stroke:"#07101f", "stroke-width":"1.5"});
    });
  });

  // First-to-last annotation
  const changes = data.curve_bp_changes || [];
  if(changes.length){
    const maxChange = changes.reduce((a,b) => (b.bp_change ?? -999) > (a.bp_change ?? -999) ? b : a, changes[0]);
    if(maxChange && maxChange.bp_change !== null && maxChange.bp_change !== undefined){
      make("rect", {x:width-292,y:26,width:260,height:58,rx:14,fill:"rgba(245,200,75,.12)",stroke:"rgba(245,200,75,.45)"});
      make("text", {x:width-274,y:50,fill:"#ffe49a","font-size":"13","font-weight":"900"}, "最强累计重定价");
      make("text", {x:width-274,y:72,fill:"#fff7d6","font-size":"18","font-weight":"900"}, `${maxChange.label}: +${maxChange.bp_change.toFixed(1)}bp`);
    }
  }
}

function escapeHtml(s){
  return String(s ?? "").replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}

async function main(){
  const data = await loadData();
  renderWarnings(data);
  renderHero(data);
  renderQuestionCards(data);
  renderCurveChart(data);
  renderLegend(data);
  renderCurveSummary(data);
  renderCurveTable(data);
  renderKpis(data);
  renderReferencePeaks(data);
  renderDetails(data);
  renderTwos10s(data);
  renderRetracement(data);
  renderSignalMatrix(data);
}

main();
