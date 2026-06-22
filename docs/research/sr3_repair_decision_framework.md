# SR3 Repair Decision Framework

## 钝化不是买点：从鹰派冲击到良性修复的三阶段决策树

> **状态**: Research-Only  
> **生成日期**: 2026-06-21  
> **数据来源**: `data/macro_backtest/research/sr3_repair_validation.{csv,json,md}`  
> **验证范围**: 2018-05-07 ~ 2026-06-17 (2045 交易日, 84 合约, 15 鹰派冲击事件)

---

## 核心结论（一句话）

**SR3 deceleration 只能解除"继续追空"的必要；SR3 level repair 才允许正式买入；benign repair 才允许加仓趋势。**

---

## 一、回测核心发现

### 1.1 钝化 ≠ 修复

| 指标 | 值 |
|------|-----|
| 鹰派冲击事件总数 | 15 |
| 检测到钝化 (deceleration) | 15 (100%) |
| 60d 修复命中率 | 3 / 15 = **20.0%** |
| 120d 修复命中率 | 4 / 15 = **26.7%** |
| 250d 修复命中率 | 7 / 15 = **46.7%** |
| 任意窗口修复 | 7 / 15 = **46.7%** |

**结论**: SR3 钝化只是说明冲击速度慢下来了。100% 的事件都出现钝化，但多数不修复。钝化是必要非充分条件。

### 1.2 加息周期是墓地

2022-2023 激进加息周期内 **10 个事件全部是 decel_no_repair**（事件 ID 6-15）：

| ID | Shock Date | Height bp | 60d Repair | Type |
|----|-----------|-----------|------------|------|
| 6 | 2022-03-14 | 47.0 | ✗ | decel_no_repair |
| 7 | 2022-06-21 | 33.25 | ✓ | benign_repair |
| 8 | 2022-11-03 | 66.0 | ✗ | decel_no_repair |
| 9 | 2022-12-02 | 40.5 | ✗ | decel_no_repair |
| 10 | 2023-01-31 | 24.75 | ✗ | decel_no_repair |
| 11 | 2023-03-08 | 22.0 | ✗ | decel_no_repair |
| 12 | 2023-05-31 | 15.0 | ✗ | decel_no_repair |
| 13 | 2023-07-11 | 9.75 | ✗ | decel_no_repair |
| 14 | 2023-08-11 | 9.75 | ✗ | decel_no_repair |
| 15 | 2023-09-11 | 8.5 | ✗ | decel_no_repair |

事件 7 (2022-06-21) 是唯一例外——mid-2022 短暂喘息修复，随后被更大加息打回。**在真正加息周期里，市场会一边喘息，一边继续把终端利率往上抬。**

---

## 二、三状态（四阶段）决策树

### State 1: SR3 Hawkish Impulse / 继续上修

**定义**: 沃什鹰派冲击发生后，SR3 仍在创新高，前端合约继续上修。

| 动作 | 说明 |
|------|------|
| 禁止抄底 AI 硬件链 | SR3 仍在加压，分母尚未稳定 |
| 维持防御仓位 | 按 Risk OS regime 执行 |
| 只观察 | 监控信用、real yield、SR3 速度 |

### State 2: SR3 Deceleration / 钝化

**定义**: SR3 不再上修，冲击速度下降。5d sum ≤ 4bp 或 1d change ≤ 3bp，持续 ≥ 2 天。

| 动作 | 说明 |
|------|------|
| 不再追空 | 鹰派冲击 price over 初步信号 |
| 允许观察或极小仓试探 | 仅限于信用不扩的前提下 |
| **不得作为正式买入信号** | 历史上 100% 钝化，80% 不修复 |
| **不得触发仓位上调** | 钝化是刹车灯，不是绿灯 |

**关键区分**: 钝化只回答了"该不该继续跑"，没回答"该不该进场"。

### State 3: SR3 Level Repair / 明确修复

**定义**: 峰值合约（如 SR3Z6 / SR3H7）较事件高点回落 10-15bp+，并持续 2-3 个交易日。

**必要条件**:
- SR3 peak contract 确认回落
- HY OAS 不扩
- IG OAS 不扩
- real yield 不再创新高

| 动作 | 说明 |
|------|------|
| 允许正式低吸 AI 硬件链 | 沃什鹰派 price over 得到初步验证 |
| 仓位可上调 | 从观察/小探升级为正式买入 |

### State 4: Benign Repair / 良性修复

**定义**: SR3 持续修复 + 信用不扩 + real yield 下修 + 通胀就业指向软着陆。

**必要条件**:
- SR3 继续修复
- HY OAS 不扩
- IG OAS 不扩
- real yield 明确下修
- BEI 稳定（非通缩恐慌）
- 就业温和降温
- AI 硬件链分子兑现（业绩/订单确认）

| 动作 | 说明 |
|------|------|
| 允许从交易仓升级为趋势仓 | 软着陆式分母修复 + AI 分子兑现 |
| 这是最舒服的硬件链环境 | |

---

## 三、修复性质分类

| 类型 | 定义 | 出现次数 | 可执行动作 |
|------|------|---------|-----------|
| **benign_repair** | SR3 修复 + HY OAS 不扩 + real yield 下修 | 2 | 允许加仓趋势 |
| **malign_repair** | SR3 修复 + HY OAS 扩 / 信用压力上升 | 0 | 观察，不追 |
| **mixed_repair** | SR3 修复 + 信用稳定，但 real yield 未改善 | 1 | 可小仓，不趋势 |
| **unknown (credit unavailable)** | HY_OAS_available = false | 0 | 不得归入 benign |
| **decel_no_repair** | 钝化但未修复 | 12 | 不得加仓 |

---

## 四、AI 硬件链执行规则

| 条件组合 | 动作 |
|----------|------|
| 信用不扩 + SR3 钝化 | 只允许观察 / 极小仓试探 |
| 信用不扩 + SR3 level repair + real yield 不再创新高 | 允许正式买入 |
| 信用不扩 + SR3 benign repair + 分子兑现 | 允许加仓趋势 |
| SR3 钝化但不修复 | **不得加仓**，防止落入 2022-2023 式加息周期墓地 |

---

## 五、与朴素框架的对比

| 朴素版本（已弃用） | 修正版本（当前） |
|-------------------|-----------------|
| SR3 不再上修 → 买 | SR3 钝化 → 观察/小探 |
| （无中间档） | SR3 level repair → 正式买 |
| （无中间档） | SR3 benign repair → 加仓趋势 |
| 两态（上修/不上修） | 四态（仍在冲/钝化/修复/良性修复） |

**修正原因**: 2022-2023 反例集证明——在真正的加息周期里，钝化是常态，修复是例外。如果把钝化当买点，10 次里你会 10 次被套。

---

## 六、禁止事项

- ❌ 不得把 SR3 deceleration 单独作为买入信号 — 钝化是刹车灯，不是绿灯
- ❌ 不得在 HY_OAS_available = false 时判断信用稳定
- ❌ 不得 forward-fill / back-fill / interpolate HY OAS
- ❌ 不得修改 Risk OS (`tools/risk_os_state_machine.py`)
- ❌ 不得修改 dashboard (`docs/risk/`)
- ❌ 不得修改 `run_all.py`、`daily_report.py` 仓位逻辑
- ❌ 不得改变当前仓位系统输出
- ❌ SR3 钝化不得触发仓位上调

---

## 七、回测参数

| 参数 | 值 |
|------|-----|
| shock_5d_min_bp | 4.0 bp |
| shock_1d_min_bp | 3.0 bp |
| peak_lookback_days | 5 天 |
| decel_abs_bp_threshold | 1.5 bp |
| decel_min_days | 2 天 |
| repair_min_bp | 5.0 bp |
| repair_min_ratio | 0.3 |
| shock_min_height_bp | 5.0 bp |
| event_min_gap_days | 20 天 |
| repair_max_days (short) | 60 天 |
| repair_max_days (mid) | 120 天 |
| repair_max_days (long) | 250 天 |

---

## 八、数据文件

| 文件 | 路径 |
|------|------|
| 验证 CSV | `data/macro_backtest/research/sr3_repair_validation.csv` |
| 验证 JSON | `data/macro_backtest/research/sr3_repair_validation.json` |
| 验证报告 | `data/macro_backtest/research/sr3_repair_validation.md` |
| 本框架 | `docs/research/sr3_repair_decision_framework.md` |

---

## 九、状态声明

- **SR3 暂不进入正式仓位裁决系统**
- 本框架为 **Research-Only**
- 不接入 Risk OS / dashboard / run_all.py
- 不改变任何仓位、regime、credit trigger 或 AI 抄底逻辑
- 主力监控参数：SR3 peak contract 回落幅度、HY OAS 方向、real yield 方向、宏观周期定性

---

*Research-Only — 2026-06-21 — SR3 修复验证 v1.0*
