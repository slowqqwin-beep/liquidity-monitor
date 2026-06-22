# TLT Leg-2 Spec — 信用利差信号（z⊕level 修订版）

> **状态**：Spec（未实现）
> **版本**：v6 — z⊕level，gate=400bp，Phase 3 三叉判据预注册（2026-06-22）
> **依赖**：Leg-1 cooling-z 已固化（Δ20/z252/−1.0，counter≤3，四组验收全 PASS）
> **数据**：`data/BAMLH0A0HYM2_tv_full.csv`（TradingView，FRED-一致，7,694 行，1996-12-31 ~ 2026-06-17）

---

## 0. 背景

### 0.1 TLT 当前触发（单腿）

H45 配置计划 §4 定义的触发：

> cooling 累积 ≥ 2/3 **且** DFII10 破 2.0%

单腿设计——两个条件都来自同一个底层（DFII10）。AND 退化为一信号看两次。

### 0.2 为什么需要第二腿

TLT 久期多头赌的是「真实利率退潮」。但如果真实利率回落的同时信用利差在飙升：

| 场景 | 真实利率↓ | 信用利差↑ | TLT 上涨原因 |
|------|----------|----------|-------------|
| **真退潮** | 联储转鸽、通胀回落 | 稳定/收窄 | 贴现率下行 → 久期受益 |
| **假退潮** | 信用恐慌 → 避险买国债 | 飙升 | flight-to-quality，信用稳住后可能暴力回撤 |

leg-2 的任务：**区分真退潮和假退潮**。冷却信号触发时，确认信用市场没有同时在恐慌。

### 0.3 数据先验

HY OAS 全量文件：7,694 行，1996-12-31 ~ 2026-06-17。无 NaN / 负值 / 重复日，无 >7d 断层。Canonical 极值验证通过：

| 事件 | 极值 | 日期 |
|------|------|------|
| 历史低点 | 241bp | 2007-06 |
| GFC | 2,182bp | 2008-12-15 |
| COVID | 1,087bp | 2020-03-23 |
| SVB | 522bp | 2023-03-24 |

Pre-2023 无法拿 FRED 二次核（FRED 已不给），但这些 canonical 极值对得上公认数字 → 可信。

### 0.4 纯 z 版本的实测失败（v1 废弃原因）

在真数据上跑纯 `credit_stress_z = (Δ20 OAS − μ252) / σ252` 后，暴露两个致命缺陷：

**坏法一：持续危机里 z 自己熄火。**

| 月份 | HY OAS 均值 | mean z | z 解读 |
|------|------------|--------|--------|
| 2008-10 | 1,530bp | 4.04 | 🔴 加速段，对 |
| 2008-11 | 1,790bp | 0.96 | 🟡 已不到 +1.0 |
| 2008-12 | 2,031bp | 0.55 | 🟢 NORMAL？OAS 在 2000bp 以上 |
| 2009-01 | 1,673bp | −2.07 | 🟢 IMPROVING？灾难水平 |

z 测的是加速度不是状态。σ252 被 9-10 月巨震撑大后（~60bp），再大的绝对利差也压不出 z。后果：纯 z 的 leg-2 在 09Q1 会放 TLT 进场——而那正是 safety bid 即将反转的时点（TLT 08 年底见顶、09H1 跌），是 leg-2 要拦的核心场景。

**坏法二：平静期 z 过敏。**

2021 年（极度自满，OAS 300–393bp），σ252 缩到 ~8bp，几 bp 噪音就顶出 max z=2.84，全年 47/262 天 >+1.0。纯 z 会在 benign 市场对噪音乱否决——威胁 2019 那种「benign 信用 + 真实利率回落、leg-2 本该放行」的增量价值场景。

**结论**：纯 z 否决的两个尾巴都坏。不改回裸水平阈值，改 z⊕level。

---

## 1. 信号定义（z⊕level）

### 1.1 输出契约

`compute_credit_stress_z()` 每日输出两个值：

| 输出 | 公式 | 含义 |
|------|------|------|
| `credit_stress_z` | (Δ20 OAS − μ252 Δ20) / σ252 Δ20 | 信用走阔的 z-score 动量 |
| `hy_oas_bp` | HY OAS × 100 | 信用利差水平（bp） |

否决逻辑需要两者。

### 1.2 veto 公式（z⊕level）

```
veto = (OAS ≥ high_floor) OR (credit_stress_z > +1.0 AND OAS ≥ low_gate)
```

| 参数 | 暂定值 | 作用 | backtest 校调 |
|------|--------|------|--------------|
| `high_floor` | **750bp** | 水平够高 → 强制否决，不管 z 是否已被 σ 抚平 | 700–800 之间校 |
| `low_gate` | **400bp** | z > +1.0 的门槛底板——压平静期 z 噪音 | ✅ 从分布定，不从事后事件凑 |
| z 阈值 | **+1.0** | 标准 z-score 否决线（仅当 OAS ≥ low_gate 时生效） | ✅ 留 |

**z 保留**：OAS 还不高时抢先抓加速度——2018Q4（z=3.45 @ 538bp）、COVID 早段（z=7.12）——§1.4 对 z 的论点对，留着。

**level 补（分布锚定，非事件拟合）**：

`high_floor` = **750bp**（≈p86）：所有真危机（2015-16 887bp、2011 910bp、COVID 1087bp、GFC 09Q1 1886bp、GFC 峰 2182bp）都 ≥750 被强否；中等事件（2018Q4 538bp、SVB 522bp）落 750 以下，交给 z-arm。代价真实：750 会强否 14.3% 交易日——含 08Q4 那种历史上最强的 TLT 避险 rally 之一。它把"09Q1 安全 bid 反转"和"08Q4 安全 bid 猛涨"一刀切掉。保守取舍，不是 bug。

`low_gate` = **400bp**（≈p40，benign↔stress 自然断点）：375bp 在第 32 百分位——2021 benign 年 OAS 最高 393bp，有 16/262 天 ≥375，z-arm 在那些天仍活着、z 噪音（max 2.84）照样能否决。400bp 才真盖住 benign 带顶：2021 全年 **0/262 天 ≥400**。同时 2018Q4（538bp）、SVB（522bp）在 400 之上，z-arm 正常工作。

**为什么 high_floor 不用 500bp**：会把 2018Q4（538bp）、SVB（522bp）那种中等事件也按 level 强否。这些事件 z 本身就抓住了加速度——让 z 测就够了，level 只补 z 测不到的那段（持续危机中 z 熄火后的高 OAS 区域）。

### 1.3 TLT 入场与否决

```
TLT entry allowed = (cooling-z counter ≥ 2/3) AND (NOT veto)
```

| cooling counter | veto | TLT 入场 | 逻辑 |
|:---:|:---:|:---:|---|
| ≥ 2/3 | ❌ 否决 | ✅ 入场 | 真实退潮 + 信用ok |
| ≥ 2/3 | ✅ 否决 | ❌ 拦 | 信用恶化 → safety bid |
| < 2/3 | — | ❌ 等待 | 冷却未确认 |

### 1.4 TLT 退出

```
TLT_EXIT = (cooling_counter = 0 持续 ≥ 5 日)
           OR (OAS ≥ high_floor)
           OR (credit_stress_z > +2.0)
```

退出也是 level-aware：high_floor 触发的强否同样适用退出——OAS 在 750bp 以上时不应该持有 TLT，不管 cooling 状态。

z > +2.0 保持作为加速度恐慌退出（实测占 6.4% 天数，右肥尾，偏频但不算太宽）。

### 1.5 与现有 systemic triggers 的关系

Risk OS 的 T1 credit trigger（`HY OAS ≥ 300bp`）是**系统性风险**信号，用于防御仓位。

TLT leg-2 veto 是**信用恐慌否决**，用于 TLT 入场门控。

两者独立：
- HY OAS = 350bp 但 z < +1.0 且 OAS < high_floor：T1 可能亮红灯（defense），但 leg-2 不否决（不是恐慌）
- HY OAS = 250bp 但 z > +2.0：T1 绿区，但 OAS < low_gate → leg-2 不否决（z 噪音被 low_gate 压住）
- HY OAS = 800bp 无论 z 多少：leg-2 强否（high_floor），T1 也亮

---

## 2. 四组验收框架

### Test A — 否决频率合理（不要频率带）

**原纯 z 版设了 P(z>1.0) 5-25% / P(z>2.0) 2-5% 频率带——实测 z>2.0 = 6.4%（右肥尾），这带会"fail"在一个非问题上。否决信号的验收锚应是 Test B（抓没抓住事件），不是频率带。**

**新验收标准**：
- `P(veto)` 不应 > 50%（否决太宽 = 信号无用）
- `P(veto)` 不应 ≈ 0%（否决太窄 = 信号不在工作）
- 否决天数主要集中在已知信用事件窗口内（见 Test B）
- 平静期（2021、2017、2014）否决天数应极少（low_gate 压噪）

### Test B — 响应真事件（z⊕level 版）

| 事件 | 日期 | 预期 veto = high_floor ∨ (z>1.0 ∧ OAS≥low_gate) | 实测 |
|------|------|------|------|
| **GFC 加速段** | 2008-09 ~ 10 | ✅ veto（z=6.08，OAS≫low_gate） | z 抓住加速度 |
| **GFC 持续期** | 2009-01 ~ 03 | ✅ veto（OAS 1,673-1,886bp ≫ 750bp → high_floor 强否）| **纯 z 会漏，z⊕level 拦住** |
| **COVID** | 2020-03 | ✅ veto（z=7.12，OAS≫low_gate） | z 抓住 |
| **2011 EU** | 2011-08 ~ 10 | ✅ veto（z=4.55，OAS ~850bp） | 双触发 |
| **2015-16 能源** | 2015-12 ~ 2016-02 | ✅ veto（z=2.25，OAS ~887bp） | |
| **2018 Q4** | 2018-12-24 | ✅ veto（z=3.45 @ 535bp，12/24 峰；OAS 峰 544bp@2019-01-03） | z 抓中等事件加速度，level 不干预 |
| **SVB** | 2023-03 | ✅ veto（z=1.73，仅 2d >1.5，但 OAS=522 ≥ 400） | 勉强过 z，low_gate 托底 |

> **边际注（SVB）**：SVB 43.5%（10/23d）是所有应激事件里否决最弱的，且全靠 z-arm（hf=0，522 < 750）。这不是 bug——SVB 的真压力在银行融资/区域行权益，broad HY OAS 只动了 430→522bp，在 2022 撑大的 σ 基线下勉强够 z-gate。任何想把 SVB 否决率拉高的调参（降 high_floor 或松 z 阈值）都会把 2021 过敏和 14% 强否带回来——别动。SVB 又是 TLT safety-bid 陷阱最活的事件（23-03 国债猛 rally 后回吐），是 Phase 3 最该盯的边际样本。
| **2021 自满期** | 2021 全年 | ❌ 不否决（OAS 300-393bp < 400 low_gate，0/262d 触发 gate → z 噪音被全压） | **纯 z 47d >1.0 过敏，z⊕level 压住** |
| **2019 降息** | 2019 全年 | ⏳ deferred → Phase 3 | leg-2 standalone veto=16/261d，但"放行好进场"是 joint 条件（leg-1 点火且 leg-2 不否）。度量应是 P(leg-2 veto \| leg-1 ignition) 在 2019，目标 ≈0——leg-2 单序列的 16/261 看不出，因为 16 天可能全落在 leg-1 未点火日（完全无害），也可能压在关键进场点（那才是问题）。等 Phase 3 合并判断 |

**验收**：
- GFC 09Q1 必须否决（纯 z 漏的，z⊕level 必须拦住）✅
- 2021 否决天数 = 0（纯 z 47 天过敏，400bp gate 全压）✅
- 2019 否决天数 16/261d — ⏳ deferred → Phase 3（leg-2 单序列数无意义，需 P(leg-2 veto | leg-1 ignition) 在 2019）
- SVB 期必须否决 ✅

### Test C — 腿间正交（Leg-1 ⊥ Leg-2）

⏳ **deferred → Phase 3**——leg-2 standalone 不可判。等两序列合并后，按 z⊕level veto 定义重测条件概率。

```
┌──────────────┬──────────┬──────────┐
│              │ leg-2 🟢 │ leg-2 🔴 │
├──────────────┼──────────┼──────────┤
│ leg-1 🟢     │    a     │    b     │
│ leg-1 🔴     │    c     │    d     │
└──────────────┴──────────┴──────────┘
```

- `P(leg-2 🔴 | leg-1 🔴)` = d/(c+d)
- `P(leg-2 🔴 | leg-1 🟢)` = b/(a+b)

如果两腿独立 → 两个条件概率应接近。AND-of-two lint 静态分析已通过（DFII10 vs HY OAS，OAS 设计扣除匹配国债），统计验证等合并后。

**注意**：leg-2 加了 level 项（high_floor/low_gate），否决分布变了——正交性按新定义（z⊕level veto）重测。

### Test D — 无静默失败

- (a) NaN 不应被当作 OK ✅ — 有效期内 0 NaN（7,422 天全有 z 值）
- (b) 零标准差不应产生 Inf ✅ — 无 Inf
- (c) 数据不足应标记（< 252+20 行） ✅ — quality_flag 标记前 272 天为 warmup
- (d) 否决不应在系统休眠 ✅ — veto=TRUE 1,779/7,422 天（24.0%），信号活跃
- (e) CSV 覆盖 1996-2026，期间无系统性断层 ✅ 已验证

---

## 3. AND-of-two 结构

### 3.1 TLT 入场

```
TLT_ENTRY = (cooling_counter ≥ 2/3) AND (NOT veto)
veto = (OAS ≥ 750bp) OR (credit_stress_z > +1.0 AND OAS ≥ 400bp)
```

### 3.2 TLT 退出

```
TLT_EXIT = (cooling_counter = 0 持续 ≥ 5 日)
           OR (OAS ≥ 750bp)
           OR (credit_stress_z > +2.0)
```

---

## 4. Backtest 计划

### 4.1 数据

`data/BAMLH0A0HYM2_tv_full.csv`：7,694 行，1996-12-31 ~ 2026-06-17。

### 4.2 样本内关键事件

| 年份 | 事件 | HY OAS 极值 | z⊕level 否决预期 |
|------|------|------------|-----------------|
| 1998 | LTCM / Russia | ~900bp | high_floor 强否 |
| 2000-02 | 互联网泡沫退潮 | ~1,100bp | high_floor 强否 |
| 2008-09~10 | GFC 加速段 | 2,182bp | z 否决 |
| 2009-01~03 | GFC 持续期 | 1,886bp | high_floor 强否（纯 z 熄火） |
| 2011 | 欧债危机 | ~850bp | high_floor 强否 |
| 2015-16 | 能源 HY 崩盘 | ~900bp | high_floor 强否 |
| 2018 Q4 | 缩表恐慌 | ~530bp | z 否决（level 不干预） |
| 2020-03 | COVID | 1,087bp | z + high_floor 双否 |
| 2023-03 | SVB | 522bp | z 否决（z=1.73，勉强过 gate） |

### 4.3 两腿联合 backtest

```
for each day in 1997-01-01 .. 2026-06-17:
    cc = cooling_counter(day)
    veto = (OAS ≥ 750) or (z > 1.0 and OAS ≥ 400)
    tlt_entry = (cc >= 2/3) and (not veto)

    if tlt_entry and not in_position:
        enter TLT at close
    if in_position and exit_condition:
        exit TLT at close

→ TLT return stream
→ vs: a) TLT buy-and-hold  b) Leg-1 only  c) Leg-1 + naive OAS<300
```

### 4.4 关键检验（z⊕level 版）

1. **2008-10**：cooling 触发 → z veto 拦 → ✅ 不进场
2. **2009-01~03**：cooling 仍在触发 → **纯 z 会放行，z⊕level 因 high_floor 强否拦** → ✅ 这是 z⊕level 对纯 z 的核心胜出场景
3. **2020-03 COVID**：cooling + 信用恐慌 → veto ✅
4. **2019**：cooling 确认、信用 benign（OAS 350-450bp，<400 时 z 被 gate 压）→ ✅ 入场
5. **2021**：如果 cooling 触发（2021 真实利率低但可能有局部回落），信用 OAS max 393bp < 400 → z 噪音被全压 → ✅ 0 天误否决
6. **2018 Q4**：cooling 触发（假设）→ z=3.45 @ 538bp ≥ 400 → veto ✅。中等事件，z 抓加速度而不是 level 强否——这是 z⊕level 的优雅处。

---

## 5. 实现路径

### Phase 1：credit_stress_z + veto 计算（~50 行 Python）

```
脚本：scripts/compute_credit_stress_z.py
输入：data/BAMLH0A0HYM2_tv_full.csv
输出：data/credit_stress_z.csv
列：date, hy_oas_bp, delta20, z, veto_high_floor, veto_z_gate, veto
```

输出契约：z 和 OAS level 都在同一行，否决逻辑调用方直接用 `veto` 列。

### Phase 2：否决验收（~120 行 Python） ✅ DONE

```
脚本：scripts/validate_credit_veto.py
输出：data/credit_veto_validation.json
```

验收范围（leg-2 standalone 可判）：Test A 否决率上下界 + 平静期计数，Test B 应激事件行（GFC/COVID/2011/2015-16/2018Q4/SVB），Test D 静默失败护栏。

暂缓到 Phase 3：Test C 腿间正交（需两序列）、Test B 2019 行（需 P(leg-2 veto | leg-1 ignition) 才可判）。

结果：**16 PASS / 0 FAIL / 2 DEFERRED**。

### Phase 3：两腿联合 backtest + 三叉判决（~300 行 Python）

```
脚本：scripts/backtest_tlt_two_leg.py
输入：data/real_yield_cooling_counter 全量 + data/credit_stress_z.csv
输出：data/tlt_two_leg_backtest.json + data/tlt_help_hurt_ledger.csv
预设参数（均已预注册，跑之前写死）：
  EVENT_MIN_GAP   = 10      # 相邻进场 episode 最短间隔（交易日）
  N_EPISODE_FLOOR = 8       # INSUFFICIENT 地板：N_decisive (help+hurt) < 8 → 退人眼
  HURT_CAP_RATIO  = 0.15    # N_hurt ≤ 15% × N_episode
  NEUTRAL_BAND    = 0.01    # |反事实收益| < 1% → NEUTRAL，不计入 help/hurt
```

#### 3.0 判据预注册（跑之前看完）⚠️

**判据不在组合 Sharpe 上，在逐 episode help/hurt 账上。** 理由：joint 入场（leg-1 点火且 leg-2 不否）历史上低-N——靠组合 Sharpe 判生死全是噪音，门必须可证伪。

**计数单位是 episode（去重后的进场事件），不是交易日。** cooling 点火是成簇的——一次退潮持续几周，按天算一个三周退潮被 leg-2 否掉就是 ~30 个 help/hurt，`N_hurt ≤ X` 瞬间失去意义。用 `EVENT_MIN_GAP` 去重，同一 episode 内连续否决日合并为一个 episode 级判定。

##### 步骤〇：枚举 leg-1 的进场 episode

取 cooling counter 全量 → 定位所有 `cooling_counter ≥ 2/3` 的日子 → 按 `EVENT_MIN_GAP` 去重为 episode 列表：

- 相邻 episode 间隔 ≥ `EVENT_MIN_GAP` 交易日 → 独立 episode
- 同一 episode 内：leg-2 在 episode 期间任一天 veto → 该 episode 被 leg-2 否决

记 `N_episode = len(episodes)`（用于 hurt 帽的分母）。

##### 步骤一：episode 级 leg-2 否决判定

对每个 episode：

- 若 leg-2 在 episode 内任一天 t 触发 veto（且 leg-1 当天也点火）→ 该 episode 被 leg-2 否决
- 每个被否决的 episode → 算反事实收益（见步骤二）

##### 步骤二：反事实收益 → help / hurt / neutral

对每个被 leg-2 否决的 episode，假设 leg-2 不否决：以 episode 首个 leg-1 点火日的 TLT 价格进场 → 持有到 leg-1 退出条件触发 → 算持有期总回报（含价格变动 + 分红）。

| 判定 | 条件 |
|------|------|
| **HELP** | 反事实收益 ≤ −NEUTRAL_BAND | 拦掉一个事后亏的进场 |
| **NEUTRAL** | −NEUTRAL_BAND < 反事实收益 < +NEUTRAL_BAND | 微涨微跌，不计入判决 |
| **HURT** | 反事实收益 ≥ +NEUTRAL_BAND | 拦掉一个本该赚的进场 |

中性带防止零附近的噪音翻转账——反事实收益接近 0 的 episode 不强行归为 help 或 hurt。

##### 步骤三：计数

- `N_help` = HELP episode 数
- `N_neutral` = NEUTRAL episode 数（记录但不影响判决）
- `N_hurt` = HURT episode 数
- `N_decisive` = N_help + N_hurt——**leg-2 真出手且结果非中性的 episode 数，即有信息的证据量**
- `N_vetoed` = N_help + N_neutral + N_hurt（leg-2 否决的总 episode 数）
- `N_episode` = leg-1 历史总进场 episode 数（用于 hurt 帽的分母）

**若 N_decisive < N_EPISODE_FLOOR → 直接 INSUFFICIENT（见步骤四）。** 证据不够时，help>hurt 不能当 GO——从门缝溜进去的 GO 不是真信号。信用承压 ∩ leg-1 点火本就稀有，INSUFFICIENT 是诚实结果，不是 bug。

##### 步骤四：三叉判决（跑之前写死）

| 结局 | 条件 | leg-2 归宿 |
|------|------|-----------|
| **INSUFFICIENT** | N_decisive < N_EPISODE_FLOOR | 数据不够、固化不了——退人眼否决 / research veto。**与 SR3 同落点：信号建起来、看、不进触发。** |
| **GO** | N_decisive ≥ N_EPISODE_FLOOR **且** N_help > N_hurt **且** N_hurt ≤ floor(HURT_CAP_RATIO × N_episode) | leg-2 固化进 `TLT_ENTRY` 公式 |
| **NO-GO** | N_decisive ≥ N_EPISODE_FLOOR **且** (N_help ≤ N_hurt **或** N_hurt > floor(HURT_CAP_RATIO × N_episode)) | leg-2 **不进触发**，退回人眼否决 / research veto。与 SR3、SOFR 同落点 |

**所有三条分支都是预先写下的可接受结局。** INSUFFICIENT 尤其——N_decisive 不够，和 NO-GO 一样不进触发。信用承压 ∩ leg-1 点火本就稀有，leg-2 是个罕见介入的工具。现实够不着 GO，人眼就是对的答案。

##### 关键边际样本

- **SVB（2023-03）**：否决最弱（43.5%，全靠 z-arm，hf=0），但恰是 TLT safety-bid 陷阱最活的事件（23-03 国债猛 rally 后回吐）。Phase 3 最该盯的边际 case。
- **2019**：hurt 检验点——若 leg-2 的 16/261 否决日恰好叠上 leg-1 点火 episode，且反事实收益为正 → HURT episode。
- **09Q1**：help 检验点——high_floor 强否拦掉 safety-bid 反转进场 → HELP episode。
- **08Q4**：high_floor 一刀切代价的实证——若 leg-1 在这段点火，leg-2 high_floor 强否会拦。反事实收益决定它是 HELP 还是 HURT。

##### 旁证（不作判据）

组合 P&L（Sharpe / 最大回撤 / MAR）仅作旁证。Test C 腿间正交和 Test B 2019 放行都在这一跑里一并落地。

输出：`tlt_help_hurt_ledger.csv` 逐行记录每个 episode 的起止日期、episode 内 veto 天数、反事实收益、help/hurt/neutral 判定。

---

### Phase 4：管线接入

- `daily_report.py` 追加 `_compute_credit_stress_z_with_veto()`
- Dashboard 加一行：`TLT Leg-2：z [X.X] | OAS [YYY]bp | veto [YES/NO]`
- `H45_configuration_plan.md` §4 更新触发条件

---

## 6. 已落地的决策

| # | 问题 | 决策 | 理由 |
|---|------|------|------|
| 1 | z 阈值 | **+1.0** ✅ 留 | 纯 z 时 +1.0→P=18.3%，抓除 SVB 外全部；现在有 low_gate 压噪，+1.0 可以用 |
| 2 | z 瞬时 vs counter | **瞬时值** ✅ 留 | 否决单日即可——误否决成本「等一天」，信用恐慌不等人 |
| 3 | TLT 退出 credit 条件 | **OAS≥high_floor ∨ z>+2.0** | 纯 z 的「仅 z>2.0」改——危机持续期 z 熄火，需 level 补 |
| 4 | live 取数 | **每日从 panel** ✅ 留 | FRED live panel 3y 窗够算 z252；⚠️ 与 TV 全量源仅在 2025-26 overlap 核过，注意 ICE 修订 |
| 5 | 纯 z vs z⊕level | **z⊕level**（纯 z 废弃） | 实测两尾巴坏——GFC 熄火 + 2021 过敏。level 补两个洞，z 保留加速度优势 |
| 6 | low_gate 值 | **400bp**（非 375） | 分布定：400≈p40，2021 0/262d≥400 真全压。375 只 p32，2021 有 16d≥375 仍可被 z 噪音否决。非事后拟合 |

---

## 7. H=45% BIL 优先级提醒

> **这条 leg-2 是把对冲端做精——但对冲端到现在还是空的。**

`H45_configuration_plan.md` 定义的第 1 批 BIL（卖 20% SGOV → 买 20% BIL）是当前账户最大未对齐项。在 leg-2 走进管线之前，先把对冲端建起来。

---

## 附录 A：AND-of-two lint 检查清单

- [ ] A. leg-1 和 leg-2 的输入序列是否不同？ → ✅ DFII10 vs HY OAS
- [ ] B. 计算逻辑是否独立？ → ✅ 各自独立，leg-2 多了 level 项但不共享输入
- [ ] C. 统计独立性（Test C）是否通过？ → ⏳ deferred → Phase 3（两序列合并后，按 z⊕level veto 定义重测）
- [ ] D. 是否存在「A 触发几乎必然 B 触发」？ → ⏳ 待验证
- [ ] E. 如果 C/D 不过，AND 是否退化为单腿？ → ⏳ 待判断

---

## 附录 B：HY OAS 数据源记录

| 属性 | 值 |
|------|-----|
| 文件 | `data/BAMLH0A0HYM2_tv_full.csv` |
| 来源 | TradingView（ICE BofA US High Yield OAS，FRED 直出） |
| 范围 | 1996-12-31 ~ 2026-06-17 |
| 行数 | 7,694 |
| 格式 | `date,hy_oas_pct`（OAS 以 % 表示，3.13 = 313bp） |
| 与 FRED 一致性 | ✅ 已验证（2025-05 ~ 2026-06 overlap 无偏移） |
| 历史低点 | 241bp（2007-06） |
| GFC 极值 | 2,182bp（2008-12-15） |
| COVID 极值 | 1,087bp（2020-03-23） |
| SVB 峰值 | 522bp（2023-03-24） |
| FRED 3 年窗限制 | 不影响本数据——TradingView 全量 |
| 更新方式 | 手动重下载（TradingView 不支持自动 API） |

---

> **Changelog**：
> - v6（2026-06-22）：Phase 3 判据从二值改三叉。分母拆开：hurt 帽分母 = N_episode（总进场数），INSUFFICIENT 地板 = N_decisive = N_help+N_hurt（非中性证据量）。N_decisive < 8 → INSUFFICIENT。计数单位从天 → episode（EVENT_MIN_GAP=10）。N_hurt ≤ floor(15%×N_episode)。中性带 |反事实收益|<1% → NEUTRAL。
> - v5（2026-06-22）：Phase 3 判据预注册。help/hurt 逐事件账替代组合 Sharpe 作为 go/no-go 判据，no-go 分支明文（N_help ≤ N_hurt → leg-2 退回人眼否决）。关键边际样本点名：SVB/2019/09Q1/08Q4。加 SVB 否决最弱边际注（不改参）。
> - v4（2026-06-22）：Phase 2 完成。`scripts/validate_credit_veto.py` 产出 `data/credit_veto_validation.json`，16 PASS / 0 FAIL / 2 DEFERRED。2019 行 + Test C 标 `deferred → Phase 3`。实测确认：2021=0/262d（gate=400 全压），GFC 09Q1 high_floor 65/65 强否，两臂量级相当 (1,099 vs 922)。2014 OAS 335-571bp 非平静年从 A3 剔除。
> - v3（2026-06-22）：low_gate 375→400bp（分布锚定 p40，2021 benign 顶 393bp 全压）。加 Phase 3 go/no-go 门控定位（leg-2 可能归宿人眼否决，不进触发）。加 high_floor 代价记录（08Q4 真 rally 被一刀切）。加 §7 H=45% BIL 优先级提醒。
> - v2（2026-06-22）：纯 z → z⊕level。修正 SVB 峰值（503→522bp，3/13→3/24）。Test A 弃频率带。Test B 改写为 z⊕level 版。退出条件 level-aware。Decision #5 重开，#3 修正。Phase 1 输出契约加 level 列。
> - v1（2026-06-22）：初始纯 z spec。实测两尾巴坏后废弃。
