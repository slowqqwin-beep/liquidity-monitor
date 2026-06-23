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
