# Real Yield Spread 诊断层 Spec (g−r Overlay)

**状态: Tier 1 诊断 overlay，非触发器，非 clean v3.5 ledger 输入**
**创建日期: 2026-06-30**
**背景**: 由 DFII10 单一阈值（5/25 backtest 证伪，DFII10>2.00%/2.20% precision 均为 7.7%，低于 17.2% baseline，属反向指标）推广而来。核心逻辑从"r 绝对水平"改为"r 相对资产自身收益能力的差"——Gordon Growth Model 分母 (r−g)。黄金单阈值之所以有效，是因为黄金的 g 恒为 0；SPY/AI 板块/组合持仓的 g 不是 0，必须把这一项对冲掉才能公平比较。

---

## §0 这个模块是什么、不是什么

**是：**
- 一个连续读数 + 趋势，辅助 regime 判读
- 报告"real yield 相对资产自身收益能力的 spread 有多宽/多窄"，而不是单独报告 DFII10 高不高
- 与已有的 CASC / VTS / RCV / 2s10s（6/22 已建）同级别，进 regime dashboard，人工综合判断时参考

**不是：**
- 不是自动触发器，不产生 buy / sell / reduce 信号
- 不进 `paper_trade_v3_5_clean.csv`，不影响 7/1–7/31 clean ledger 的仓位判定，不是 clean v3.5 那 5 个信号之外的"第 6 个"
- 如果未来想把这里的某个具体数字变成自动执行规则（例如"spread < X% 时减仓 Y%"），必须走跟 TLT Leg-2 一样的 Tier 2 审计路径（N、precision、Bonferroni 修正、前后半段稳健性）。不能因为"这次看起来解释得通"就直接转正——这正是这几轮对话想避免的那个坑。

---

## §1 核心公式

### 1.1 市场层 real yield spread（主要指标，数据可靠）

```
RYS_market = EarningsYield_proxy − DFII10
EarningsYield_proxy = 1 / trailingPE（forwardPE 如稳定可用则并列输出，不替代 trailing）
proxy 标的：SPY（大盘基准）+ QQQ（成长/AI 权重更高的对照）+ IGV（软件板块，更贴近持仓风格）
```

### 1.2 组合层 real yield spread（主要指标）

```
RYS_portfolio = Σ(weight_i × EarningsYield_i) − DFII10
EarningsYield_i = 1 / trailingPE_i，逐个 ticker（CRM/SNOW/MSFT/DDOG/OKTA 等）计算
weight_i = 当前持仓权重
```
**权重来源**：从你实际维护持仓权重的那条数据源读取当前值，复用现有流程，不要新建一套。**不使用历史对话中出现过的具体权重数字**——那些是历史快照，不是当前状态，直接拿来用等于编数字。

**组合层 PE 结构（2026-07-01 发现）**：
Portfolio trailingPE 呈双峰分布——CRM/MSFT 在成熟盈利区间（18-22x），DDOG/OKTA 在刚转正/薄利润区间（99-668x，E/P 失真），SNOW 未转正（负 EPS）。这印证了组合的真实久期结构：CRM/MSFT 有 earnings cushion，DDOG/OKTA/SNOW 几乎无 cushion、估值靠 g 侧支撑。不允许用板块 ETF 的 PE 替代个股 PE——这样做等于磨平"这几个持仓本来就没有有意义的 trailing earnings"这个事实。portfolio RYS 在 PE 缺失/失真时保留 None + notes 描述，不做数值填补。

### 1.3 增长调整版（次要指标，允许缺失，不允许编造）

```
RYS_growth = ConsensusGrowthEstimate − DFII10
```
数据源 yfinance `info` 字典的 `earningsGrowth` / `revenueGrowth` 等字段，免费源经常缺失或滞后。
**规则：拉不到可靠数据就报 `data_quality: insufficient`，禁止用市场平均值或历史值填补——填补等于编数字，这条框架从 5/25 起就没让步过。**

---

## §2 数据源

| 变量 | 来源 | 备注 |
|---|---|---|
| DFII10 | FRED（已在 pipeline 里） | 沿用 Real Yield Nowcast 现有的清洗逻辑，不重建 |
| trailingPE / forwardPE（SPY/QQQ/IGV） | yfinance | ETF 层级这三个字段有时缺失，缺失即标 flag，不用个股均值替代 |
| trailingPE（持仓个股） | yfinance | 逐 ticker，个股数据完整度通常远高于 ETF 层级 |
| 持仓权重 | 你现有的权重维护流程 | 不要硬编码任何历史权重数字 |
| Growth estimate | yfinance info 字段 | 允许为 null，禁止编造 |

---

## §3 输出字段（仅这些，不许扩展）

```
date
DFII10
RYS_market_SPY
RYS_market_QQQ
RYS_market_IGV
RYS_portfolio
RYS_growth_market      (可为 null)
RYS_growth_portfolio   (可为 null)
RYS_market_20d_change
RYS_portfolio_20d_change
data_quality_flag      (ok / partial / insufficient)
notes
```

---

## §4 呈现方式

- 每次跑批输出一行，追加到 `real_yield_spread_diagnostic.csv`
- 和 6/22 已建好的 2s10s bull/bear steepen/flatten 面板放在**同一个 regime dashboard 里并排展示**，不合并成一个复合分数——合并等于又一次"跨域加权"，这条 v3.4 已经测过没有增益（F1 no improvement）
- dashboard 标题或页眉必须明确写"读数，非信号"，不能省略

---

## §5 CodeBuddy 实现时的红旗自查

违反任一条 = 停下来问，不要顺手改：

- 不要把 RYS 阈值化（比如"RYS < 5% 就标红触发"）——这等于重新发明一个新版 DFII10 阈值，只是换了公式外壳
- 不要把 RYS_market 和 RYS_portfolio 加权合并成一个分数
- 不要用市场平均值/历史值填补缺失的 growth 数据
- 不要让这个模块的任何输出出现在 `paper_trade_v3_5_clean.csv` 的任何字段里
- 如果发现自己在写"如果 RYS 触发就自动调整仓位"这类代码，立刻停止并汇报，不要"顺手实现了"

---

## §6 后续路径（如果以后想转正为 Tier 2 候选）

标准跟 TLT Leg-2 一致：
- 限定在 2023 年至今（高利率 regime）重新测，不用会稀释信号的完整 5 年窗口
- 报 N（独立事件数）、precision、F1
- Bonferroni 修正（这已经是第 N 次测 real-yield 相关假设，要算进去）
- 前后半段稳健性（2023H2 / 2024–2025 / 2026 YTD 分段看是否一致）
- 经济逻辑要写清楚：为什么这次用 spread 而非 level，理论上就该表现更好——这个理由现在就要写，不能等测完了再事后补

---

丢给 CodeBuddy 之前，把 §0 和 §5 整段贴过去，跟贴 REJECTED_SIGNALS 硬约束首行是同一个道理。
