# 分子端证伪监测 · 财报/业绩说明会存档

**用途**：按 AI 传导链位置归档各公司财报 transcript 及"分子证伪"快照，追踪分子端走强/走弱。

## 传导链结构

```
上游（最晚露馅）      → 中游（swing link）    → 下游（最先冒烟）
芯片/算力               超大厂/云              软件/应用
NVDA, AMD, INTC        MSFT, GOOGL, AMZN, META  CRM, SNOW, DDOG, MDB...

边缘/交叉（不在核心链但相关）
AAPL, TSLA ...         → `edge/`
```

| 位置 | 关键盯什么 | 目录 |
|------|-----------|------|
| **上游** | 需求持久性、backlog/订单、供给是否仍紧 | `upstream/` |
| **中游** | capex 指引方向 — swing link，最关键 | `midstream/` |
| **下游** | 变现证据 NRR、billings、AI 归因收入、ROI | `downstream/` |
| **边缘** | 与核心链的交叉面（供给竞争/平行验证） | `edge/` |

## 分析框架（每条 transcript 统一用）

1. **硬信号**：收入/指引/backlog/ROI，每条附原文出处
2. **画饼隔离**：TAM/多年愿景/GDP-attach，不混入信号
3. **定性结论**：本季走强/持平/冒烟，一句话依据
4. **遗漏标注**：这份 transcript 给不了什么

## 使用方式

- 单家公司 transcript → 在对应子目录创建 `{ticker}_{quarter}.md`
- 跨链合力判断 → 对比同季上游/中游/下游读数，找背离
- 和温度计对一遍 → IGV vs SOX（下游 vs 上游）相对强弱

## 当前覆盖率

| 位置 | 已归档 | 最近季度 |
|------|--------|---------|
| 上游 | NVDA | Q1 FY2027 (2026-05-20) |
| 中游 | MSFT, GOOGL, **AMZN**, **META** | Q3 FY2026 / Q1 CY2026 / Q1 CY2026 / Q1 CY2026 |
| 下游 | CRM, **DDOG**, **NOW**, **ADBE**, **PLTR**, **SNOW** | Q1 FY2027 / Q1 CY2026 / Q1 CY2026 / Q1 FY2026 / Q1 CY2026 / Q1 FY2027 |
| 边缘 | AAPL, TSLA | Q2 FY2026 / Q1 CY2026 |
| 未覆盖 | AMD, MDB | — |

### 最近跨链合力

📊 **[Q1 CY2026 跨链合力](./Q1_CY2026_跨链合力.md)** — 上游走强 + 中游四家全票 capex 加速 (>$600B total) + 下游 5 家多线加速 → 传导链全环走强，史上最强合力
