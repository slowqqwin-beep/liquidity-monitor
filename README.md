# Liquidity Monitor — Three-Layer Framework

A self-hosted liquidity dashboard for the post-2022 macro regime, where long-bond
yields no longer cleanly price liquidity and traditional monitors miss the framework
shift toward fiscal dominance / sovereign-debasement signals.

Hosted entirely on GitHub Pages. Data refreshed daily via GitHub Actions.

![preview](docs/preview.png)

## What this dashboard adds vs. a typical rates & credit monitor

Most professional liquidity dashboards cover **system plumbing** (repo, reserves,
SOFR–IORB, cross-currency basis) and **risk appetite** (HY/IG OAS, MOVE, VIX) well.
They almost universally miss the third layer that has become essential since 2022:

| Layer | What it measures | Typical dashboards | This dashboard |
|---|---|---|---|
| **I. System plumbing** | Repo, reserves, RRP, money-market spreads | ✅ | ✅ |
| **II. Risk appetite** | Credit OAS, vol indices | ✅ (often missing MOVE) | ✅ |
| **III. Framework** | Gold/yield ratio, term premium, stablecoins, 5y5y forward | ❌ | ✅ |

The framework layer answers: **is the market repricing the sovereign claim itself?**
Without it, you can see "everything's fine" right up until you can't — because in a
fiscal-dominance regime, framework switches *precede* plumbing stress by months.

---

## Quick start

### 1. Fork or clone this repository

You need your own GitHub repo so that GitHub Actions can commit data updates back to it.

### 2. Get a free FRED API key

Register at <https://fred.stlouisfed.org/docs/api/api_key.html>. Takes 30 seconds.

### 3. Add the key as a repository secret

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `FRED_API_KEY`
- Value: your FRED key

### 4. Enable GitHub Pages

In your repo: **Settings → Pages → Source: Deploy from a branch → Branch: main / (root)**

After a minute, your dashboard will be live at:
```
https://<your-username>.github.io/<repo-name>/
```

### 5. Trigger the first data fetch

In your repo: **Actions → Update Liquidity Data → Run workflow**

After ~2 minutes, the workflow commits real data to `/data/`, and your dashboard
will refresh with live numbers on next load.

The workflow then runs automatically every weekday at 22:00 UTC.

---

## Indicator coverage

### Layer I — System Plumbing

| Indicator | Source | What it tells you |
|---|---|---|
| SOFR, IORB, EFFR | FRED | Short-end corridor — where overnight cash actually clears |
| Fed funds target (upper/lower) | FRED | Policy bracket |
| ON RRP balance | FRED | Excess cash parked at Fed; drain funds duration absorption |
| Reserve balances (WRESBAL) | FRED | Reserves in the banking system |
| Treasury General Account | FRED | TGA rebuild pulls liquidity out |
| Fed total assets (WALCL) | FRED | QT pace |
| **SOFR – IORB spread** | derived | Positive = banks lending into repo, reserves becoming scarce |
| **EFFR – IORB spread** | derived | Direct reserve scarcity gauge |

### Layer II — Risk Appetite

| Indicator | Source | What it tells you |
|---|---|---|
| HY OAS (BAMLH0A0HYM2) | FRED | Junk credit conditions |
| IG OAS (BAMLC0A0CM) | FRED | Investment grade conditions |
| EM Corp OAS | FRED | Emerging market corporate credit |
| MOVE Index | Stooq | Bond market implied vol — leads HY by weeks |
| VIX (VIXCLS) | FRED | Equity vol |
| **HY / IG ratio** | derived | Risk-tier divergence |

### Layer III — Framework

| Indicator | Source | What it tells you |
|---|---|---|
| 10Y nominal / TIPS / breakeven | FRED | Yield decomposition |
| **5Y5Y forward inflation (T5YIFR)** | FRED | Cleanest long-term inflation expectation |
| **10Y term premium (THREEFYTP10)** | FRED (NY Fed ACM) | The "non-rate, non-inflation" residual — fiscal/credit risk |
| Gold (LBMA AM) | FRED | The framework signal |
| **Gold / 10Y yield ratio** | derived | The cleanest single regime indicator |
| **Stablecoin aggregate market cap** | CoinGecko | USDT+USDC+DAI+FDUSD — non-sovereign dollar liquidity |
| Bitcoin | CoinGecko | Alternative monetary asset |
| 30Y Mortgage – 10Y spread | derived | Real-economy credit transmission |
| Dollar index (DTWEXBGS) | FRED | Trade-weighted broad dollar |

### Excluded (require paid feeds)

- Cross-currency basis swaps (EUR/JPY/AUD/GBP/CAD vs USD) — partial proxies via FRED swap rates
- CDX NA IG / HY indices
- Bank CDS (BofA, JPM, DB sub) — partly proxied via banking-sector OAS

---

## Repository layout

```
liquidity-dashboard/
├── index.html                    # Dashboard page
├── css/style.css                 # Editorial dark theme
├── js/dashboard.js               # Chart logic
├── risk_dashboard_latest.md      # ABCD v3.5 Risk Evolution Dashboard (auto-updated)
├── data/
│   ├── series.json               # All time series (auto-updated)
│   ├── metadata.json             # Generation timestamp + series catalog
│   ├── mm_calendar.json          # MacroMicro filtered calendar events (auto-updated)
│   └── mm_calendar.ics           # Optional: manually downloaded calendar snapshot
├── scripts/
│   ├── fetch_data.py             # Pulls from FRED + CoinGecko + Stooq
│   ├── fetch_mm_calendar.py      # Pulls MacroMicro Google Calendar iCal feed
│   ├── update_event_window.py    # Auto-updates §① near-term event risk section
│   ├── build_site.py             # Generates docs/index.html + docs/risk/index.html
│   ├── local_auto_push.py        # Local file watcher → auto git push
│   ├── generate_demo_data.py     # Synthetic seed for first deploy
│   └── requirements.txt
├── .github/workflows/
│   ├── update-data.yml           # Daily FRED data auto-update
│   └── build-pages.yml           # Hourly MM calendar + site rebuild
├── docs/                         # GitHub Pages output (auto-generated)
│   ├── index.html                # Fed Reaction Dashboard
│   └── risk/
│       └── index.html            # Risk Evolution Dashboard
└── README.md
```

---

## Reading the matrix

The dashboard's bottom section ("Reading the matrix") encodes the three regime states:

1. **L1 healthy + L2 tight + L3 framework switch** → current regime since late 2023.
   Sustainable until L1 or L2 breaks. *Risk-on in real assets while gold grinds higher.*

2. **L1 healthy + L2 widens + L3 framework switch** → the inflection.
   HY breaks above 4% from the sub-3% floor. *6–12 month signal for risk drawdown.*
   This is where AI/hyperscaler capex meets its credit constraint.

3. **L1 stress (any other state)** → pipe blockage. SOFR–IORB persistently positive,
   RRP drained, TGA volatile. *All bets off* — every framework loses to liquidity flight.
   2008, 2020, 2023 March all started here.

---

## Customizing

### Add a new indicator

1. Add to `FRED_SERIES` list in `scripts/fetch_data.py` with an appropriate layer tag.
2. Add a panel to `index.html` with a `<canvas id="chart-...">`.
3. Add a `baseChart(...)` call in `js/dashboard.js`.

### Change lookback window

Set the `LOOKBACK_YEARS` env var in the workflow. Default is 3.

### Run locally

```bash
# Install deps
pip install -r scripts/requirements.txt

# Generate demo data
python scripts/generate_demo_data.py

# (or fetch real data with your FRED key)
export FRED_API_KEY=your_key
python scripts/fetch_data.py

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

---

## Notes & limits

- FRED daily series typically lag by 1 business day; weekly series (WRESBAL, WTREGEN, WALCL) by ~1 week.
- CoinGecko free tier limits historical depth to ~365 days. Stablecoin and BTC charts will show ~1 year max.
- Stooq's MOVE feed is best-effort; if it fails the chart will be empty. Replace with a paid feed if you need guaranteed coverage.
- Term premium (THREEFYTP10) is the NY Fed's ACM model estimate, updated monthly with a small lag.
- All times in UTC.

---

## Why this exists

Built to support a specific macro thesis: that since 2022, the bond market is no
longer a clean liquidity gauge — long-yields rise on fiscal/credit risk premia
(not just inflation or growth), and gold + equities + yields can rise together.
Standard rates dashboards miss this entirely. This one foregrounds it.

---

## MM 财经日历自动更新

### 数据源

MacroMicro（财经 M 平方）Google Calendar iCal 订阅源。URL 为**动态订阅源**，每次运行脚本都会重新 `requests.get()` 下载最新 `basic.ics`，不是本地静态文件。

```
https://calendar.google.com/calendar/ical/c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e%40group.calendar.google.com/public/basic.ics
```

### 处理流程

```
basic.ics (订阅源)
    │  fetch_mm_calendar.py 每次请求最新
    ▼
data/mm_calendar.json  (筛选后：未来10天美国/宏观事件 + 权重评分)
    │  update_event_window.py 选score最高事件
    ▼
risk_dashboard_latest.md §① 近端事件风险 (自动改写)
    │  build_site.py 生成HTML
    ▼
docs/risk/index.html (GitHub Pages 自动展示)
```

### 关键脚本

| 脚本 | 功能 |
|------|------|
| `scripts/fetch_mm_calendar.py` | 下载 iCal → 解析 VEVENT → 筛选未来10天 → 权重评分 → 输出 JSON |
| `scripts/update_event_window.py` | 读取 JSON → 选主事件 → 改写 `risk_dashboard_latest.md` §① |
| `scripts/build_site.py` | 生成 `docs/index.html` + `docs/risk/index.html` |
| `scripts/local_auto_push.py` | 本地文件监听 → 自动 git push（手动修改 Markdown/JSON 后触发） |

### 定时更新

GitHub Actions (`.github/workflows/build-pages.yml`) 每小时运行一次，自动抓取最新 MM 日历并更新页面。也可以手动触发 `workflow_dispatch`。

### 事件筛选规则

- 默认只保留美国事件和 Powell / FOMC 相关
- 权重体系：FOMC > CPI > PCE > 非农 > Powell > PPI > ISM > 初请
- 事件分数：`score = weight - days_to_event × 5`
- 取 score 最高者作为近端主事件

### 注意事项

- **basic.ics URL 是动态订阅源**，不是静态文件。手动下载的 `.ics` 是快照，程序每次运行都会重新请求 URL。
- `data/mm_calendar.json` 是筛选后的结构化事件数据，不是原始 ics。
- `risk_dashboard_latest.md` 的 `## ① 近端事件风险` 段由 `update_event_window.py` 自动改写，只替换这一段。
- `docs/risk/index.html` 由 `build_site.py` 自动生成。
- GitHub Pages 使用 `docs/` 目录发布。
- 正常情况 MM 日历自动更新由 GitHub Actions schedule 完成，本地手动触发用 `local_auto_push.py`。
