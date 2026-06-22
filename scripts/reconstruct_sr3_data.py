#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重建 sr3_long.csv 和 sr3_curve_features.csv
============================================
从 84 个合约日线 CSV 重组为长表和每日曲线特征。

输入: data/历史数据/SR3截止20260617/SR3_{code}_day.csv
输出:
  data/macro_backtest/input/sr3_long.csv          — 84 合约长表
  data/macro_backtest/input/sr3_curve_features.csv — 每日曲线特征
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "历史数据" / "SR3截止20260617"
OUT_DIR = PROJECT_ROOT / "data" / "macro_backtest" / "input"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- 月份代码解析 ----
MONTH_CODE = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
MONTH_NAME = {v: k for k, v in {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}.items()}


def parse_contract(code: str) -> tuple:
    """SR3_M25 → (contract_code, maturity_year, maturity_month)"""
    # SR3_M25 → month_char='M', year_suffix='25'
    month_char = code.replace("SR3_", "")
    month_num = MONTH_CODE[month_char[0]]
    year_suffix = int(month_char[1:])
    year = 2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix
    return code, year, month_num


# ============================================================
# 1. 构建 sr3_long.csv
# ============================================================
print("[1/3] Building sr3_long.csv from 84 contract CSVs...")

contract_files = sorted(RAW_DIR.glob("SR3_*_day.csv"))
rows = []

for fp in contract_files:
    code = fp.stem.replace("_day", "")  # SR3_M25
    _, year, month = parse_contract(code)
    maturity = datetime(year, month, 1)

    df = pd.read_csv(fp)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.rename(columns={
        "datetime": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "position": "position",
    })
    # 只保留有成交量的行（剔除纯 listing 无交易行）
    df = df[df["close"] > 0].copy()
    df["contract"] = code
    df["maturity"] = maturity
    df["maturity_year"] = year
    df["maturity_month"] = month
    df["implied_rate"] = 100.0 - df["close"]

    rows.append(df)

long_df = pd.concat(rows, ignore_index=True)
long_df = long_df.sort_values(["date", "maturity"]).reset_index(drop=True)

# 列顺序
LONG_COLS = [
    "date", "contract", "maturity", "maturity_year", "maturity_month",
    "open", "high", "low", "close", "implied_rate", "volume", "position",
]
long_df = long_df[LONG_COLS]

long_path = OUT_DIR / "sr3_long.csv"
long_df.to_csv(long_path, index=False)

n_contracts = long_df["contract"].nunique()
n_rows = len(long_df)
n_dates = long_df["date"].nunique()
dt_min, dt_max = long_df["date"].min(), long_df["date"].max()
print(f"  → {n_rows:,} rows, {n_dates:,} trading days, "
      f"{n_contracts} contracts, {dt_min.date()} ~ {dt_max.date()}")

# QC: check for 0 gaps, 0 anomalies
gaps = long_df.groupby("date")["contract"].count()
print(f"  QC: contracts/day min={gaps.min()}, max={gaps.max()}, median={gaps.median():.0f}")

# ============================================================
# 2. 构建 sr3_curve_features.csv
# ============================================================
print("[2/3] Computing daily curve features...")

features = []

for date, grp in long_df.groupby("date"):
    # 按到期月排序
    grp = grp.sort_values("maturity")

    rates = grp["implied_rate"].values
    contracts = grp["contract"].values
    maturities = grp["maturity"].values
    n = len(rates)

    # 基础特征
    near_rate = rates[0] if n > 0 else np.nan
    near_contract = contracts[0] if n > 0 else ""
    far_rate = rates[-1] if n > 0 else np.nan
    far_contract = contracts[-1] if n > 0 else ""

    # 隐含终点 = 曲线最低点（在有效区间内：前2/3的合约，排除远端低流动性噪音）
    valid_cutoff = max(1, int(n * 2 / 3))
    valid_rates = rates[:valid_cutoff]
    valid_contracts = contracts[:valid_cutoff]
    valid_maturities = maturities[:valid_cutoff]

    terminal_idx = np.argmin(valid_rates) if len(valid_rates) > 0 else 0
    terminal_rate = valid_rates[terminal_idx]
    terminal_contract = valid_contracts[terminal_idx]
    terminal_maturity = valid_maturities[terminal_idx]

    # 峰值：曲线最高点
    peak_idx = np.argmax(valid_rates) if len(valid_rates) > 0 else 0
    peak_rate = valid_rates[peak_idx]
    peak_contract = valid_contracts[peak_idx]
    peak_maturity = valid_maturities[peak_idx]

    # 曲线斜率: far - near
    curve_slope_bp = (far_rate - near_rate) * 100 if (n > 1 and not np.isnan(far_rate) and not np.isnan(near_rate)) else np.nan

    # 曲线中段 (前后各去掉 20%)
    mid_start = max(0, int(n * 0.2))
    mid_end = min(n, int(n * 0.8))
    mid_rates = rates[mid_start:mid_end]
    mid_mean = np.mean(mid_rates) if len(mid_rates) > 0 else np.nan

    # Z6-M7 段 (Dec-26 到 Jun-27)：关键观察段
    z6_mask = grp["contract"].str.match(r"SR3_Z26")
    m7_mask = grp["contract"].str.match(r"SR3_M27")
    z6_rate = grp.loc[z6_mask, "implied_rate"].values
    m7_rate = grp.loc[m7_mask, "implied_rate"].values
    z6_val = float(z6_rate[0]) if len(z6_rate) > 0 else np.nan
    m7_val = float(m7_rate[0]) if len(m7_rate) > 0 else np.nan

    features.append({
        "date": date,
        "n_contracts": n,
        "near_rate": near_rate,
        "near_contract": near_contract,
        "far_rate": far_rate,
        "far_contract": far_contract,
        "terminal_rate": terminal_rate,
        "terminal_contract": terminal_contract,
        "terminal_maturity": pd.Timestamp(terminal_maturity),
        "peak_rate": peak_rate,
        "peak_contract": peak_contract,
        "peak_maturity": pd.Timestamp(peak_maturity),
        "curve_slope_bp": curve_slope_bp,
        "mid_mean_rate": mid_mean,
        "z6_rate": z6_val,
        "m7_rate": m7_val,
    })

feat_df = pd.DataFrame(features).sort_values("date").reset_index(drop=True)

# 日变化量
feat_df["near_rate_chg"] = feat_df["near_rate"].diff()
feat_df["far_rate_chg"] = feat_df["far_rate"].diff()
feat_df["terminal_rate_chg"] = feat_df["terminal_rate"].diff()
feat_df["peak_rate_chg"] = feat_df["peak_rate"].diff()
feat_df["mid_mean_chg"] = feat_df["mid_mean_rate"].diff()
feat_df["z6_m7_spread"] = feat_df["z6_rate"] - feat_df["m7_rate"]

# 曲线整体移动幅度 (平均近月变化 + 远月变化 / 2，bp)
feat_df["curve_move_bp"] = (
    (feat_df["near_rate_chg"] + feat_df["far_rate_chg"]) / 2.0 * 100
)

# 曲线移动的滚动标准差 (用于判断钝化)
feat_df["curve_move_5d_vol"] = feat_df["curve_move_bp"].rolling(5).std()
feat_df["curve_move_20d_vol"] = feat_df["curve_move_bp"].rolling(20).std()

# 5d/20d 累计移动
feat_df["curve_move_5d_sum"] = feat_df["curve_move_bp"].rolling(5).sum()
feat_df["curve_move_20d_sum"] = feat_df["curve_move_bp"].rolling(20).sum()

feat_path = OUT_DIR / "sr3_curve_features.csv"
feat_df.to_csv(feat_path, index=False, float_format="%.6f")

print(f"  → {len(feat_df):,} days, {len(feat_df.columns)} features")
print(f"  Date range: {feat_df['date'].min().date()} ~ {feat_df['date'].max().date()}")
print(f"  curve_move_bp mean={feat_df['curve_move_bp'].mean():.2f}, "
      f"std={feat_df['curve_move_bp'].std():.2f}")

# ============================================================
# 3. QC 摘要
# ============================================================
print(f"\n[3/3] QC Summary")
print(f"  sr3_long.csv:     {long_path} ({n_rows:,} rows)")
print(f"  sr3_curve_features.csv: {feat_path} ({len(feat_df):,} rows)")
print(f"  Contracts: {n_contracts}")
print(f"  Date range: {dt_min.date()} ~ {dt_max.date()}")

# 检查是否有缺失交易日（节假日除外）
all_dates = pd.date_range(dt_min, dt_max, freq="B")  # business days only
data_dates = set(long_df["date"].dt.date)
missing_bdays = [d.date() for d in all_dates if d.date() not in data_dates]
if missing_bdays:
    print(f"  Missing business days: {len(missing_bdays)} (holidays expected)")
else:
    print(f"  No missing business days ✓")

# Near rate sample
print(f"\n  Near rate range: {feat_df['near_rate'].min():.2f}% ~ {feat_df['near_rate'].max():.2f}%")
print(f"  Near rate last 5 days:")
print(feat_df[["date", "near_rate", "curve_move_bp", "near_rate_chg"]].tail(5).to_string(index=False))
