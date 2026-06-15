# Pipeline v1.0 — 日报 & 风险流程图生成管线

归档日期：2026-06-10

## 快速开始

```powershell
# 一键生成日报+风险看板+风险流程图
cd D:\liquidity-dashboard\v3.5
uv run python -X utf8 daily_report.py --md

# 完整抓数+报告
cd D:\liquidity-dashboard
uv run python v3.5/run_daily.py
```

## 输出

| 产物 | 路径 |
|------|------|
| 日报 | `../liquidity-dashboard/report/daily_{date}.md` |
| 风险看板 MD | `../liquidity-dashboard/report/risk_dashboard_{date}.md` |
| 风险看板 PNG | `../liquidity-dashboard/report/risk_dashboard_{date}.png` |
| 风险流程图 HTML | `daily_archive/{YYYY-MM}/risk_flowchart_{date}.html` |

## 环境要求

```powershell
uv add -r requirements.txt
```
环境变量：`FRED_API_KEY`

## 文件清单 (7 个)

1. `daily_report.py` — 核心引擎 (~2900 行)
2. `generate_risk_dashboard.py` — 风险看板 MD+PNG (~560 行)
3. `generate_risk_flowchart.py` — 风险演化流程图 HTML v4 (~680 行)
4. `run_daily.py` — 编排器 (~90 行)
5. `fetch_data.py` — FRED + Yahoo + CoinGecko 数据抓取 (~530 行)
6. `fetch_yahoo_local.py` — 本地 Yahoo 缓存 (~100 行)
7. `requirements.txt` — 依赖清单
