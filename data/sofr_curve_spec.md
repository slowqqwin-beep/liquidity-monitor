# SOFR Implied Curve 指标 — 实现规格

> 数据源：手动维护的 `sofr_sr3.csv`（用户每天从 TradingView 抄 SR3 各合约价格）+ 框架已抓取的 EFFR
> 输出：进 ABCD 报告的路径特征（隐含终点 / 首降时点 / 累计降息bp）
> 定位：补现有指标（DGS2−IORB 给方向、2s10s 给形态、cooling 给真实利率）没有的"降息路径精度"

---

## 0. 数据流

```
用户手动填 sofr_sr3.csv（SR3 各合约价格）
         +
框架已抓 EFFR（当前政策利率水平，曲线起点锚）
         ↓
程序计算 implied curve + 路径特征
         ↓
进 ABCD 报告（与 2s10s/cooling 并列）
```

CSV 是输入数据源，不嵌公式。所有计算在框架 Python 里，和其他指标一致。

---

## 1. CSV 格式（已建好）

```
date, SR3M2026, SR3N2026, SR3Q2026, SR3U2026, SR3V2026, SR3X2026, SR3Z2026, SR3H2027, SR3M2027, SR3U2027, note
# 月份, Jun 2026, Jul 2026, ..., Sep 2027, （注释行，读取时跳过 # 开头的行）
2026-06-22, , , , ... , 
```

- 第 1 行表头，第 2 行 `#` 开头是月份注释（读取时 skip）；
- 各 SR3 列 = 合约**价格**（96.xx 形式），用户从 TradingView 抄；
- 列对应的到期月份从合约代码解析：M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec, H=Mar（月份代码表见 §5）；
- 近端月度（2026 全月）+ 远端季月（2027 H/M/U），**合约间隔不均匀**，计算时按实际月份对齐，不按"第几个合约"。

---

## 2. 核心计算

```python
# 每个合约: 隐含 SOFR = 100 - 价格
implied_sofr[contract] = 100.0 - price[contract]

# 曲线起点锚: 当前 EFFR（框架已抓）
# 注意 SOFR vs EFFR 有小基差(通常几bp), 看路径方向可忽略;
# 先用固定基差常量, 具名, 以后可调
SOFR_EFFR_BASIS = 0.0   # bp, 起点设0, 标定后调整
anchor = effr_current + SOFR_EFFR_BASIS   # 曲线当前水平

# 曲线 = anchor → 各合约 implied_sofr 按到期月排列的路径
```

## 3. 路径特征提取（进报告的三个数）

```python
# 特征1: 隐含终点 (terminal) = 曲线最低点对应的隐含利率
#        = 市场认为这轮降到哪停
terminal_rate = min(implied_sofr.values())
terminal_month = 对应最低点的合约月份

# 特征2: 首降时点 (first cut) = 第一个明显低于 anchor 的合约月份
#        "明显" = 低于 anchor 至少 FIRST_CUT_THRESH (具名常量)
FIRST_CUT_THRESH = 12.5   # bp, 半次降息(25bp的一半)作为"开始定价降息"门槛, 可调
for contract in 按到期月排序:
    if anchor - implied_sofr[contract] >= FIRST_CUT_THRESH:
        first_cut_month = contract 的月份
        break
else:
    first_cut_month = None   # 曲线未 price in 降息

# 特征3: 未来N月累计降息bp = anchor - 某个远月合约的隐含利率
#        用一个固定锚点合约(如 12个月后)
cumulative_cut_12m = anchor - implied_sofr[约12个月后的合约]   # bp
```

## 4. 平滑与防抖（关键 — 路径精度高=单日易抖）

SR3 价格单日波动会让"首降时点"在相邻月份间跳。**直接报当日值没信息，必须平滑 + 报变化方向**（和 2s10s 同款纪律）：

```python
# 对每个特征做 5日均值, 并报 vs 5日前的变化
terminal_5d_avg = mean(terminal_rate[t-4 ... t])
terminal_chg = terminal_rate[t] - terminal_rate[t-5]   # 方向

# 首降时点: 报 5日内是否稳定, 单日跳变要标"未稳定"
# 如 5日内 first_cut_month 在 Sep/Oct 间跳 → 报 "Sep-Oct(未稳定)"
```

报告输出带平滑值 + 方向，不报裸当日值。

## 5. 月份代码表（解析合约到期月）

```python
MONTH_CODE = {'F':1,'G':2,'H':3,'J':4,'K':5,'M':6,'N':7,'Q':8,'U':9,'V':10,'X':11,'Z':12}
# SR3M2026 → M=6月, 2026 → 到期 2026-06
# 用到期月计算"距今几个月", 累计降息/斜率按实际月份间隔算, 不按列序号
```

## 6. 缺数据处理（系统铁律 — 缺数据要可见，不能伪装）

```python
# 情况1: 某天整行空(用户忘填) → 当天 SOFR 曲线"未更新", 报告标 ⚠️,
#        绝不拿昨天的值硬算当今天 (同 Mortgage stale / VTS N/A 逻辑)
if 整行价格都空:
    输出 "SOFR曲线: 数据未更新(last: YYYY-MM-DD)"

# 情况2: 个别合约空(某远月 TradingView 没有/用户漏填) →
#        该合约不参与曲线, 但其余照算; 若影响特定特征(如终点恰好在缺的那个月)
#        → 该特征标"低置信"
if 个别合约空:
    跳过该合约, 用其余点; 受影响特征标低置信

# 情况3: 价格明显异常(如填错小数点, 90 填成 9.0) →
#        加合理性检查: SR3 价格应在 ~95-99 区间(对应利率 1-5%),
#        超出 → 报错提示用户检查, 不静默用错值
if not (94 <= price <= 100):
    报错 "SR3价格 {contract}={price} 超出合理区间, 请检查"

# 情况4: EFFR 缺失(框架那边没抓到) → anchor 无法确定 →
#        整个曲线无法算 → 标"缺EFFR锚, 无法计算"
```

## 7. 报告输出格式（加在 ① 利率路径区，与 DGS2−IORB / 2s10s 并列）

```
| SOFR路径 | 隐含终点=X.XX% (5d X.XX%, Δ±Xbp) | 首降≈{月份} | 12m累计降息≈Xbp | [解读] |
```

解读串（conditioned on 特征，不写死）：
- 终点远低于当前 + 首降近 → "市场price in较快降息路径"
- 终点接近当前 + 首降远/无 → "市场price in按兵不动/慢降"
- 终点上升(Δ正) → "降息预期降温"
- 数据未更新 → "SOFR数据未更新(last: ...)"

## 8. 与现有指标的关系（避免重复 + 交叉验证）

- **不是又一个降息方向信号**（DGS2−IORB 已给方向）；SOFR 的增量是**精确路径**（降到哪、几月、多少）；
- **可与 DGS2−IORB / cooling 做交叉验证**：若 SOFR 首降时点临近 + cooling 仍 0/3，是背离信号——市场 price in 降息但真实利率还没退潮，值得标注；
- **触发联动**：SOFR 隐含的首降时点，可作为 TLT 触发条件（cooling + DFII10破2%）的**前瞻补充**——市场 price in 降息提前，可能预示 cooling 将启动。

## 9. 标定（上线后做，非阻塞）

FIRST_CUT_THRESH(12.5bp)、SOFR_EFFR_BASIS(0)、12m锚点合约 都是起点值。上线积累数据后：
- 用历史回算 SOFR-EFFR 实际基差，调 SOFR_EFFR_BASIS；
- 看"首降时点"的单日稳定性，定平滑窗口；
- 和实际 FOMC 降息对照，验证"首降时点"的预测有效性（正向验证）。

---

## 附：与你手动流程的衔接

1. 你每天从 TradingView 抄 SR3 价格 → 填 sofr_sr3.csv（10 个合约）；
2. 框架管线读这个 CSV（多一个本地数据源，像读 FRED）；
3. 用 EFFR 当锚 + SR3 价格算曲线 → 三个特征进报告；
4. 忘填某天 → 报告标"SOFR 数据未更新"（不静默用旧值）。

*规格版本 v1 · 数据源 sofr_sr3.csv(手动) + EFFR(框架已抓) · 输出路径精度特征*
