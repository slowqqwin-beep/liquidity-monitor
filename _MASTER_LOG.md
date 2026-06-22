# v3.5 Risk OS — 主控日志 (Master Log)

> **单文件全量**：合并架构、版本历史、当前状态、管线速查、已知问题。  
> **更新规则**：每次封版/重要变更时，在对应节追加条目。  
> **封版日期**：2026-06-21 21:16 | **版本线**：v3.5.1 (FRED/HY OAS auto-sync + SR3 repair watch + pipeline validate)

---

## 一、项目概述

v3.5 是美国/全球流动性风险监控框架。核心思路：**ABCD 四端框架** → **Risk OS State Machine (SSoT)** → **Dashboard 纯渲染**。

```
A 美元资金管道 → B 信用融资条件 → C 长端利率定价 → D 外汇风险扩散
```

**两轨制**：ABS/DUR=生效，ROLL=评估。Dashboard 不自主计算信号，只渲染 `event_state.json`。

---

## 二、架构 — Risk OS State Machine v1.0 (SSoT)

> **核心原则**：`tools/risk_os_state_machine.py` 是**唯一状态裁决层**。  
> 所有其他系统（daily_report.py、Fed reaction、ABCD）降级为**信号输入层**，不得输出最终结论。

```
┌──────────────────────────────────────────┐
│         🖥️ Dashboard (browser)           │
│   docs/risk/index.html + dashboard.js    │
│   读取 event_state.json → 纯渲染         │
└────────────────┬─────────────────────────┘
                 │ reads
┌────────────────▼─────────────────────────┐
│    ⚖️ Risk OS State Machine (SSoT)      │
│   tools/risk_os_state_machine.py         │
│   读 series.json → 状态机 →             │
│   event_state.json                       │
│   唯一裁决层：R1-R4 + SYSTEMIC/WATCH/    │
│   NON-SYSTEMIC                           │
└────────┬─────────────────────────────────┘
         │ reads                ▲
┌────────▼───────┐    ┌────────┴──────────┐
│  data/         │    │  信号输入层        │
│  series.json   │    │  (降级，不输出结论) │
│  (FRED+Yahoo+  │    ├───────────────────┤
│  CoinGecko+    │    │ daily_report.py   │
│  Stooq)        │    │ → MD 报告          │
└────────────────┘    │ Fed reaction      │
                       │ → Fed dashboard   │
                       └───────────────────┘
```

### 2.1 R1-R4 Regime

| Regime | 条件 | 持仓 (P/H/C) | 含义 |
|--------|------|-------------|------|
| **R1 正常** | red=0, orange=0 | 75/5/20 | 无显著压力 |
| **R2 观察** | red=0, orange≥1 | 55/25/20 | 预警信号出现 |
| **R3 警惕** | red≥1 或 (orange≥1 且 前端active) | 35/35/30 | 信号确认，大幅降风险 |
| **R4 风险释放** | red≥3 | 30/40/30 | 多域压力共振，激进防御 |

### 2.2 Red vs Orange 计数

**Red (已确认系统级信号)**：
1. `real_yield_pressure` — DFII10 ≥ 2.00% DUR5 ≥ 5
2. `T2 liquidity active` — EFFR-IORB ≥ -3bp DUR5 ≥ 3
3. `T1 credit active` — HY OAS ≥ 300bp
4. `T3 cross_asset active` — CASC ≥ 2/4

**Orange (预警/早期信号)**：
1. `front_event active` — VIX > 20 或 DGS2-IORB > 0
2. `rate_shock active` — DFII10 ≥ 2.00 (即使 DUR5 < 5)
3. `T2 liquidity partial` — EFFR-IORB ≥ -3bp 但 DUR5 < 3
4. `T2 credit_partial` — T2 fully active 但 T1 credit 未触发

### 2.3 系统性风险触发器

| 触发器 | 条件 | 指标 |
|--------|------|------|
| **T1 信用** | HY OAS ≥ 300bp | 信用条件恶化 |
| **T2 流动性** | EFFR-IORB ≥ -3bp AND DUR5 ≥ 3 | 资金管道承压 |
| **T3 跨资产** | CASC ≥ 2/4 (VIX>25 / MOVE>120 / HY OAS 20dΔ>20bp / FXY 5d>2.5%) | 跨资产共振 |

### 2.4 SYSTEMIC 判定

| 分类 | 条件 |
|------|------|
| **SYSTEMIC** | T1+T2+T3 全部触发 |
| **WATCH** | 至少一个 trigger 触发，但未达全触发 |
| **NON-SYSTEMIC** | 无 trigger 触发 |

### 2.5 双探针互锁 (VTS + RCV)

- **VTS (§0.8)**：VIX9D / VIX 期限结构，contango/backwardation 判断
- **RCV (§0.9)**：2Y/10Y/30Y 实际收益曲线形态 (elevated-front-tilt 等)
- **三态互锁**：双缺/仅VTS缺/仅RCV缺/双探针共振 → 缺任一侧都无法确认共振

---

## 三、版本历史 (Git + 管线快照)

### v3.5.1 (2026-06-17 → 现在)

| 日期 | commit | 内容 |
|------|--------|------|
| 06-21 | — | feat: `scripts/sync_historical_data.py` — series.json → 历史数据 CSV + fred_live 每日增量同步，接入 CI |
| 06-21 | — | feat: `scripts/append_sr3_daily.py` — sofr_sr3.csv 10 合约 → sr3_long/sr3_curve_features 每日追加，幂等 |
| 06-21 | — | feat: `scripts/validate_fred_pipeline.py` — 五路日期同步验收 (series.json/DGS10/HY OAS/panel/daily report)，CI post-check，FRED 链路断链自动报警 |  
| 06-21 | — | feat: `scripts/sr3_repair_watch.py` — SR3 只读监控，回答四问(impulse/decel/level_repair/classification)，输出 JSON+MD，不接任何系统 |  
| 06-21 | — | **封版 v3.5.1** — FRED/HY OAS 自动同步 + SR3 repair 只读监控 + mixed_repair 防误用提示 + 五路日期验收。系统边界锁定：Risk OS / dashboard / run_all.py 不接 SR3。 |
| 06-21 | — | verify: HY OAS master 接缝核查通过 — seed(Wayback)→fred_live 于 2023-06-19 无缝对齐(4.15→4.15), 2008 peak 21.82(2182bp)/2020 peak 10.87(1087bp) 双试金石一致，Wayback 回填段可信 |
| 06-21 | — | note: SSoT(event_state.json) R4/P25/H45 vs 显示层(daily_report) R3/P35/H35 — 待修#3 两套 red_count 合并后对齐 |
| 06-20 | `9f7392f` | fix: 2s10s 表格 stray `\n` → 曲线行恢复 + VTS tickers 补入 CI pipeline |
| 06-20 | `d781043` | fix: `fetch_mm_calendar` embed→ical URL 自动转换 + HTML 检测 fallback |
| 06-20 | `fdd8e6e` | build: 重建 Risk Dashboard HTML (06-20 数据) |
| 06-20 | `0c21bb2` | feat: 2s10s 曲线结构扩展至 risk_dashboard |
| 06-20 | `2808f90` | feat: 2s10s 曲线结构节 (2Y/10Y/30Y/Spread/Bear Flattening) |
| 06-19 | `362fd9a` | refactor: DGS2−IORB 利率路径标签 → 单一函数 |
| 06-19 | `c40c922` | v3.5: 06-19 日报 — nowcast=2.19%, US10Y Futu IEF 推算 |
| 06-18 | `3ade63d` | fix: VTS 缺失 — `^VIX`/`^VIX3M`/`^VIX9D` 注入 series.json |
| 06-18 | `9c1b73d` | fix: verdicts 缺键 + risk_dashboard_latest.md 自动同步 + §7 总纲 |
| 06-17 | `3653f5a` | v3.5.1: VTS 数据修复 + 三态互锁 + 缺数据可见原则归档 |
| 06-17 | `43adbe3` | fix: yfinance pandas 3.0 scalar + ABCD 用实际阈值 |
| 06-17 | `ccef424` | report: R4 防御 · ON RRP $0.7B 极低 · Yahoo stale 16d |

### v3.5 (2026-06-15 → 06-16)

| 日期 | commit | 内容 |
|------|--------|------|
| 06-16 | `f6c3056` | feat: MOVE_PROXY fallback (DGS2+DGS10 20d realized vol) |
| 06-16 | `201d384` | feat: Risk OS Orchestrator v2.0 — 三系统融合唯一裁决，消除 systemic_confirmed 误报 |
| 06-16 | `93542d1` | report: ABCD 2026-06-16 R4 防御 |
| 06-15 | `b2c84bc` | feat: Risk OS SSoT v1.0 — 状态机+看板v3 schema升级，GH Actions 切换 |
| 06-15 | `98879c0` | fix: T2流动性统一显示'已触发·部分压力' |
| 06-15 | `eb3769d` | feat: 实际利率卡片展示 Nowcast 方法、差值方向、数据质量备注 |

### 管线快照

| 版本 | 日期 | 说明 |
|------|------|------|
| **v1.2** | 06-20 21:20 | 新增 2s10s 曲线结构节 (2Y/10Y/30Y/Spread/Bear Flattening) |
| v1.1 | 06-10 19:47 | 审计修复版：Reserve 单位、HY OAS 箭头、字母碰撞、VTS 双比率等 7 项 |
| v1.0 | 06-10 | 初始归档：ABCD 四端 + 风险看板 + 流程图 v4 |

### 关键架构决策

- **2026-06-15**：Risk OS SSoT 确立 — `tools/risk_os_state_machine.py` 为唯一裁决层
- **2026-06-16**：Orchestrator v2.0 — 三系统融合，分离 Regime/Systemic，消除误报
- **2026-06-17**：缺数据可见原则 — 三态互锁 (确认/否定/无法判定)
- **2026-06-18**：§7 总纲落盘 — 「不确定」必须可见，不能沉默
- **2026-06-20**：2s10s 曲线结构上线，VTS tickers CI 补全
- **2026-06-21**：SR3 修复验证研究 + 只读监控上线 — `scripts/sr3_repair_watch.py` 输出 `sr3_repair_watch_latest.{json,md}`，四问实时追踪，双轨参考峰值（formal shock / recent 60d peak），research-only
- **2026-06-21**：历史数据自动同步 — `scripts/sync_historical_data.py` 每日从 series.json 增量同步到 历史数据/CSV + fred_live，幂等。`build_macro_research_panel.py` 接入 CI 每日自动重建面板。
- **2026-06-21**：FRED 管线验收 — `scripts/validate_fred_pipeline.py` 五路日期对齐检查，CI 提交前置后检查，任一落后 >1d 即报警。

---

## 四、当前状态 (2026-06-20 收盘)

### ABCD 四端快照

| 端 | 灯 | 关键指标 | DUR 确认 |
|----|-----|---------|---------|
| A 资金管道 | 🟠 | EFFR-IORB=-2bp | DUR5=5/5 ✅ |
| B 信用条件 | 🟢 | HY OAS=263bp ⚠️自满 | — |
| C 长端利率 | 🔴 | DFII10=2.23% | DUR5=5/5 ✅ |
| D 外汇扩散 | 🟢 | FXY 5d=-1.0% | — |

### 综合判定

| 项目 | 值 |
|------|-----|
| **Regime** | **R4 防御** |
| 仓位 | P=25% / H=45% / C=30% |
| 跨域信号 | 2 (red=1, orange=1) |
| 2s10s Spread | +29bp, Bear Flattening (Flat) |
| Real Yield Nowcast | 2.19% (官方 DFII10=2.23%) |
| ON RRP | $0.3B (极低) |
| VTS | N/A ⚠️缺数据 |
| RCV | elevated-front-tilt |
| 互锁 | vts_missing |
| SYSTEMIC | 未确认 (WATCH) |
| CASC | 0/4 |

### 第一层传导路径

```
C先红（贴现率压估值）→ A再紧（流动性缓冲变薄）→ B未坏（内部轮动）
→ 若B转坏+信用走阔 → 系统性 → 若D再动 → 全球联动
```

---

## 五、管线速查

### GH Actions (自动)

```
update-data.yml  (22:00 UTC weekdays)
  fetch_data.py → sync_historical_data.py → build_macro_research_panel.py
  → daily_report.py → risk_os_state_machine.py → validate_fred_pipeline.py → commit

build-pages.yml  (hourly + push)
  fetch_mm_calendar.py → build_site.py → risk_os_state_machine.py → commit
```

### 本地手动

```
# SR3 日常更新（手工更新 sofr_sr3.csv 后）
uv run python scripts/append_sr3_daily.py
uv run python scripts/sr3_repair_watch.py

# 同步历史数据（series.json → 历史数据/CSV + macro_research_panel）
uv run python scripts/sync_historical_data.py
uv run python scripts/build_macro_research_panel.py
```

### 本地一键运行

```powershell
cd D:\liquidity-dashboard\v3.5

# 只出报告（不抓数据）
uv run python -X utf8 daily_report.py --md

# 完整数据抓取+报告
uv run python run_daily.py

# 快照归档
copy to _pipeline_snapshots/v1.x/
```

### 输出路径

| 产物 | 位置 |
|------|------|
| 日报 MD | `report/daily_YYYY-MM-DD.md` |
| 风险看板 MD | `report/risk_dashboard_YYYY-MM-DD.md` |
| 风险看板 PNG | `report/risk_dashboard_YYYY-MM-DD.png` |
| 流程图 HTML | `daily_archive/YYYY-MM/risk_flowchart_YYYY-MM-DD.html` |
| SSoT 状态 JSON | `docs/risk/assets/event_state.json` |
| Dashboard | `docs/risk/index.html` |
| 数据文件 | `data/series.json` |

### 脚本职责

| 脚本 | 角色 | 大小 |
|------|------|------|
| `daily_report.py` | 核心引擎：ABCD 信号计算、regime 判定、触发条件评估，输出 MD+PNG+HTML | 126.5 KB |
| `fetch_data.py` | FRED + Yahoo + CoinGecko 实时抓取 → series.json | 20.2 KB |
| `fetch_yahoo_local.py` | 本地 Yahoo 数据 (FXY/HYG/SPY/GLD) → yahoo_series.json | 3.4 KB |
| `run_daily.py` | 编排器：Step 1→3 | 3.3 KB |
| `generate_risk_dashboard.py` | 四模块文字表格 + PNG 可视化 | 19.8 KB |
| `generate_risk_flowchart.py` | 前端风险→系统性风险演化流程图 HTML (v4) | 24.4 KB |
| `scripts/sync_historical_data.py` | series.json → 历史数据 CSV + fred_live 每日增量同步 | — |
| `scripts/build_macro_research_panel.py` | HY OAS + FRED 利率 → macro_research_panel.csv | — |
| `scripts/validate_fred_pipeline.py` | 五路日期同步验收 (post-check) | — |
| `scripts/append_sr3_daily.py` | sofr_sr3.csv 10 合约 → sr3_long/sr3_curve_features 追加 | — |
| `scripts/sr3_repair_watch.py` | SR3 修复只读监控 → JSON/MD (Research-Only) | — |
| `tools/risk_os_state_machine.py` | **SSoT 唯一裁决层** | — |

---

## 六、已知待修复

| # | 问题 | 状态 | 备注 |
|---|------|------|------|
| 1 | VTS/^VIX/^VIX3M/^VIX9D 数据仍缺失 | 🔧 已修，待生效 (6/23 周一) | CI ticker 已补，等下次 GH Actions |
| 2 | GLD/^MOVE/^TNX/GOLD_10Y_RATIO 同样缺 Yahoo 数据 | 同上 | — |
| 3 | daily_report.py 与 state_machine 独立定 regime | 📋 待合并 | 两套 red_count 定义，架构 §7-④ |
| 4 | VTS 阈值前端急性 (VIX9D/VIX > 1) 缺滞回带 | 📋 待触发 | 记忆 #53003036 |
| 5 | build-pages.yml step 4 已切 state_machine | ✅ 已修 | — |
| 6 | fetch_mm_calendar.py embed URL 自动转换 | ✅ 已修 | — |
| 7 | 2s10s 表格 stray `\n` 断裂 | ✅ 已修 | — |

---

## 七、架构原则 (防退化)

### AND-of-two lint
任何"信号A🔴 ∧ 信号B🔴 → 动作"结构，必须验证 A、B 不共享输入。共享则 AND 退化为一信号看两次。

### 缺数据三态原则
缺数据 ≠ 条件不满足。判定函数收到 N/A 输入时，必须显式输出缺数据状态，不能默默折叠为"未触发/calm/false"。

### 查表取不到 → 可见告警
字典取值用 `.get(key, f"[!] MISSING_KEY:{key}")` 而非 `.get(key, '')`，确保缺键时产物上出现醒目的错误信息。

### 禁止事项
- ❌ 其他系统不得输出 final_judgement、regime、systemic 等结论
- ❌ Dashboard 不得自行计算信号 — 只渲染 event_state.json
- ❌ GH Actions 不得直接部署未经状态机验证的 event_state.json
- ✅ 信号输入层只输出中间数据/表格
- ✅ 所有状态变更必须经过 risk_os_state_machine.py

---

## 八、关键文件索引

| 文件 | 用途 |
|------|------|
| `_risk_os_architecture.md` | 架构详细文档 |
| `_pipeline_snapshots/CHANGELOG.md` | 管线变更历史 |
| `_pipeline_snapshots/v1.2/` | 最新管线快照 |
| `report/daily_*.md` | 每日诊断简报 |
| `report/risk_dashboard_*.md` | 每日风险看板 |
| `daily_archive/` | 历史报告归档 |
| `docs/risk/index.html` | 网页 Dashboard |
| `docs/risk/assets/event_state.json` | SSoT 输出 |

---

## 九、macro_research_panel 使用口径

> **验收日期**：2026-06-21 | **脚本**：`scripts/build_macro_research_panel.py`
> **输出**：`data/macro_db/processed/macro_research_panel.csv`

### 数据定位

`macro_research_panel.csv` 是**独立宏观研究主表**，不是 HY OAS 全覆盖日历：

| 特性 | 说明 |
|------|------|
| 主轴 | FRED 利率全历史日历 (1962-01-02 ~ 今) |
| HY OAS | `BAMLH0A0HYM2_master_clean_for_backtest.csv` **左连接** |
| HY OAS 有效观测 | 仅 7,560 行 (32.1%)，其余为 NaN |
| 缺失策略 | **不 forward-fill、不 back-fill、不插值** |
| SVB gap | 2023-03-06 ~ 2023-04-20 标记 `credit_signal_status = unavailable` |

### 使用铁律

1. **做依赖 HY OAS 的回测时，必须过滤 `HY_OAS_available == True`**，或者把 `unavailable` 作为单独状态处理
2. **不要把 HY OAS 缺失当作「信用稳定」** — 缺数据 ≠ 低风险
3. **不要对 HY OAS 做任何填充** — 缺失就是缺失，必须反映在信号中

### HY_OAS_chg_5d / chg_20d 语义

**是 observation-based changes，不是 calendar-day changes，也不是 strictly-trading-day changes。**

```
HY_OAS_chg_5d: 当前有效 HY OAS 观测 vs 第 5 个前有效观测的差值
HY_OAS_chg_20d: 当前有效 HY OAS 观测 vs 第 20 个前有效观测的差值
```

**跨 gap 行为**：`_obs_diff()` 先 dropna 再 diff，自然跳过缺失段。例如 2023-04-21（gap 后第一个有效值=4.46）：
- `chg_5d = 0.25` → 4.46 vs 2023-02-27 的值 4.21（跳过 gap 内 46 天）
- `chg_20d = 0.47` → 4.46 vs 约 20 obs 前的值 3.99

**不适用场景**：需要解释为「过去一周/过去一月信用利差变化」时，不能用 chg_5d/chg_20d，必须用 calendar-day diff 或另一个衍生列。

### 数据源声明

| 列 | 来源 | 格式 |
|----|------|------|
| BAMLH0A0HYM2 | `BAMLH0A0HYM2_master_clean_for_backtest.csv` | 仅交易日，无填充 |
| DGS10, DFII10, T10YIE, DGS2, EFFR, DFEDTARU | `data/历史数据/*.csv` | FRED `observation_date` 日历 |
| HY_OAS_chg_*/DGS10_chg_*/… | 本脚本计算 | observation-based diff |
| real_yield_nowcast | DGS10 - T10YIE | — |
| real_yield_basis_diff | real_yield_nowcast - DFII10 | — |
| curve_2s10s | DGS10 - DGS2 | — |
| credit_signal_status | available / unavailable / (空) | SVB gap = unavailable |

### 不接入项

- ❌ 不接 Risk OS
- ❌ 不改 dashboard
- ❌ 不改 run_all.py

### 下一步扩展点

✅ **SR3 修复验证已完成** (2026-06-21)。成果：
- `data/macro_backtest/research/sr3_repair_validation.{csv,json,md}` — 回测数据
- `docs/research/sr3_repair_decision_framework.md` — 四阶段决策框架 (research-only)

追加列已完成：
```
sr3_repair_event
credit_state
real_yield_state
repair_type = benign / malign / mixed / unavailable
```

---

## 十、更新规则

1. **每次封版**：在第三节追加版本条目
2. **每日运行后**：更新第四节当前状态
3. **修复完成后**：第六节对应条目标 ✅ 并注日期
4. **架构变更**：第二节对应节更新
5. **新问题发现**：第六节追加

---

*封版日期: 2026-06-20 22:37 | 最后更新: 2026-06-21 (SR3 修复验证) | 下次运行窗口: 周一 06-23 | v3.5 / v3.5.1*
