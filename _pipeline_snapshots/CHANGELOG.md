# 报告生成管线 · 版本归档日志

> 目录 `_pipeline_snapshots/` 存放「日报 & 风险演化流程图生成」管线的完整快照。
> 每次管线有重要修改时，递增版本号，把最新全部脚本复制到新版本子目录，并在此记录变更。

---

## 版本列表

| 版本 | 日期 | 说明 |
|------|------|------|
| [v1.1](./v1.1/) | 2026-06-10 (19:47) | 审计修复版：Reserve 单位、HY OAS 箭头、§②/§③ 字母碰撞、VTS 双比率等 7 项 |
| [v1.0](./v1.0/) | 2026-06-10 | 初始归档：ABCD 四端框架 + 风险看板 PNG + 风险演化流程图 HTML v4 |

---

## 管线概览

```
run_daily.py
│
├─ Step 1: fetch_yahoo_local.py  →  yahoo_series.json  (FXY/HYG/SPY/GLD)
├─ Step 2: fetch_data.py         →  series.json        (FRED + Yahoo + CoinGecko)
└─ Step 3: daily_report.py --md
    ├─ daily_{date}.md                    → report/
    ├─ risk_dashboard_{date}.md           → report/
    ├─ risk_dashboard_{date}.png          → report/
    └─ risk_flowchart_{date}.html         → daily_archive/{YYYY-MM}/
       (通过 generate_risk_dashboard.py + generate_risk_flowchart.py subprocess)
```

### 脚本职责速查

| 脚本 | 角色 | 大小 |
|------|------|------|
| `run_daily.py` | 编排器：按顺序调用 Step 1→3 | 3.3 KB |
| `fetch_yahoo_local.py` | 本地 Yahoo 数据抓取（FXY/HYG/SPY/GLD），写 yahoo_series.json | 3.4 KB |
| `fetch_data.py` | FRED + Yahoo + CoinGecko 实时抓取，merge 后写 series.json | 20.2 KB |
| `daily_report.py` | **核心引擎**：ABCD 信号计算、regime 判定、触发条件评估，输出 daily/risk_dashboard MD，调 subprocess 生成 PNG + HTML | 126.5 KB |
| `generate_risk_dashboard.py` | 从 daily_report 计算管线读数据 → 四模块文字表格 + PNG 可视化 | 19.8 KB |
| `generate_risk_flowchart.py` | 从 daily_{date}.md 提取信号 → 生成「前端风险 → 系统性风险演化流程图」HTML (v4) | 24.4 KB |
| `requirements.txt` | 依赖：requests, yfinance, openpyxl, markdown, beautifulsoup4, lxml | 106 B |

---

## 运行方式

### 一键运行（推荐）
```powershell
cd D:\liquidity-dashboard\v3.5
uv run python -X utf8 daily_report.py --md
```

### 完整数据抓取+报告
```powershell
cd D:\liquidity-dashboard
uv run python v3.5/run_daily.py
```

### 只生成报告（不抓数据）
```powershell
cd D:\liquidity-dashboard
uv run python v3.5/run_daily.py --skip-fetch
```

### 单独生成风险演化流程图
```powershell
cd D:\liquidity-dashboard\v3.5
uv run python -X utf8 generate_risk_flowchart.py --date 2026-06-10
```

---

## 关键依赖关系

- `generate_risk_dashboard.py` **import** `daily_report` 模块的计算函数（load_data, compute_v35_triggers, compute_abcd_signals 等）
- `generate_risk_flowchart.py` 独立运行，从 `report/daily_{date}.md` 文本解析提取信号，不 import 其他模块
- `daily_report.py` 通过 `subprocess.run` 调用 `generate_risk_dashboard.py` 和 `generate_risk_flowchart.py`
- `fetch_data.py` 需要 `FRED_API_KEY` 环境变量；fallback 读 `yahoo_series.json`

## 输出路径

所有输出相对于 `D:\liquidity-dashboard\`：
- `liquidity-dashboard\report\daily_{date}.md`
- `liquidity-dashboard\report\risk_dashboard_{date}.md`
- `liquidity-dashboard\report\risk_dashboard_{date}.png`
- `v3.5\daily_archive\{YYYY-MM}\risk_flowchart_{date}.html`

---

## v1.0 (2026-06-10) — 初始归档

### 包含文件
所有 7 个文件已复制到 `v1.0/`：

| 文件 | 最后修改 |
|------|---------|
| daily_report.py | 2026-06-10 15:33 |
| generate_risk_dashboard.py | 2026-06-10 14:30 |
| generate_risk_flowchart.py | 2026-06-10 15:48 |
| run_daily.py | 2026-06-10 15:36 |
| fetch_data.py | 2026-06-08 15:57 |
| fetch_yahoo_local.py | 2026-06-08 14:59 |
| requirements.txt | 2026-06-10 15:33 |

### 此版本关键特性
- **ABCD 四域框架**：A(美联储) / B(利率曲线) / C(信用利差) / D(资金流/跨资产)
- **v3.5 触发条件**：HY OAS、IG OAS、FXY 5d 变动率等
- **CASC / VTS / RCV** 联合仓位信号
- **风险看板 (risk_dashboard)**：四模块文字版 MD + 可视化 PNG
- **风险演化流程图 (risk_flowchart)**：v4 升级 — clip-path 箭头、badge/check-list CSS、底部动态横幅
- **paper_trade 已废弃**，被 risk_dashboard 替代

---

> **归档规则**：下次修改管线脚本时 → 新版本号（v1.1, v1.2 …）→ `mkdir _pipeline_snapshots/v新版本` → 复制全部脚本 → 在此 CHANGELOG 顶部追加变更记录。

---

## v1.1 (2026-06-10 19:47) — 审计修复版

基于 2026-06-10 日更 + dashboard 双份审计报告，修复 7 项问题。

### 变更文件
- `daily_report.py` — 5 处修复
- `generate_risk_flowchart.py` — 2 处修复

### 🔴 严重修复

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| 1 | Reserve 单位 `3.01%` → `$3.01T` | `daily_report.py` | `_indicator_row()` 新增 `"trillion"` unit → `f"${cur_val:.2f}T"` |
| 2 | HY OAS 趋势箭头 `▲` 误判（20dΔ=-7bp 应收缩） | `daily_report.py` | 触发距离表 `trend_arrow(..., 5)` → `trend_arrow(..., 20)`，箭头与表中 20dΔ 对齐 |
| 3 | §② A/C 端字母 vs §③ 触发器 A/B/C 口径碰撞 | `generate_risk_flowchart.py` | 触发器 `A/B/C` → `T1/T2/T3`，变量 `trig_a/b/c` → `trig_t1/t2/t3` |

### 🟡 次要修复

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| 4 | VTS 只显示一端 → contango/backwardation 字面矛盾 | `generate_risk_flowchart.py` | 新增双比率 regex 提取 + `vts_display`：`VTS 背端=contango(0.910) · 前端=前端紧张(1.041)` |
| 5 | HY OAS 混用 %/bp 单位 | `daily_report.py` | Drawdown Warning + 信号检查表 `hy_oas_pct%` → `hy_oas_pct*100:.0fbp` |
| 6 | CASC FX 行「状态」列为触发阈值，与其他行的「当前态」语义不同 | `daily_report.py` | 表头 `状态` → `当前态 (Watch)`；FX 行 `fx_thr` → `f"{'抬升' if mutated else '平静'} (Watch {fx_thr})"` |
| 7 | Mortgage 表内无 stale 标签 | `daily_report.py` | `_indicator_row()` 新增 `stale_note` 参数；B 端 Mortgage 行自动计算并显示 ` (last_date, Nd stale)` |

### 已验证

```
✅ Reserve: $3.01T  (was 3.01%)
✅ HY OAS arrow: ▼  (was ▲)
✅ Flowchart triggers: T1/T2/T3  (was A/B/C)
✅ VTS display: 背端=contango(0.910) · 前端=前端紧张(1.041)
✅ HY OAS unit: 275bp  (was 2.75%)
✅ CASC header: 当前态 (Watch)  (was 状态)
✅ Mortgage: Mortgage (2026-06-04, 6d stale)
```

### 🔒 口径锁定 (2026-06-10 20:41)

**stale 天数统一为日历日**：`check_staleness()` 和 `_indicator_row(stale_note=...)` 均使用 `(today - last_date).days`（自然日差），不用交易日。审计报告同步对齐。今后 stale 计数一率日历日，不再区分交易日/日历日。
