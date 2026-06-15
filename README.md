# v3.5 ABCD 流动性框架 — 整理文件夹

> 下次打开这个文件夹跟我说 `"看 v3.5/ 文件夹"`，我就知道你是来找 US/全球流动性框架的。

---

## 文件夹结构

```
v3.5/
├── README.md                    # 本文件
├── paper_trade_协议.md           # 30 天 Paper Trade 协议（2026-05-27 → 06-26）
├── task1-5_证伪结论.md           # task1–5 证伪审计结论汇总
├── run_daily.py                 # 🚀 一键工作流编排（推荐入口）
├── fetch_yahoo_local.py         # Step 1: 本地 Yahoo 数据（FXY/HYG/SPY）
├── fetch_data.py                # Step 2: FRED + Yahoo 线上拉取
├── daily_report.py              # Step 3: 诊断简报 + paper_trade
├── requirements.txt             # Python 依赖
├── daily_archive/
│   ├── 2026-05/
│   │   ├── daily_2026-05-25.md
│   │   ├── ...                   # 日更报告
│   │   ├── paper_trade_2026-05-27.md
│   │   └── ...                   # Paper trade（仓位 §0.6 自动推导）
│   └── 2026-06/
│       └── (每日 paper trade 记录)
```

## 核心文件（工作区根目录）

| 文件 | 作用 |
|------|------|
| `ABCD_framework_v3.5.md` | **框架规范**（v3.5 权威文档） |
| `liquidity-dashboard/data/series.json` | **数据文件**（FRED + Yahoo，py 脚本读写） |
| `liquidity-dashboard/report/daily_*.md` | **日更报告**（daily_report.py 输出） |

## 无关文件（别混入）

- `A股/` — A 股 v0.4.1 框架，完全独立，不交叉
- `liquidity-dashboard/v0.4.1_空跑期协议.md` — A 股空跑协议

---

## 日更工作流

### 🚀 一键运行（推荐）

```bash
python v3.5/run_daily.py
```

自动按顺序执行：

```
Step 1: fetch_yahoo_local.py    → yahoo_series.json      (本地 Yahoo)
   ↓
Step 2: fetch_data.py           → series.json            (FRED + 线上 Yahoo，fallback 到 step1)
   ↓
Step 3: daily_report.py --md    → daily_*.md + paper_trade_*.md
```

### 分解命令（手动分步）

```bash
# Step 1: 本地 Yahoo 数据（必须在 Step 2 之前）
python v3.5/fetch_yahoo_local.py

# Step 2: FRED + 线上 Yahoo（需要 FRED_API_KEY 环境变量）
python v3.5/fetch_data.py

# Step 3: 出报告
python v3.5/daily_report.py --md
```

| 输出 | 位置 |
|------|------|
| 诊断简报 | `liquidity-dashboard/report/daily_YYYY-MM-DD.md` |
| 交易日志 | `v3.5/daily_archive/YYYY-MM/paper_trade_YYYY-MM-DD.md` |

> **paper_trade 仓位**不再是手工填写——`compute_position()` 按 §0.6 第一层→第七层机械化推导，Step-by-step 审计链可见。

---

*创建: 2026-05-29 | 框架: ABCD v3.5*
