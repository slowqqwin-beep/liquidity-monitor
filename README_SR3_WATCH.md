# Standalone SR3 Repair Watch Dashboard

这是独立的 SR3 Repair Watch 页面，属于 Research-Only，不构成交易指令，不接入 Risk OS，不接入旧 dashboard，不接入 run_all.py，不影响仓位。

## 页面路径

```text
docs/sr3-watch/index.html
```

GitHub Pages 访问路径：

```text
https://<username>.github.io/<repo>/sr3-watch/
```

## 数据输入

### 1. SR3 Repair Watch 报告

根目录放：

```text
sr3_repair_watch_latest.md
```

构建脚本会复制到：

```text
docs/sr3-watch/data/sr3_repair_watch_latest.md
```

并解析生成：

```text
docs/sr3-watch/data/sr3_repair_watch_latest.json
```

### 2. Z26-H27-M27 远期曲线

根目录放 TradingView 导出的 CSV，例如：

```text
100-CME_DL_SR3H2027, 1D.csv
```

页面会显示从 `2026-06-16` 开始的每日三点远期曲线比较：

```text
Z26 = Dec-26
H27 = Mar-27
M27 = Jun-27
```

如果 CSV 是 `100-SR3` 格式，数值已经是隐含利率。  
如果 CSV 是普通 `SR3` 价格格式，则脚本自动转换：

```text
implied_rate = 100 - price
```

## 本地构建

```bash
python scripts/build_sr3_watch_dashboard.py
```

然后打开：

```text
docs/sr3-watch/index.html
```

## 自动推送

新增独立 workflow：

```text
.github/workflows/sr3-watch-dashboard.yml
```

默认工作日每天 UTC 23:30 运行，也支持手动触发。

它只提交：

```text
docs/sr3-watch
scripts/build_sr3_watch_dashboard.py
.github/workflows/sr3-watch-dashboard.yml
```

不会修改旧 dashboard，也不会接入 Risk OS。

## 关键边界

- Research-Only
- Deceleration ≠ buy signal
- mixed_repair 不是买入信号
- 不接 Risk OS
- 不接 run_all.py
- 不影响仓位


## 2s10s 曲线结构模块

网页不再显示“约束确认”卡片模块，改为显示：

```text
2s10s 曲线结构
```

每天可从 TradingView 下载 2s10s CSV 放到仓库根目录，推荐命名：

```text
2s10s.csv
```

也支持：

```text
US10Y-US02Y, 1D.csv
TVC_US10Y-US02Y, 1D.csv
tradingview_2s10s.csv
```

支持两种格式：

1. 只有 spread close：
   - `time`
   - `close`
   - 文件名包含 `2s10s` 或 `US10Y-US02Y`
2. 同时有 10Y / 2Y close：
   - `time`
   - `US10Y ... close`
   - `US02Y ... close`

如果只有 spread，页面判断变陡/变平。  
如果同时有 10Y 和 2Y，页面进一步判断：

```text
熊平 / 熊陡 / 牛平 / 牛陡
```


## 当前事件修复起始日

为避免 FOMC / 沃什事件后的新波动被旧 formal shock 起点污染，页面现在区分两类修复日期：

```text
当前事件修复起始日
原报告修复起始日
```

算法：

```text
1. 从 2026-06-16 起读取 Z26-H27-M27 每日曲线。
2. 计算三合约平均隐含利率。
3. 找到事件窗口内最高点，作为当前事件峰值。
4. 峰值之后第一天平均隐含利率回落，即当前事件修复起始日。
```

示例：

```text
当前事件峰值：2026-06-22
当前事件修复起始日：2026-06-23
```

注意：当前事件修复启动不等于 level repair，也不等于买入信号。


## Price-over / Hike-over 口径

当前版本将 FOMC/沃什后的 SR3 上冲定义为：

```text
price-over / hike-over
```

而不是简单的 `price-out cuts`。

含义：

```text
不是市场只把降息预期抹掉；
而是曲线被推到更高利率路径，等价于加息风险 / higher-for-longer premium 被重新计入。
```

Dashboard 显示：

```text
事件前基准日：通常为 2026-06-16
Hike-over 峰值日：当前事件窗口内 Z26-H27-M27 平均隐含利率最高日
当前修复起始日：峰值后第一天下修
Hike-over 冲击：峰值相对事件前基准的上修幅度
已修复幅度：峰值到最新值的回落幅度
修复比例：已修复幅度 / Hike-over 冲击
距离基准仍高：最新值相对事件前基准仍高多少 bp
Avg level repair：三合约平均是否回到基准 + tolerance
Strict level repair：Z26/H27/M27 是否全部回到各自基准 + tolerance
```

注意：

```text
当前修复起始日 ≠ level repair
修复比例提升 ≠ 买入信号
只有回到事件前基准附近，才是 event level repair
```


## 顶部四问卡片口径修正

顶部四问卡片不再展示原报告的 `deceleration_since = 2026-05-26`。

原因：

```text
2026-05-26 属于旧 formal shock / 原报告窗口的 deceleration 起点。
当前页面主要判断 FOMC/沃什后的 current event。
```

现在顶部卡片使用：

```text
当前事件仍在 hike-over impulse？
当前事件修复启动？
发生 event level repair？
修复分类
```

其中：

```text
当前事件修复启动 = 当前事件峰值后第一天下修
event level repair = 曲线回到 2026-06-16 事件前基准附近
```
