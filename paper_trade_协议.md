# v3.5 Paper Trade 30 天协议

> **启动**: 2026-05-27 | **结束**: 2026-06-26 | **周期**: 30 天（~21 交易日）
> **框架**: ABCDS v3.5（两轨制：轨1 ABS/DUR 生效，轨2 ROLL 待数据层）
> **日更脚本**: `liquidity-dashboard/scripts/daily_report.py` → `liquidity-dashboard/report/daily_*.md`

---

## 1. Paper Trade 目的

v3.4-beta 框架条款已冻结，task1–5 证伪审计完成。Paper trade 的目的是 **前向 out-of-sample 验证**：
- 框架信号在实际市场条件下是否稳定
- HYG drawdown warning 重定位（非 directional sell）的实际表现
- 但不真金白银交易——只记录信号、假设仓位、事后对照

---

## 2. Paper Trade 中几件事提醒自己

### 2.1 HYG < -1.5% 触发率预期
- 历史触发率 ~12%。一个月 ~21 交易日，期望触发 2-3 次
- 实际触发 0 次 → 正常
- 触发 5+ 次 → 环境进入 tail-risk 集中期，值得记录

### 2.2 触发 ≠ 减仓
- v3.5 重新定位为 drawdown warning
- 触发意义 = "接下来 20d >5% DD 频率 ~3x baseline"
- **不是** "SPY 接下来要跌"
- Paper trade 假设仓位时用这个新口径

### 2.3 5Y5Y 情绪管理
- 5Y5Y 当前在 2.47%，会持续 >2.45%
- F1=0.13 已证伪 narrative-only，但视觉红字"长期通胀锚"仍有情绪压力
- 检验"数据 > 叙事"

### 2.4 Curve Regime Steep-Steepening
- 进入时记一笔
- 即使不真加仓，记录"假设此时加仓 60d 后表现如何"
- 1 个月 paper trade 不够验证 60d window，但能积累 entry 时刻样本

---

## 3. 每日记录模板

```
日期: 2026-05-XX
Regime: R? 
ABC 灯: A=🟢/🟡/🟠/🔴 B=... C=... D=...
跨域信号数: N
HYG 5d Δ: -X.X%  [触发/未触发 drawdown warning]
仓位假设: Primary=XX% Hedge=XX% Cash=XX%

今日备注:
- 信号变化? 
- 5Y5Y 位置? 
- Curve regime?
- 任何"假设..."类记录
```

---

## 4. Claude 的自提醒（继承）

1. 回来时先 conversation_search 拉 paper trade 记录上下文，再喂任何意见
2. 别预设 Option A/B/C 哪个对，等用户报告实战观察
3. 如果用户报告"什么都没触发"，这是 important null，不要因此推动 v3.6 "做点什么"
4. 如果用户报告"触发了但 SPY 涨了"，正是 drawdown warning ≠ directional 的预期表现，不是信号失败

---

## 5. CodeBuddy 协作纪律（存档）

有效协作 = 精确 cell-level prompt + 完成清单（不是"已完成"）+ 强制约束（"不要扩展"、"6 项改完即停"）
Task 4 vs 4.5 的差距本质上就这一个变量。

---

*协议版本: v1.0 | 创建: 2026-05-29（回溯记录） | 原文来源: Claude 对话 2026-05-27*
