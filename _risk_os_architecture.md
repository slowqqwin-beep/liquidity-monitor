# Risk OS Architecture v1.0 — Single Source of Truth

> **生效日期**: 2026-06-15  
> **核心原则**: `tools/risk_os_state_machine.py` 是**唯一状态裁决层**。  
> 所有其他系统（generate_risk_dashboard、scripts/daily_report.py、Fed reaction、ABCD）降级为**信号输入层**，不得输出最终结论。

---

## 架构分层

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
└────────────────┘    │ extract_risk_     │
                       │   events.py       │
                       │ → 已退役(文本解析) │
                       │ Fed reaction      │
                       │ → Fed dashboard   │
                       └───────────────────┘
```

---

## 1. 状态机规则

### R1-R4 Regime

| Regime | 条件 | 持仓 (P/H/C) | 含义 |
|--------|------|-------------|------|
| **R1 正常** | red=0, orange=0 | 75/5/20 | 无显著压力 |
| **R2 观察** | red=0, orange≥1 | 55/25/20 | 预警信号出现，持仓微调 |
| **R3 警惕** | red≥1 或 (orange≥1 且 前端active) | 35/35/30 | 信号确认，大幅降风险 |
| **R4 风险释放** | red≥3 | 30/40/30 | 多域压力共振，激进防御 |

### Red vs Orange 计数

**Red (已确认系统级信号)**：
1. `real_yield_pressure` — DFII10 ≥ 2.00% DUR5 ≥ 5
2. `T2 liquidity active` — EFFR-IORB ≥ -3bp DUR5 ≥ 3
3. `T1 credit active` — HY OAS ≥ 300bp
4. `T3 cross_asset active` — CASC ≥ 2/4

**Orange (预警/早期信号)**：
1. `front_event active` — VIX > 20 或 DGS2-IORB > 0
2. `rate_shock active` — DFII10 ≥ 2.00 (even if DUR5 < 5)
3. `T2 liquidity partial` — EFFR-IORB ≥ -3bp but DUR5 < 3
4. `T2 credit_partial` — T2 fully active but T1 credit not triggered

### SYSTEMIC 判定

| 分类 | 条件 |
|------|------|
| **SYSTEMIC** | T1+T2+T3 **全部触发** |
| **WATCH** | 至少一个 trigger 触发，但未达全触发 |
| **NON-SYSTEMIC** | 无 trigger 触发 |

---

## 2. 信号计算模块

### 2.1 DFII10 Nowcast (`compute_nowcast`)
```
Nowcast = DGS10 − T10YIE
gap_bp = (Nowcast − DFII10) × 100
```
- 来源: FRED DGS10 + T10YIE
- 质量说明: "官方DFII10滞后修正，Nowcast更实时"

### 2.2 近端事件风险 (`compute_front_event`)
- DGS2 − IORB > 0 → rate_event
- VIX > 20 → vol_event
- intensity: DGS2−IORB ≥ 20bp → red, else orange

### 2.3 实际利率/估值挤压 (`compute_rate_shock`)
- DFII10 ≥ 2.00% → active
- DUR5 ≥ 5 → confirmed
- 标签: ≥2.00→"高压·估值压缩", ≥1.20→"偏紧·接近阈值"

### 2.4 第一层传导 (`compute_transmission`)
- 使用 EFFR_IORB 衍生序列查 DUR5 (≥ -3bp)
- 传导路径: C→A→B→D

### 2.5 系统性风险触发器 (`compute_triggers`)
- **T1 (信用)**: HY OAS ≥ 300bp
- **T2 (流动性)**: EFFR-IORB ≥ -3bp AND DUR5 ≥ 3
- **T3 (跨资产)**: CASC ≥ 2/4
  - VIX > 25
  - MOVE > 120
  - HY OAS 20dΔ > 20bp
  - FXY 5d return > 2.5%

---

## 3. 数据流

### 输入
```
data/series.json  ←  scripts/fetch_data.py (GH Actions, 22:00 UTC weekdays)
```
包含 36 个序列：FRED(24)、Yahoo(3)、CoinGecko(2)、Stooq(1)、衍生(6)

### 输出
```
docs/risk/assets/event_state.json  ←  tools/risk_os_state_machine.py
```
**这是唯一权威输出。** Dashboard 直接读取此文件。

### Schema
```json
{
  "date": "YYYY-MM-DD",
  "source": "Risk OS State Machine v1.0 — Single Source of Truth",
  "regime": "R3 警惕",
  "regime_key": "R3",
  "systemic_classification": "WATCH",
  "positions": {"primary": "35%", "hedge": "35%", "cash": "30%"},
  "cross_domain_signals": 3,
  "red_count": 2,
  "front_event_risk": { "active": true, "type": "rate_event", "intensity": "red", ... },
  "rate_shock": { "active": true, "dfii10_official": 2.16, "dfii10_nowcast": 2.14, ... },
  "first_layer_transmission": { "active": true, "main_path": "C先红 → A偏紧 → B未坏 → D未动", ... },
  "systemic_triggers": {
    "credit": { "active": false, ... },
    "liquidity": { "active": true, "partial": false, "credit_partial": true, ... },
    "cross_asset": { "active": false, "casc_count": 0 }
  },
  "stage_assessment": {
    "current_stage": "...",
    "not_yet_stage": "系统性风险",
    "final_judgement": "...",
    "systemic_upgrade_conditions": { ... },
    "next_watch": [ ... ]
  },
  "signal_conflicts": []
}
```

---

## 4. GH Actions 流水线

### 4.1 `update-data.yml` (22:00 UTC weekdays)
```
fetch_data.py → daily_report.py → risk_os_state_machine.py → commit
```
**关键变更**: 第 3 步从 `extract_risk_events.py` 换成 `risk_os_state_machine.py`。

### 4.2 `build-pages.yml` (hourly + push)
```
fetch_mm_calendar.py → update_event_window.py → build_site.py → risk_os_state_machine.py → commit
```
**关键变更**: 第 4 步从 `extract_risk_events.py` 换成 `risk_os_state_machine.py`。

---

## 5. 信号冲突检测

当以下情况发生时标记冲突：
1. 近端事件活跃 (front_event active) 但 regime = R1
2. (预留) regime 与 systemic_classification 不一致

冲突不会阻止输出，但会在 `signal_conflicts` 数组中标出供 review。

---

## 6. 禁止事项

- ❌ 其他系统不得输出 `final_judgement`、`regime`、`systemic` 等结论
- ❌ Dashboard 不得自行计算信号 — 只渲染 `event_state.json`
- ❌ GH Actions 不得直接部署未经状态机验证的 event_state.json
- ✅ 信号输入层只输出中间数据/表格
- ✅ 所有状态变更必须经过 `risk_os_state_machine.py`

---

## 8. SR3 修复决策框架 (Research-Only)

> **引用文档**: `docs/research/sr3_repair_decision_framework.md`  
> **状态**: Research-Only — **不接入 Risk OS，不改变仓位裁决**

### 核心结论

**SR3 deceleration 只能解除"继续追空"的必要；SR3 level repair 才允许正式买入；benign repair 才允许加仓趋势。**

### 关键数据

- 15 个鹰派冲击事件，100% 出现钝化，但 60d 修复率仅 20%
- 2022-2023 加息周期内 10 个事件全部 decel_no_repair
- **钝化是刹车灯，不是绿灯**

### 集成状态

| 项目 | 状态 |
|------|------|
| 接入 Risk OS | ❌ 不接入 |
| 修改 dashboard | ❌ 不修改 |
| 修改 run_all.py | ❌ 不修改 |
| 改变仓位系统 | ❌ 不改变 |
| SR3 deceleration 作为买入信号 | ❌ 禁用 |
| 用于 AI 硬件链观察/小探参考 | ✅ 仅参考 |

### 禁止事项

- ❌ SR3 钝化不得作为正式买入信号
- ❌ SR3 钝化不得触发仓位上调
- ❌ 不得在 HY_OAS_available = false 时判断信用稳定
- ❌ 不得 forward-fill / back-fill / interpolate HY OAS

详细决策树和四阶段框架见 `docs/research/sr3_repair_decision_framework.md`。

---

## 7. 维护清单

- [ ] 新增 FRED 序列 → 更新 `FRED_SERIES` + 状态机 `_load_data()` 引用
- [ ] 修改阈值 → 更新状态机对应 `compute_*()` 函数
- [ ] 修改 R1-R4 规则 → 更新 `run_state_machine()`
- [ ] 新增输出字段 → 更新 `assemble()` + `dashboard.js`
- [ ] 数据异常 → 检查 `data/series.json` 中对应序列的 len

- [x] **④ 已发生的裁决冲突：MD 与 SSoT 对 regime/position 独立判定，今日实测 R4 vs R3、P 差 5pp、H 差 10pp。** 架构文档已定 SSoT=状态机。根因：`daily_report.py` 的 `compute_position()` 和 `risk_os_state_machine.py` 的 `run_orchestrator()` 是两套独立 red_count 定义（ABCD 域综合 vs 原始触发器二进制和），对"流动性压力"的颗粒度不同导致 regime 分歧。**修复分两阶段：**
  - **已做（v0.5.59）**: (a) 管线补入 `risk_os_state_machine.py` 每天自动刷新 SSoT event_state；(b) 加交叉验证横幅 — 每天比对两个 event_state 的 regime/red_count/systemic_confirmed/positions，不一致打印 ⚠️ 到日报末；(c) flowchart PNG + MD 报告头部标注"显示用·权威裁决以 Dashboard 为准"。
  - **待做**: 将 `daily_report.py` 的 regime/position 判定改为读 `risk_os_state_machine` 输出（SSoT 单向流），彻底消除第二裁决器。涉及：`compute_position()` 的 `red_count` 语义对齐、ABCD 域 `cross_count` 与状态机 `orange_count` 映射。

- [ ] **总纲：「不确定」必须可见，不能沉默** → 任何输入缺失/状态未知的情形，默认行为必须是**可见的不确定**（告警、⚪灯、N/A、abort），绝不能是**沉默的确定**（停在 true、折叠成 calm、返回空串、当作未触发）。以下三条是同一原则在不同切面的投影——manifest 横幅停滞、门控 None、VTS 折叠、verdict 缺键四次实锤：

    - [ ] **① 门控/判定依赖的输入必须在判定之前完成解析** → 任何 `if cross_confirm >= N` 式的门控，其输入变量必须在当前函数中先于该行赋值。含解析逻辑的函数需有正向（该触发时触发）+ 负向（该拦时拦住）+ 边界（恰好等于阈值-1）三层回放用例。`tests/test_systemic_gate.py` 含顺序不变性静态断言作为保护。**教训：v3.5.1 中 CASC 解析初版在门控之后执行，`cross_confirm` 读到 None 导致门控形同虚设——负向测试无法暴露（因为 False 的结果碰巧正确），只有正向用例才能发现。**

    - [ ] **② 判定依赖的输入缺失时，必须区分"未触发"和"无法判定"（三态原则）** → 缺数据 ≠ 条件不满足。判定函数收到 N/A 输入时，不能默默折叠为"未触发/calm/false"，必须显式输出缺数据状态（`vts_missing`、`N/A`、`⚪`），并在上游显示层标注 `⚠️缺数据`。**两个实例：(1) CASC 门控 — `cross_confirm=None` 时形同虚设，`systemic` 碰巧 false 的假阴性；(2) VTS/RCV 互锁 — `compute_vts_rcv_interlock()` 做成三态分流（双缺/仅VTS缺/仅RCV缺），缺任一侧都不能声称"双探针共振"也不能声称"无共振"，只能说"无法确认"。补一个分支时对称检查对侧是否也有同样盲点。**

    - [ ] **③ 查表取不到时，返回可见告警，不返回空/默认安全值** → 任何字典/映射取值（`verdicts[state]`、`label_map[key]`、`.get(key)` 无 fallback），如果 state 全集已知且不大，用 `.get(state, f"[!] MISSING_KEY:{state}")` 替代 `[state]` 或 `.get(state,'')`。fallback 必须是刺眼告警而非空串，这样下次缺键时产物上是一行醒目的错误信息而非又一次空白/假平静。**配测试：遍历 state 枚举全集，断言每个都能取到非空值。`tests/test_systemic_gate.py` 含 `test_interlock_verdict_coverage` + `test_verdict_keys_match_interlock_states` 两个不变性守卫（枚举覆盖性）。** **两次教训：(1) event_state 布尔停在 true 未更新 → 掩蔽了状态演化；(2) verdicts 字典缺 `divergent`/`vts_missing` 键 → PNG verdict 空白，MD 有结论但 PNG 丢了。同一家族——缺键返回空而非告警，问题在产物层被沉默。**
