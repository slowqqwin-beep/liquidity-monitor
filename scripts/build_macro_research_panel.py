#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立回测研究模块 — HY OAS 与 FRED 利率序列对齐面板
====================================================

输入:
  - BAMLH0A0HYM2_master_clean_for_backtest.csv  (唯一日频回测 HY OAS 输入)
  - FRED 利率序列: DGS10, DFII10, T10YIE, DGS2, EFFR, DFEDTARU

输出:
  - data/macro_db/processed/macro_research_panel.csv

约束:
  - 不 forward-fill / back-fill / 插值 HY OAS
  - SVB period (2023-03-06~2023-04-20): deliberate GAP — FRED BAMLH0A0HYM2 observation_start=2023-06-19; no reliable source pre-seam. Not interpolated.
  - 变动率基于观测行数 (observation-based), 非自然日历日
  - 不修改 dashboard / Risk OS / run_all.py

输出面板使用口径:
  - 本面板是宏观研究主表，不是 HY OAS 全覆盖日历
  - HY OAS 仅 7,560 个有效观测 (32.1%)，做依赖 HY OAS 的回测时必须过滤 HY_OAS_available == True
  - HY_OAS_chg_5d / chg_20d 是 observation-based changes (dropna→diff→reindex)
    跨 SVB gap 时跳过缺失日期，不适合解释为"过去一周/一月变化"
  - 不要把 HY OAS 缺失当成"信用稳定"，缺数据必须作为单独状态处理
"""

import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# 1. 加载 HY OAS (clean for backtest — 唯一日频回测输入)
# ============================================================
hy_path = (
    PROJECT_ROOT / "data" / "macro_db" / "processed"
    / "BAMLH0A0HYM2_master_clean_for_backtest.csv"
)
hy_raw = pd.read_csv(hy_path)
hy_raw["date"] = pd.to_datetime(hy_raw["date"])
hy = hy_raw[["date", "value"]].rename(columns={"value": "BAMLH0A0HYM2"})
hy = hy.set_index("date").sort_index()
# 仅交易日有值，无填充。

print(f"[1/6] HY OAS loaded: {len(hy):,} rows, {hy.index.min().date()} ~ {hy.index.max().date()}")

# ============================================================
# 2. 加载 FRED 利率序列
# ============================================================
fred_dir = PROJECT_ROOT / "data" / "历史数据"

FRED_SERIES = {
    "DGS10":     "DGS10.csv",
    "DFII10":    "DFII10.csv",
    "T10YIE":    "T10YIE.csv",
    "DGS2":      "DGS2.csv",
    "EFFR":      "EFFR.csv",
    "DFEDTARU":  "DFEDTARU.csv",
}

fred_dfs = {}
for name, fname in FRED_SERIES.items():
    fp = fred_dir / fname
    df = pd.read_csv(fp)
    date_col = df.columns[0]  # observation_date
    val_col = df.columns[1]   # series value column
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.rename(columns={date_col: "date", val_col: name})
    df = df.set_index("date").sort_index()
    df[name] = pd.to_numeric(df[name], errors="coerce")
    fred_dfs[name] = df
    n_valid = df[name].notna().sum()
    print(f"[2/6] {name}: {len(df):,} rows, {n_valid:,} valid, "
          f"{df.index.min().date()} ~ {df.index.max().date()}")

# ============================================================
# 3. 合并为统一面板 (outer join, 保留所有日历日)
# ============================================================
panel = pd.DataFrame(
    index=pd.date_range("1962-01-02", pd.Timestamp.now().date(), freq="D")
)

for name, df in fred_dfs.items():
    panel[name] = df[name]

panel["BAMLH0A0HYM2"] = hy["BAMLH0A0HYM2"]

print(f"[3/6] Merged panel: {len(panel):,} rows, {panel.index.min().date()} ~ {panel.index.max().date()}")

# ============================================================
# 4. 派生字段
# ============================================================

# --- 4a. HY_OAS_available ---
panel["HY_OAS_available"] = panel["BAMLH0A0HYM2"].notna()

# --- 4b. 实际利率 / 利差 ---
panel["real_yield_nowcast"]   = panel["DGS10"] - panel["T10YIE"]
panel["real_yield_basis_diff"] = panel["real_yield_nowcast"] - panel["DFII10"]
panel["curve_2s10s"]          = panel["DGS10"] - panel["DGS2"]

# --- 4c. SVB gap 标记 ---
SVB_START = pd.Timestamp("2023-03-06")
SVB_END   = pd.Timestamp("2023-04-20")
svb_mask  = (panel.index >= SVB_START) & (panel.index <= SVB_END)

# credit_signal_status: unavailable (SVB gap) / available (有值) / "" (非 SVB 的周末/假日)
panel["credit_signal_status"] = ""
panel.loc[panel["HY_OAS_available"], "credit_signal_status"] = "available"
panel.loc[svb_mask & ~panel["HY_OAS_available"], "credit_signal_status"] = "unavailable"

# credit_signal_reason: 仅 SVB gap 填充
panel["credit_signal_reason"] = ""
panel.loc[svb_mask & ~panel["HY_OAS_available"], "credit_signal_reason"] = "HY_OAS_missing_svb_gap"

svb_unavailable = svb_mask & ~panel["HY_OAS_available"]
print(f"[4/6] SVB gap (2023-03-06 ~ 2023-04-20): {svb_unavailable.sum()} days marked unavailable")

# ============================================================
# 5. 变动率计算 (观测行数差异, 非自然日差异)
#    规则: 只对非空序列做 diff, 再 reindex 回原日历。
#    这样周末/假日/断档不会稀释真正的 N-observation 变动。
# ============================================================

def _obs_diff(series: pd.Series, n: int) -> pd.Series:
    """Compute N-observation difference, preserving NaN alignment.

    Example: diff(5) on a trading-day-only series means 'vs 5 trading days ago',
    not 'vs 5 calendar days ago'.
    """
    non_null = series.dropna()
    if len(non_null) <= n:
        return pd.Series(np.nan, index=series.index)
    diffs = non_null.diff(n)
    result = pd.Series(np.nan, index=series.index, dtype=float)
    result.loc[diffs.index] = diffs
    return result


CHG_CONFIG = {
    "BAMLH0A0HYM2": ("HY_OAS_chg_5d", "HY_OAS_chg_20d"),
    "DGS10":        ("DGS10_chg_5d", "DGS10_chg_20d"),
    "DFII10":       ("DFII10_chg_5d", "DFII10_chg_20d"),
    "T10YIE":       ("T10YIE_chg_5d", "T10YIE_chg_20d"),
    "EFFR":         ("EFFR_chg_5d", "EFFR_chg_20d"),
    "DFEDTARU":     ("DFEDTARU_chg_5d", "DFEDTARU_chg_20d"),
    "DGS2":         ("DGS2_chg_5d", "DGS2_chg_20d"),
}

for src, (c5, c20) in CHG_CONFIG.items():
    panel[c5]  = _obs_diff(panel[src], 5)
    panel[c20] = _obs_diff(panel[src], 20)

print(f"[5/6] Change columns computed (observation-based diff)")

# ============================================================
# 6. 输出
# ============================================================

# 列顺序: date 第一列 (从 index 还原), 然后是核心字段, 变动率, 派生字段
OUTPUT_COLS = [
    "BAMLH0A0HYM2",
    "HY_OAS_available",
    "DGS10",
    "DFII10",
    "T10YIE",
    "DGS2",
    "EFFR",
    "DFEDTARU",
    "HY_OAS_chg_5d",
    "HY_OAS_chg_20d",
    "DGS10_chg_5d",
    "DGS10_chg_20d",
    "DFII10_chg_5d",
    "DFII10_chg_20d",
    "T10YIE_chg_5d",
    "T10YIE_chg_20d",
    "real_yield_nowcast",
    "real_yield_basis_diff",
    "curve_2s10s",
    "credit_signal_status",
    "credit_signal_reason",
]

out_path = PROJECT_ROOT / "data" / "macro_db" / "processed" / "macro_research_panel.csv"
panel_out = panel[OUTPUT_COLS].copy()
panel_out.index.name = "date"
panel_out.to_csv(out_path, float_format="%.4f")

# ============================================================
# 7. QC 摘要
# ============================================================
print(f"\n[6/6] Output: {out_path}")
print(f"      {len(panel_out):,} rows × {len(panel_out.columns)} columns")
print()

# 覆盖率统计
for col in ["BAMLH0A0HYM2", "DGS10", "DFII10", "T10YIE", "DGS2", "EFFR", "DFEDTARU"]:
    n = panel_out[col].notna().sum()
    pct = n / len(panel_out) * 100
    print(f"  {col:>14s}: {n:>7,} / {len(panel_out):,} ({pct:.1f}%)")

print(f"\n  HY_OAS_available=True:  {panel_out['HY_OAS_available'].sum():,}")
print(f"  credit_signal_status=unavailable: {(panel_out['credit_signal_status'] == 'unavailable').sum()}")
print(f"  credit_signal_status=available:   {(panel_out['credit_signal_status'] == 'available').sum()}")

# 变动率有效行数
for col in ["HY_OAS_chg_5d", "HY_OAS_chg_20d"]:
    n = panel_out[col].notna().sum()
    print(f"  {col}: {n:,} valid observations")

# 尾部预览
print(f"\n--- Tail (last 10 rows with any non-null) ---")
tail = panel_out.dropna(how="all").tail(10)
print(tail.to_string())
