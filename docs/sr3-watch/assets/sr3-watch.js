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
  try{
    const res = await fetch(JSON_URL, {cache:"no-store"});
    if(!res.ok) throw new Error(`JSON fetch failed: ${res.status}`);
    return await res.json();
  }catch(err){
    console.warn(err);
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
  $("heroNote").textContent = data.state_note || "SR3 已钝化，但尚未完成 level repair；当前不是买入信号。";
  $("dataDate").textContent = data.data_date || "N/A";
  $("generatedAt").textContent = data.generated_at || "N/A";
  $("referencePeak").textContent = data.reference_peak || "N/A";
  $("status").textContent = data.status || "Research-Only";
  $("mixedRepairWarning").textContent = data.mixed_repair_warning || fallbackData.mixed_repair_warning;
}

function renderQuestionCards(data){
  const items = [
    {label:"处于 hawkish impulse？", value:boolText(data.hawkish_impulse), sub:"否 = 鹰派冲击不是当前主状态", cls:data.hawkish_impulse ? "red" : "green"},
    {label:"进入 deceleration？", value:boolText(data.deceleration), sub:data.deceleration_since ? `起始：${data.deceleration_since}` : "N/A", cls:data.deceleration ? "yellow" : "gray"},
    {label:"发生 level repair？", value:boolText(data.level_repair), sub:data.level_repair ? "已完成修复" : "未完成修复", cls:data.level_repair ? "green" : "red"},
    {label:"修复分类", value:data.classification || "N/A", sub:"mixed_repair 仅表示混合修复，不代表买入信号", cls:"yellow"},
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
    {label:"较参考峰回落", value:fmt(data.drawdown_from_peak_bp, " bp", 2), cls:data.drawdown_from_peak_bp < 0 ? "good" : "warn"},
    {label:"当日变动", value:fmt(data.daily_change_bp, " bp", 2), cls:data.daily_change_bp < 0 ? "good" : "warn", note:data.daily_change_bp < 0 ? "钝化，但不是买点" : ""},
    {label:"5d 累计", value:fmt(data.five_day_change_bp, " bp", 2), cls:data.five_day_change_bp > 5 ? "warn" : ""},
    {label:"高台 >3.5%", value:boolText(data.high_plateau), cls:data.high_plateau ? "warn" : "good"},
    {label:"HY OAS", value:data.hy_oas === null ? "N/A" : fmt(data.hy_oas, " bp", 1), cls:data.hy_oas === null ? "na" : ""},
    {label:"DGS10", value:data.dgs10 === null ? "N/A" : fmt(data.dgs10, "%", 3), cls:data.dgs10 === null ? "na" : ""},
    {label:"Real Yield Nowcast", value:data.real_yield_nowcast === null ? "N/A" : fmt(data.real_yield_nowcast, "%", 3), cls:data.real_yield_nowcast === null ? "na" : ""},
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
  const rows = data.reference_peaks || [];
  const table = $("referencePeaksTable");
  if(!rows.length){
    table.innerHTML = `<thead><tr><th>来源</th><th>日期</th><th>距今</th><th>near_rate</th><th>高度</th></tr></thead><tbody><tr><td colspan="5">N/A</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead><tr><th>来源</th><th>日期</th><th>距今</th><th>near_rate</th><th>高度</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${escapeHtml(r.source || "N/A")}</td>
        <td>${escapeHtml(r.date || "N/A")}</td>
        <td>${escapeHtml(r.distance || "N/A")}</td>
        <td>${r.near_rate === null || r.near_rate === undefined ? "N/A" : fmt(r.near_rate, "%", 4)}</td>
        <td>${escapeHtml(r.height || "N/A")}</td>
      </tr>
    `).join("")}</tbody>`;
}

function renderDetails(data){
  const rows = [
    ["分类", data.classification || "N/A", "warn"],
    ["原因", data.classification_reason || "N/A", ""],
    ["level_repair", boolText(data.level_repair), data.level_repair ? "ok" : "bad"],
    ["repair", boolText(data.repair), data.repair ? "ok" : "na"],
    ["修复起始日", data.repair_start_date || "N/A", ""],
    ["修复幅度", data.repair_magnitude_bp === null ? "N/A" : fmt(data.repair_magnitude_bp, " bp", 2), "warn"],
  ];
  $("classificationDetails").innerHTML = rows.map(([k,v,cls]) => `
    <div class="detail-row"><span>${escapeHtml(k)}</span><strong class="${cls}">${escapeHtml(v)}</strong></div>
  `).join("");
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
  $("twos10s1d").textContent = latest.change_1d_bp === null || latest.change_1d_bp === undefined ? "N/A" : `${Number(latest.change_1d_bp).toFixed(1)} bp`;
  $("twos10s5d").textContent = latest.change_5d_bp === null || latest.change_5d_bp === undefined ? "N/A" : `${Number(latest.change_5d_bp).toFixed(1)} bp`;
  $("twos10sStructure").textContent = latest.structure || "N/A";
  $("twos10sNote").textContent = latest.structure_note || data.twos10s_warning || "等待 2s10s 数据。";
  renderTwos10sChart(data);
  renderTwos10sTable(data);
}

function renderTwos10sTable(data){
  const rows = (data.twos10s_series || []).slice(-10).reverse();
  const table = $("twos10sTable");
  if(!rows.length){
    table.innerHTML = `<thead><tr><th>日期</th><th>2s10s</th><th>10Y</th><th>2Y</th></tr></thead><tbody><tr><td colspan="4">暂无 2s10s 数据</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead><tr><th>日期</th><th>2s10s</th><th>10Y</th><th>2Y</th></tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${escapeHtml(r.date)}</td>
        <td>${r.spread_bp === null || r.spread_bp === undefined ? "N/A" : `${Number(r.spread_bp).toFixed(1)} bp`}</td>
        <td>${r.ten_y === null || r.ten_y === undefined ? "N/A" : `${Number(r.ten_y).toFixed(3)}%`}</td>
        <td>${r.two_y === null || r.two_y === undefined ? "N/A" : `${Number(r.two_y).toFixed(3)}%`}</td>
      </tr>`).join("")}</tbody>`;
}

function renderTwos10sChart(data){
  const svg = $("twos10sChart");
  const rows = data.twos10s_series || [];
  svg.innerHTML = "";
  if(!rows.length){
    svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#92a3bc">暂无 2s10s 数据</text>`;
    return;
  }

  const width = 560, height = 220;
  const margin = {top: 22, right: 20, bottom: 36, left: 54};
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const dataRows = rows.slice(-30).filter(r => r.spread_bp !== null && r.spread_bp !== undefined);
  if(!dataRows.length){
    svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#92a3bc">暂无 2s10s 数据</text>`;
    return;
  }

  const vals = dataRows.map(r => Number(r.spread_bp));
  const minV = Math.floor((Math.min(...vals) - 5) / 5) * 5;
  const maxV = Math.ceil((Math.max(...vals) + 5) / 5) * 5;
  const x = i => margin.left + (dataRows.length === 1 ? innerW / 2 : innerW * i / (dataRows.length - 1));
  const y = v => margin.top + (maxV - v) * innerH / (maxV - minV || 1);

  const make = (tag, attrs = {}, text = null) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, v));
    if(text !== null) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  for(let i=0;i<=4;i++){
    const val = minV + (maxV-minV)*i/4;
    const yy = y(val);
    make("line",{x1:margin.left,y1:yy,x2:width-margin.right,y2:yy,stroke:"rgba(148,163,184,.18)","stroke-dasharray":"4 6"});
    make("text",{x:margin.left-9,y:yy+4,"text-anchor":"end",fill:"#92a3bc","font-size":"10"}, `${val.toFixed(0)}`);
  }

  const d = dataRows.map((r,i) => `${i===0 ? "M" : "L"} ${x(i)} ${y(Number(r.spread_bp))}`).join(" ");
  make("path",{d,fill:"none",stroke:"#57d8ff","stroke-width":"2.8","stroke-linecap":"round","stroke-linejoin":"round"});
  dataRows.forEach((r,i)=>{
    make("circle",{cx:x(i),cy:y(Number(r.spread_bp)),r:i===dataRows.length-1 ? 4.8 : 3.2,fill:"#57d8ff",stroke:"#07101f","stroke-width":"1.2"});
  });

  const last = dataRows[dataRows.length-1];
  make("text",{x:width-margin.right,y:margin.top+12,"text-anchor":"end",fill:"#cfe6ff","font-size":"12","font-weight":"900"}, `Latest: ${Number(last.spread_bp).toFixed(1)} bp`);
  make("text",{x:margin.left,y:height-10,fill:"#92a3bc","font-size":"10"}, `${dataRows[0].date} → ${last.date}`);
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
  renderSignalMatrix(data);
}

main();
