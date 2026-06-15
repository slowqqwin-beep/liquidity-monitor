# task1–5 证伪审计结论

> **审计范围**: task1–5 系列脚本 | **完成日期**: ~2026-05-27
> **用途**: 解释为什么 v3.5 走 ABS 绝对阈值 + DUR5 确认 + 熔断路线，而不依赖 regime 分类的 mechanistic mapping

---

## Task 1 — 2s10s 6 类 Regime

- 分类可行，但段长偏短（中位 <5 天 → **noisy**）
- 不适合独立作为仓位信号
- Steep-Steepening 罕见但有意义（exit 后 60d SPY 正向）

---

## Task 2 — Credit Dispersion

- **路径 A**（HYG 代理，11 年）可用，但与路径 B（BAML 真值，仅 3 年）一致性中等
- **BAML 真值只有 ~3 年** → sample-limited，不能独立做 high-confidence signal

---

## Task 3 — Reserve Scarcity

- 三维分类（Abundant / Ample / Tightening）可行
- Ample 占比 >60% → **主导分布，区分度低**
- Tightening 占比 <5% → **样本不足**

---

## Task 5 — Forward Returns 全面评估

- 大部分 regime entry/exit 的 forward return **无统计显著性**（N<20 或 p>0.10）
- 只有少数组合有显著信号，且需强调"样本小、前后半期一致性存疑"

### Task 5.5 — v3.5 HYG <-1.5% Drawdown 信号

- 以 2020-11 为分界，**后半段退化**
- 结论：信号曾经的 drawdown warning power **减弱**，可用但 confidence 降低
- → v3.5 重定位为 drawdown warning（非 directional sell）

### Task 5 verify — 四项审计

- 5.1: dispersion:Widening 36 个 entry 日 **集中在 ≤3 个 episode**（SVB / Yen Carry / 关税），不是独立事件
- 5.4: v3.5 核心信号（HY OAS 20d Δ > +20bp）在 2020-11 前后**方向准确率退化**

---

## 对 v3.5 框架的影响

| 发现 | 框架处置 |
|------|---------|
| Regime 分类统计不 robust | 不依赖 regime 类别的 mechanistic mapping |
| Forward return 无显著性 | 仓位信号走 ABS 绝对阈值 + DUR5 确认 |
| Credit dispersion 样本不足 | 不独立使用，作为辅助确认 |
| HYG drawdown 信号退化 | 重定位为 drawdown warning（非 sell signal） |

**v3.5 的保守路线是其设计特征，不是缺陷**——恰因证伪了太多"看似可用"的统计关系，才转向了物理约束 + 持续确认 + 熔断的底线策略。

---

## 脚本清单

| 文件 | 功能 |
|------|------|
| `task1_regime_2s10s.py` | 2s10s 6 类 Regime 分类 |
| `task2_regime_credit.py` | Credit Dispersion（HYG vs BAML） |
| `task3_regime_reserve.py` | Reserve Scarcity 三维分类 |
| `task5_forward_returns.py` | Forward Returns 全面评估 |
| `task55_drawdown.py` | HYG drawdown 信号退化分析 |
| `task5_verify.py` | 四项审计（dispersion / threshold / signal / direction） |

---

*文档版本: v1.0 | 创建: 2026-05-29*
