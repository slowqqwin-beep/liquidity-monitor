/* =====================================================
   Liquidity Monitor — Dashboard Logic
   ===================================================== */

// Color palette mirrors CSS variables
const C = {
  ink:      '#e8e6e1',
  inkMute:  '#9a988f',
  inkDeep:  '#6a6862',
  good:     '#6dd3a3',
  stress:   '#e08363',
  gold:     '#d4a657',
  data:     '#87a4c4',
  violet:   '#b094c8',
  amber:    '#d6b37c',
  line:     'rgba(232, 230, 225, 0.10)',
  lineWeak: 'rgba(232, 230, 225, 0.05)',
};

// Chart.js global defaults
Chart.defaults.color = C.inkMute;
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 11;
Chart.defaults.borderColor = C.line;

// =====================================================
// Data loading
// =====================================================

async function loadData() {
  try {
    const [seriesRes, metaRes] = await Promise.all([
      fetch('data/series.json'),
      fetch('data/metadata.json'),
    ]);
    if (!seriesRes.ok || !metaRes.ok) throw new Error('Missing data files');
    return {
      series: await seriesRes.json(),
      metadata: await metaRes.json(),
    };
  } catch (e) {
    showErrorBanner(
      'Could not load data files. Run the GitHub Action to populate /data/series.json. ' +
      'Add FRED_API_KEY to repository secrets, then trigger Actions → Update Liquidity Data → Run workflow.'
    );
    throw e;
  }
}

function showErrorBanner(msg) {
  const banner = document.createElement('div');
  banner.className = 'error-banner';
  banner.textContent = msg;
  document.querySelector('main').prepend(banner);
}


// =====================================================
// Helpers
// =====================================================

const fmt = (n, dp = 2) =>
  n == null || isNaN(n) ? '—' : Number(n).toLocaleString('en-US', {
    minimumFractionDigits: dp, maximumFractionDigits: dp,
  });

const fmtCompact = (n) => {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (abs >= 1e3) return (n / 1e3).toFixed(2) + 'K';
  return fmt(n);
};

const last = (arr) => arr && arr.length ? arr[arr.length - 1] : null;

const lookback = (arr, days) => {
  if (!arr || arr.length === 0) return null;
  const target = new Date(arr[arr.length - 1].date);
  target.setDate(target.getDate() - days);
  const targetStr = target.toISOString().slice(0, 10);
  // Find first observation on/after target
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i].date <= targetStr) return arr[i];
  }
  return arr[0];
};

const toXY = (arr) => arr.map(d => ({ x: d.date, y: d.value }));


// =====================================================
// Chart factory — common config
// =====================================================

function baseChart(canvasId, datasets, opts = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const config = {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: opts.legend !== false,
          position: 'top',
          align: 'end',
          labels: {
            boxWidth: 8,
            boxHeight: 8,
            padding: 14,
            usePointStyle: true,
            pointStyle: 'rectRounded',
            font: { size: 10.5, weight: '500' },
          },
        },
        tooltip: {
          backgroundColor: '#0b0d10',
          borderColor: C.line,
          borderWidth: 1,
          titleColor: C.ink,
          bodyColor: C.ink,
          padding: 12,
          titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
          cornerRadius: 0,
          displayColors: true,
          boxWidth: 8,
          boxHeight: 8,
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${fmt(ctx.parsed.y, opts.dp ?? 2)}${opts.suffix || ''}`,
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: opts.timeUnit || 'month', displayFormats: { month: 'MMM yy' } },
          grid: { color: C.lineWeak, drawTicks: false },
          ticks: { maxRotation: 0, autoSkipPadding: 24 },
          border: { color: C.line },
        },
        y: {
          grid: { color: C.lineWeak, drawTicks: false },
          ticks: {
            padding: 8,
            callback: (v) => `${fmt(v, opts.yDp ?? 1)}${opts.ySuffix || ''}`,
          },
          border: { display: false },
          ...(opts.yAxis || {}),
        },
        ...(opts.extraScales || {}),
      },
      elements: {
        line: { tension: 0.15, borderWidth: 1.4 },
        point: { radius: 0, hoverRadius: 3 },
      },
    },
  };

  return new Chart(ctx, config);
}

const ds = (label, data, color, extra = {}) => ({
  label,
  data: toXY(data || []),
  borderColor: color,
  backgroundColor: extra.fill ? color + '22' : 'transparent',
  fill: extra.fill || false,
  borderWidth: extra.width || 1.4,
  borderDash: extra.dash || [],
  yAxisID: extra.yAxisID || 'y',
  pointRadius: 0,
  ...extra,
});


// =====================================================
// Card renderer (summary tiles)
// =====================================================

function renderCard(container, { id, label, unit, series, dp = 2, hint }) {
  const cur = last(series);
  if (!cur) return;

  const w = lookback(series, 7);
  const m = lookback(series, 30);
  const wkChange = w ? cur.value - w.value : null;
  const moChange = m ? cur.value - m.value : null;

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `
    <div class="card-label">${label}</div>
    <div class="card-value">${fmt(cur.value, dp)}<span class="card-unit">${unit || ''}</span></div>
    <div class="card-change">
      <span class="${wkChange > 0 ? 'change-pos' : wkChange < 0 ? 'change-neg' : ''}">
        1w ${wkChange != null ? (wkChange >= 0 ? '+' : '') + fmt(wkChange, dp) : '—'}
      </span>
      <span class="${moChange > 0 ? 'change-pos' : moChange < 0 ? 'change-neg' : ''}">
        1m ${moChange != null ? (moChange >= 0 ? '+' : '') + fmt(moChange, dp) : '—'}
      </span>
    </div>
    <canvas class="card-spark" id="spark-${id}"></canvas>
  `;
  container.appendChild(card);

  // Sparkline
  const sparkData = series.slice(-90);
  new Chart(document.getElementById(`spark-${id}`), {
    type: 'line',
    data: {
      datasets: [{
        data: toXY(sparkData),
        borderColor: C.inkMute,
        borderWidth: 1,
        fill: false,
        pointRadius: 0,
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { type: 'time', display: false },
        y: { display: false },
      },
      elements: { line: { borderJoinStyle: 'round' } },
    },
  });
}


// =====================================================
// Main render
// =====================================================

async function main() {
  const { series, metadata } = await loadData();

  // Header meta
  const generated = new Date(metadata.generated_at);
  document.getElementById('updated-at').textContent = generated.toISOString().slice(0, 10);
  document.getElementById('lookback').textContent = `${metadata.lookback_years}Y`;
  document.getElementById('series-count').textContent = metadata.series.length;

  // -----------------------------------------------------
  // LAYER 1 cards
  // -----------------------------------------------------
  const l1 = document.getElementById('l1-cards');
  renderCard(l1, { id: 'sofr',    label: 'SOFR',           unit: '%',  series: series.SOFR,         dp: 2 });
  renderCard(l1, { id: 'sofr_iorb', label: 'SOFR – IORB',  unit: 'bp', series: series.SOFR_IORB,    dp: 1 });
  renderCard(l1, { id: 'rrp',     label: 'ON RRP Balance', unit: '$B', series: series.RRPONTSYD,    dp: 1 });
  renderCard(l1, { id: 'reserves',label: 'Reserve Balances', unit: '$B', series: series.WRESBAL,    dp: 0 });

  // L1 charts
  baseChart('chart-mm-spreads', [
    ds('SOFR – IORB',     series.SOFR_IORB,      C.data),
    ds('EFFR – IORB',     series.EFFR_IORB,      C.violet),
  ], { ySuffix: 'bp', yDp: 1, suffix: 'bp', dp: 2 });

  baseChart('chart-balances', [
    ds('Reserve Balances', series.WRESBAL,    C.data),
    ds('ON RRP',           series.RRPONTSYD,  C.gold),
    ds('TGA',              series.WTREGEN,    C.violet),
  ], { ySuffix: '', yDp: 0, suffix: ' $B', dp: 0 });

  baseChart('chart-on-rates', [
    ds('SOFR',           series.SOFR,      C.ink),
    ds('IORB',           series.IORB,      C.data,   { dash: [4, 4] }),
    ds('EFFR',           series.EFFR,      C.violet, { dash: [4, 4] }),
    ds('Fed Funds Upper', series.DFEDTARU, C.inkDeep, { dash: [2, 4] }),
    ds('Fed Funds Lower', series.DFEDTARL, C.inkDeep, { dash: [2, 4] }),
  ], { ySuffix: '%', yDp: 2, suffix: '%' });

  // -----------------------------------------------------
  // LAYER 2 cards
  // -----------------------------------------------------
  const l2 = document.getElementById('l2-cards');
  renderCard(l2, { id: 'hy_oas', label: 'HY OAS',          unit: '%', series: series.BAMLH0A0HYM2, dp: 2 });
  renderCard(l2, { id: 'ig_oas', label: 'IG OAS',          unit: '%', series: series.BAMLC0A0CM,  dp: 2 });
  renderCard(l2, { id: 'move',   label: 'MOVE Index',      unit: '',  series: series.MOVE,         dp: 1 });
  renderCard(l2, { id: 'vix',    label: 'VIX',             unit: '',  series: series.VIXCLS,       dp: 1 });

  baseChart('chart-credit', [
    ds('HY OAS',         series.BAMLH0A0HYM2, C.stress),
    ds('IG OAS',         series.BAMLC0A0CM,   C.data),
    ds('EM Corp OAS',    series.BAMLEMCBPIOAS, C.violet),
  ], { ySuffix: '%', yDp: 1, suffix: '%' });

  baseChart('chart-vol', [
    ds('MOVE',  series.MOVE,    C.gold,    { yAxisID: 'y'  }),
    ds('VIX',   series.VIXCLS,  C.violet,  { yAxisID: 'y2' }),
  ], {
    yDp: 0, dp: 1,
    yAxis: { position: 'left' },
    extraScales: {
      y2: {
        position: 'right',
        grid: { drawOnChartArea: false },
        border: { display: false },
        ticks: { padding: 8 },
      },
    },
  });

  baseChart('chart-hyig', [
    ds('HY / IG Ratio', series.HY_IG_RATIO, C.amber),
  ], { ySuffix: 'x', yDp: 1, suffix: 'x', dp: 2, legend: false });

  // -----------------------------------------------------
  // LAYER 3 cards
  // -----------------------------------------------------
  const l3 = document.getElementById('l3-cards');
  renderCard(l3, { id: 'gold',     label: 'Gold (LBMA AM)',     unit: '$/oz', series: series.GOLDAMGBD228NLBM, dp: 0 });
  renderCard(l3, { id: 'gold_10y', label: 'Gold / 10Y Yield',   unit: '',     series: series.GOLD_10Y_RATIO,  dp: 0 });
  renderCard(l3, { id: 'tp10',     label: '10Y Term Premium',   unit: '%',    series: series.THREEFYTP10,     dp: 2 });
  renderCard(l3, { id: 'stables',  label: 'Stablecoin Mcap',    unit: '$B',   series: series.STABLECOIN_MCAP_B, dp: 0 });

  baseChart('chart-gold-ratio', [
    ds('Gold / 10Y Yield', series.GOLD_10Y_RATIO, C.gold, { fill: true, width: 1.6 }),
  ], { yDp: 0, dp: 0, legend: false });

  baseChart('chart-yield-decomp', [
    ds('10Y Nominal',    series.DGS10,        C.ink),
    ds('10Y Real (TIPS)', series.DFII10,      C.data),
    ds('10Y Breakeven',  series.T10YIE,       C.amber),
    ds('Term Premium (ACM)', series.THREEFYTP10, C.gold, { dash: [4, 3] }),
  ], { ySuffix: '%', yDp: 2, suffix: '%' });

  baseChart('chart-5y5y', [
    ds('5Y5Y Forward Inflation', series.T5YIFR, C.data, { fill: true, width: 1.6 }),
  ], { ySuffix: '%', yDp: 2, suffix: '%', legend: false });

  baseChart('chart-stables', [
    ds('Stablecoin Aggregate', series.STABLECOIN_MCAP_B, C.gold, { fill: true, width: 1.6 }),
  ], { ySuffix: ' $B', yDp: 0, suffix: ' $B', dp: 1, legend: false });

  // BTC vs Gold rebased to first overlapping date
  const btcRebased = rebase(series.BTC_USD);
  const goldRebased = rebase(series.GOLDAMGBD228NLBM);
  baseChart('chart-btc-gold', [
    ds('Bitcoin (rebased)',  btcRebased,  C.violet),
    ds('Gold (rebased)',     goldRebased, C.gold),
  ], { ySuffix: '', yDp: 0, dp: 0 });

  baseChart('chart-mortgage', [
    ds('30Y Mortgage – 10Y', series.MORTGAGE_SPREAD, C.amber, { fill: true, width: 1.6 }),
  ], { ySuffix: 'bp', yDp: 0, suffix: 'bp', dp: 0, legend: false });
}

// Rebase a series to start at 100
function rebase(series) {
  if (!series || series.length === 0) return [];
  const base = series[0].value;
  return series.map(d => ({ date: d.date, value: (d.value / base) * 100 }));
}

main().catch(err => {
  console.error('Dashboard load failed:', err);
});
