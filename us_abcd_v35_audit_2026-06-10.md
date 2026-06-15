# US ABCD v3.5 — 审计日记 · 2026-06-10

**日期**: 2026-06-10
**归属**: US 侧 · ABCD v3.5(独立于 China ABCDS)
**审计对象**: 当日两份产出 — `risk_dashboard_2026-06-10.md` + `daily_2026-06-10.md`
**接续**: us_abcd_v35_audit_kickoff_2026-06-07.md

---

## 一、当日产出 / 审计范围

| 文件 | 角色 | 整体评价 |
|---|---|---|
| `risk_dashboard_2026-06-10.md` | 摘要 dashboard | 字母口径碰撞,结构性 broken,需修 |
| `daily_2026-06-10.md` | 完整日更 | 90% 干净,两条明确 bug + 三处口径松动 |

**核心结论**:日更版扎实,dashboard 在渲染层有问题。修 dashboard 的字母口径碰撞 + 同步显示 VTS 双比率 + 修日更的两条 bug,这套就达到 v3.5 paper trade reading 套件标准。

---

## 二、Daily(日更版)审计

### 🔴 两条明确 bug

**Bug 1 · A Reserve 单位错(同份内自相矛盾)**

§四端快照里:
```
| A | Reserve | 3.01% | -0.04% | 🟢2.8~+∞ / 🟡2.2~2.8% / 🟠1.6~2.2% | ...
```

值是 "3.01%",阈值也都带 "%" 后缀。但 §"Layer 1: System Plumbing" 同一报告里写的是 "Reserves $3.01T"——正确单位是**万亿美元**。

**修**:直接改 "%" → "$T",阈值同步改。

**Bug 2 · HY OAS 趋势箭头方向反了**

§触发距离里:HY OAS 20dΔ = **-7bp(压缩)**,正在**远离** 300bp ⚠️上沿,但画了 **▲(逼近)**。应该 **▼**。

其他四行箭头都对:DFII10 ▲ 配 +28bp / Mortgage ▲ 配 +42bp / 5Y5Y ▼ 配 -5bp / EFFR-IORB → 配 -1bp。**只有 HY OAS 反了。**

**修**:不只是改这一格——查判定逻辑,可能是"距阈值越近=▲"而不是"指标 20dΔ 方向"。**修逻辑层**。

### 🟡 口径松动

1. **HY OAS 单位混用**:§"v3.5 信号检查" 里写 "2.75%",其他地方全是 "275bp"。**unify 成 bp**(阈值表 native 单位)。

2. **CASC 表"状态"列两种语义**:VIX/MOVE 行写"当前态"(抬升/平静),FX 行写"触发阈值"(>+2.5%)。**列名拆分 Current vs Watch**,或把 FX 行也写当前态。

3. **Mortgage stale 标签不在表内**:§数据完整性 底部诚实标了 "MORTGAGE_SPREAD 可能未更新(last: 2026-06-04)",但 §四端快照 Mortgage 6.48% / +42bp 那行没就地标 stale。**修法**:就地加 "(06-04, 6d stale)" 内嵌标签。**新鲜度纪律标准做法 = 读到哪标到哪,不只在脚注**。

   **⚠️ 口径锁定:** stale 天数用**日历日**（`(today - last_date).days`），不用交易日。代码层已统一(`_indicator_row` stale_note 和 `check_staleness` 都用 `.days`)，审计侧同步对齐。今后 stale 计数一率日历日。

   附:**MORTGAGE_SPREAD vs mortgage rate 关系未说清** — 如果不是同一 series,可能 mortgage rate 本身新鲜,只是衍生 spread series stale。需要在文档里讲清楚。

### 干净的部分

- **Vintage 双标签**:`FRED T-0 / Yahoo T-2 + 日期` — 每源单独标 ✓
- **ABS/DUR=生效, ROLL=评估** 状态行每份带 — 元数据健康
- **每指标阈值带 + 当前值 + 20dΔ 都明示** — 不用废话词
- **§仓位动作 Step-by-step** 把 R2(55/25/20) → R3(40/30/30) → A-B 背离(-5p +5h) → **35/35/30** 完整推一遍 — **完全可审计**
- **VTS 分解清楚**:`期限结构=contango(0.910)` + `前端=前端紧张(1.041)`,**两段不矛盾,只是不同段**(背端 30d-vs-90d 正常斜率,前端 9d-vs-30d 有恐慌凸起)
- **RCV §0.9** 分 2y/10y/30y + z-score + tilt — 比单值可读
- **双探针互锁 = agree-front** — 综合定性,不是各报各的
- **HY/IG OAS ⚠️自满 标签** — 不把低 OAS 当 reassurance
- **Mortgage 条件触发(需 HY<455bp 配合)** — 显式条件名出
- **ON RRP $0.6B → "!! <$100B Tightening !!"** — 缓冲抽干 framing 正确(fragility up ≠ 危机已现)
- **观察项 利率路径 DGS2−IORB = +50bp / 5dΔ +10bp ▲** — 代理项工作正常
- **明日检查 6 条具体可验** — 不是"密切关注"废话

---

## 三、Dashboard(摘要)审计

### 🔴 严重 · §② 与 §③ 字母口径同份内碰撞

| Section | A | B | C |
|---|---|---|---|
| **§② 第一层传导** | A 资金管道 = EFFR-IORB / SOFR-IORB | — | C 长端利率 = DFII10 |
| **§③ 系统性风险触发器** | **A 信用** = HY/IG OAS | **B 流动性** = EFFR-IORB | C 跨资产/跨境 |

§② 的 A/C 跟 v3.5 框架对得上(A=Fed plumbing,C=real rates)。§③ 的 A 跑去当"信用"(框架里这是 B),B 跑去当"流动性 / EFFR-IORB"(框架里这是 A)——**EFFR-IORB 在 §② 是 A,到 §③ 就变成 B**。

**这是 v3.5 框架字母含义被本份报告内部破坏。**

**修法**:§③ 三个触发器**用纯数字 T1/T2/T3,或重排去对齐框架字母**(B 信用 / A 流动性 / D 跨资产)。

### 🟡 §① 和 §④ 对 VTS 状态字面矛盾(渲染层 bug,非逻辑 bug)

Dashboard:`§① 前端紧张` vs `§④ VTS = contango`。

**这条逻辑是对的,只是渲染压缩丢了信息**——VTS 实际是两段(背端 contango 0.910 + 前端紧张 1.041),日更版那行写了具体比率所以不矛盾。Dashboard 把两段压成两个独立标签,读起来就矛盾。

**修法**:dashboard 同步显示两个比率:`VTS全段=contango(0.910), VTS前端=紧张(1.041)`。

### 🟡 §② DUR5 列不对称

EFFR-IORB DUR5=5/5,SOFR-IORB DUR5=—(未追踪)。两个都是 A 域 plumbing 同色 🟠。**要么补 SOFR-IORB DUR(历史回填),要么 footnote 说明暂不追踪的理由。**

### Dashboard 没问题但请下次澄清(口径文档化缺失)

- 仓位 P=35/H=35/C=30 vs 之前 R3 基线 30/30/40 — **日更版给出了完整推导(R2→R3→A-B背离),解释清楚了,dashboard 不必重述但可加一句注脚**
- 跨域信号 = 2,哪两个?列出来
- 🔴=1 口径:DFII10 是那个;§② 还有两个 🟠 不计入 🔴 count — 口径写死

### Dashboard 干净的部分

- 日期诚实,vintage 对得上
- "非系统性·近端事件"定性 — 双探针前端一致时不升系统性,这是对的
- 触发器条件全列明,阈值和当前值都摆
- 翻转点事前命名 — "RCV → long-led/acute-broad 叠 VTS 倒挂 → agree-systemic"
- HY/IG OAS 标 "⚠️自满" — quiescence 不当 reassurance
- 跨域信号 = 2 / 🔴 = 1 量化,不用废话词

---

## 四、实质性变化(超出审计范围的市场观察)

**C 端真实利率压力在加深,不是噪声**:

| 日期 | DFII10 | DGS2−IORB |
|---|---|---|
| 06-04 | 2.07% | — |
| 06-05 | 2.11% | +43bp |
| 06-10 | **2.21%** | **+50bp** |

- DFII10 20dΔ **+28bp**, DUR5 **5/5** ✅
- 同期 BEI 在 🟡 区(2.33%),通胀预期同步微升
- 同期 DGS2−IORB 5dΔ +10bp

**长端真实利率推升 + 短端"降息被 price out"同步发生** = C 端是这一周框架里**最确凿的趋势变量**。Dashboard 用 "🔴=1 个域" 给到了,日更版用 DUR 5/5 ✅ 锁定了。**这不是事件性噪声,是真在动。**

---

## 五、处置优先级 / 修复清单

| 优先级 | 项目 | 文件 | 类别 |
|---|---|---|---|
| **马上** | Reserve 单位 "%" → "$T" | daily | Bug 1 |
| **马上** | HY OAS 趋势箭头逻辑修(▲/▼ 应看 20dΔ 方向) | daily | Bug 2 |
| **马上** | §③ 触发器字母改 T1/T2/T3 或对齐 v3.5 | dashboard | 严重 |
| **本周** | HY OAS 单位统一成 bp(v3.5 信号检查那处改) | daily | 口径 |
| **本周** | CASC "状态"列拆 Current vs Watch | daily | 口径 |
| **本周** | Mortgage stale 标签内嵌 + 澄清 MORTGAGE_SPREAD 关系 | daily | 新鲜度 |
| **本周** | VTS 0.910 / 1.041 两比率显式写在 dashboard | dashboard | 渲染 |
| **本周** | SOFR-IORB DUR5 补 or footnote | dashboard | 对称 |
| **小问题** | 跨域信号列名、🔴 计数口径文档化 | dashboard | 文档化 |

---

## 六、本日审计纪律自检

- ✓ 用元纪律框审(新鲜度 / 单位口径 / 确认计数)
- ✓ 不踩"空值当当日"那条 — 两份报告新鲜度都诚实(daily Yahoo T-2 显式标,Mortgage stale 底部标)
- ✓ 撤回过往一条质疑(dashboard "35/35/30 vs 30/30/40"):日更版的 step-by-step 推导给出完整答案,基线没变,是 A-B 背离 overlay 调的 — **质疑收回**
- ✓ 撤回过往一条质疑(dashboard "VTS contango vs 前端紧张"):**两段不同段,渲染层 bug,逻辑没问题** — **质疑改为"渲染建议"**
- ✓ 区分了 bug(必修) / 口径松动(应修) / 文档化缺失(请澄清) / 干净部分(确认) 四档

---

*接续指针:下一份 v3.5 审计在本文件后续追加,或新开 dated 文件。BLOCKER 类问题(若产生)单独标记。*
