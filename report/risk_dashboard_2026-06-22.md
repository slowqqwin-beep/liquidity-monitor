# 🛡️ 前端风险 → 系统性风险 演化看板

> **2026-06-22** | Regime: **R4 防御** | P=25% / H=45% / C=30% | 跨域信号=2 | 🔴=1

> ⚠️ 显示用 · 权威裁决以 Risk Dashboard (risk_os_state_machine SSoT) 为准 — 若与 dashboard.js 显示的 regime/仓位不一致，以 dashboard 为准

---
## ① 近端事件风险

| 维度 | 信号 |
|------|------|
| 事件窗 | VIX9D/VIX=0.849 前端平静 | VIX=16.4 5dΔ-3.0 |
| 风险性质 | 单资产技术性·CASC守卫 |
| 市场信号 | 无跨资产确认 |
| 利率路径 | DGS2−IORB=55.0bp · 5dΔ+7.0bp ▲ · [降息被price out / 加息风险 · 代理非OIS] |

---
## ② 第一层传导

| 端 | 指标 | 当前值 | 灯 | DUR5 | 状态 |
|----|------|--------|------|------|------|
| C 长端利率 | DFII10 | 2.23% | 🔴 | 5/5 ✅ | 贴现率压力 |
| C Nowcast | Real Yield Nowcast | 2.20% | 🔴 | — | 官方DFII10滞后修正・实际利率高压 方向：小幅回落 |
| A 资金管道 | EFFR-IORB | -2.0bp | 🟠 | 5/5 ✅ | 资金管道偏紧 |
| A 拆借 | SOFR-IORB | -2.0bp | 🟠 | — | 拆借市场 |
| — | 2Y | 4.20% | — | — | — |
| — | 10Y | 4.49% | — | — | — |
| — | 30Y | 4.93% | — | — | — |
| — | **2s10s Spread** | **+29bp** | — | — | Δ5d -6bp · Bear Flattening(Flat) |
| — | 5s30s Spread | +66bp | — | — | — |

---
## ③ 系统性风险触发器

| 触发器 | 条件 | 当前状态 |
|--------|------|---------|
| **T1 信用(B端)** | HY/IG OAS走阔脱离自满 | 🟢 未触发 (HY/IG ⚠️自满) |
| **T2 流动性(A端)** | EFFR-IORB 🟠/🔴+DUR5≥5 | 🟠 已触发·部分压力 (EFFR-IORB=-2.0bp DUR5=5/5) |
| **T3 跨资产/跨境** | CASC≥2+VTS+RCV互锁 | 🟢 未触发 (CASC0/4·VTS=contango·互锁=divergent) |

---
## ④ 系统性风险阶段与最终判断

| 项目 | 状态 |
|------|------|
| 当前阶段 | 🟡 **单资产技术性·无双探针共振** |
| Regime | **R4 防御**(R4) · 跨域=2 · 🔴=1 |
| 仓位 | P=25% / H=45% / C=30% |
| VTS | contango · 前端=前端平静 |
| RCV | elevated-front-tilt · sev=elevated · tilt=front · 2y/30y=2.096 z=3.5 |
| 互锁 | divergent — RCV热·VTS平→利率单资产技术性 |
| C端 | 有序重定价·估值压缩 · 双探针:divergent |
| C Nowcast | 官方🔴红灯·Nowcast边际回落 → 估值压力边际缓和 |

> **最终判断**：VTS热·RCV平→单资产技术性。无双探针共振，不触发额外系统性仓位动作。

---
*ABCD v3.5.1 风险演化看板 | 2026-06-22 | FRED+Yahoo*