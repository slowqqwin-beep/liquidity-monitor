#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 sofr_sr3.csv（10 合约手工更新）追加新日期到 sr3_long.csv 和 sr3_curve_features.csv
====================================================================================
用法: uv run python scripts/append_sr3_daily.py

输入: data/sofr_sr3.csv (用户每日手工更新 10 个关键合约收盘价)
      data/macro_backtest/input/sr3_long.csv (现有 84 合约长表)
      data/macro_backtest/input/sr3_curve_features.csv (现有曲线特征)

输出: 追加新日期的行到以上两个 CSV（幂等——已存在的日期不会重复追加）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOFR_SR3_PATH = PROJECT_ROOT / "data" / "sofr_sr3.csv"
LONG_PATH = PROJECT_ROOT / "data" / "macro_backtest" / "input" / "sr3_long.csv"
FEAT_PATH = PROJECT_ROOT / "data" / "macro_backtest" / "input" / "sr3_curve_features.csv"

# 10 合约 → (contract_code, year, month) 映射
CONTRACT_MAP = {
    "SR3M2026": ("SR3_M26", 2026, 6),
    "SR3N2026": ("SR3_N26", 2026, 7),
    "SR3Q2026": ("SR3_Q26", 2026, 8),
    "SR3U2026": ("SR3_U26", 2026, 9),
    "SR3V2026": ("SR3_V26", 2026, 10),
    "SR3X2026": ("SR3_X26", 2026, 11),
    "SR3Z2026": ("SR3_Z26", 2026, 12),
    "SR3H2027": ("SR3_H27", 2027, 3),
    "SR3M2027": ("SR3_M27", 2027, 6),
    "SR3U2027": ("SR3_U27", 2027, 9),
}


def read_sofr_sr3() -> pd.DataFrame:
    """Read sofr_sr3.csv, return DataFrame with date + 10 contract prices.
    
    CSV format (13 columns, trailing comma creates extra empty col):
      col 0: date, col 1-10: 10 contract prices, col 11: note, col 12: trailing empty
    """
    # Use usecols to read exactly 12 columns (skip trailing empty col 12)
    column_names = ["date"] + list(CONTRACT_MAP.keys()) + ["note"]
    raw = pd.read_csv(SOFR_SR3_PATH, skiprows=2, header=None,
                      names=column_names, usecols=range(12), dtype=str)

    # Parse dates
    raw["_date"] = pd.to_datetime(raw["date"], errors="coerce")

    # Drop rows without valid date
    valid = raw[raw["_date"].notna()].copy()
    valid = valid.set_index("_date")

    # Parse prices (10 contract columns)
    price_cols = list(CONTRACT_MAP.keys())
    for c in price_cols:
        valid[c] = pd.to_numeric(valid[c].str.strip(), errors="coerce")

    # Keep only rows where at least 5 of 10 contracts have prices
    valid["_n_prices"] = valid[price_cols].notna().sum(axis=1)
    valid = valid[valid["_n_prices"] >= 5].copy()

    if len(valid) == 0:
        print("[WARN] sofr_sr3.csv has no valid price rows.")
        return pd.DataFrame()

    # Pivot to long format
    records = []
    for dt, row in valid.iterrows():
        for col in price_cols:
            price = row[col]
            if pd.notna(price) and price > 0:
                code, year, month = CONTRACT_MAP[col]
                records.append({
                    "date": dt,
                    "contract": code,
                    "maturity": datetime(year, month, 1),
                    "maturity_year": year,
                    "maturity_month": month,
                    "close": price,
                    "implied_rate": 100.0 - price,
                })

    return pd.DataFrame(records).sort_values(["date", "maturity"]).reset_index(drop=True)


def compute_curve_features(grp: pd.DataFrame) -> dict:
    """Compute curve features from a single date's contract rows (sorted by maturity)."""
    grp = grp.sort_values("maturity")
    rates = grp["implied_rate"].values
    contracts = grp["contract"].values
    maturities = grp["maturity"].values
    n = len(rates)

    near_rate = rates[0]
    near_contract = contracts[0]
    far_rate = rates[-1]
    far_contract = contracts[-1]

    # 隐含终点 = 曲线最低点（前2/3合约）
    valid_cutoff = max(1, int(n * 2 / 3))
    valid_rates = rates[:valid_cutoff]
    valid_contracts = contracts[:valid_cutoff]
    valid_maturities = maturities[:valid_cutoff]

    terminal_idx = np.argmin(valid_rates)
    terminal_rate = valid_rates[terminal_idx]
    terminal_contract = valid_contracts[terminal_idx]
    terminal_maturity = valid_maturities[terminal_idx]

    peak_idx = np.argmax(valid_rates)
    peak_rate = valid_rates[peak_idx]
    peak_contract = valid_contracts[peak_idx]
    peak_maturity = valid_maturities[peak_idx]

    curve_slope_bp = (far_rate - near_rate) * 100

    mid_start = max(0, int(n * 0.2))
    mid_end = min(n, int(n * 0.8))
    mid_rates = rates[mid_start:mid_end]
    mid_mean = np.mean(mid_rates) if len(mid_rates) > 0 else np.nan

    z6_mask = grp["contract"] == "SR3_Z26"
    m7_mask = grp["contract"] == "SR3_M27"
    z6_val = float(grp.loc[z6_mask, "implied_rate"].values[0]) if z6_mask.any() else np.nan
    m7_val = float(grp.loc[m7_mask, "implied_rate"].values[0]) if m7_mask.any() else np.nan

    return {
        "date": grp["date"].iloc[0],
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
    }


def main():
    print("[Append SR3 Daily] Loading sofr_sr3.csv...")
    new_long = read_sofr_sr3()
    if len(new_long) == 0:
        print("  No new data. Done.")
        return

    new_dates = sorted(new_long["date"].unique())
    print(f"  Found {len(new_dates)} dates in sofr_sr3.csv: "
          f"{new_dates[0].date()} ~ {new_dates[-1].date()}")

    # Load existing long table
    if LONG_PATH.exists():
        existing_long = pd.read_csv(LONG_PATH, parse_dates=["date", "maturity"])
        existing_dates = set(existing_long["date"].dt.date)
    else:
        existing_long = pd.DataFrame()
        existing_dates = set()

    # Filter to truly new dates
    truly_new = new_long[~new_long["date"].dt.date.isin(existing_dates)]
    if len(truly_new) == 0:
        print("  All dates already in sr3_long.csv. Nothing to append.")
        return

    new_dates_only = sorted(truly_new["date"].unique())
    print(f"  New dates to append: {[d.date() for d in new_dates_only]}")

    # ---- 1. Append to sr3_long.csv ----
    long_cols = ["date", "contract", "maturity", "maturity_year", "maturity_month",
                 "open", "high", "low", "close", "implied_rate", "volume", "position"]
    new_long_fmt = truly_new.copy()
    for c in ["open", "high", "low", "volume", "position"]:
        new_long_fmt[c] = np.nan  # sofr_sr3 only has close
    new_long_fmt = new_long_fmt[long_cols]

    updated_long = pd.concat([existing_long, new_long_fmt], ignore_index=True)
    updated_long = updated_long.sort_values(["date", "maturity"]).reset_index(drop=True)
    updated_long.to_csv(LONG_PATH, index=False)
    print(f"  → sr3_long.csv: {len(updated_long):,} rows (+{len(new_long_fmt)})")

    # ---- 2. Compute curve features for new dates ----
    new_features = []
    for dt in new_dates_only:
        grp = truly_new[truly_new["date"] == dt].copy()
        feat = compute_curve_features(grp)
        new_features.append(feat)

    new_feat_df = pd.DataFrame(new_features).sort_values("date").reset_index(drop=True)

    # ---- 3. Append to sr3_curve_features.csv + recompute diffs/rolling ----
    if FEAT_PATH.exists():
        old_feat = pd.read_csv(FEAT_PATH, parse_dates=["date", "terminal_maturity", "peak_maturity"])
    else:
        old_feat = pd.DataFrame()

    combined_feat = pd.concat([old_feat, new_feat_df], ignore_index=True)
    combined_feat = combined_feat.sort_values("date").reset_index(drop=True)
    combined_feat = combined_feat.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    # Recompute derived columns (diffs + rolling) on the full combined series
    combined_feat["near_rate_chg"] = combined_feat["near_rate"].diff()
    combined_feat["far_rate_chg"] = combined_feat["far_rate"].diff()
    combined_feat["terminal_rate_chg"] = combined_feat["terminal_rate"].diff()
    combined_feat["peak_rate_chg"] = combined_feat["peak_rate"].diff()
    combined_feat["mid_mean_chg"] = combined_feat["mid_mean_rate"].diff()
    combined_feat["z6_m7_spread"] = combined_feat["z6_rate"] - combined_feat["m7_rate"]
    combined_feat["curve_move_bp"] = (
        (combined_feat["near_rate_chg"] + combined_feat["far_rate_chg"]) / 2.0 * 100
    )
    combined_feat["curve_move_5d_vol"] = combined_feat["curve_move_bp"].rolling(5).std()
    combined_feat["curve_move_20d_vol"] = combined_feat["curve_move_bp"].rolling(20).std()
    combined_feat["curve_move_5d_sum"] = combined_feat["curve_move_bp"].rolling(5).sum()
    combined_feat["curve_move_20d_sum"] = combined_feat["curve_move_bp"].rolling(20).sum()

    combined_feat.to_csv(FEAT_PATH, index=False, float_format="%.6f")
    print(f"  → sr3_curve_features.csv: {len(combined_feat):,} rows (+{len(new_feat_df)})")

    # Show latest
    latest = combined_feat.iloc[-1]
    print(f"\n  Latest entry:")
    print(f"    date={latest['date'].date()}, near_rate={latest['near_rate']:.4f}%, "
          f"curve_move_bp={latest['curve_move_bp']:.2f}, "
          f"curve_move_5d_sum={latest['curve_move_5d_sum']:.2f}")

    print(f"\nDone. Ready for sr3_repair_watch.py.")


if __name__ == "__main__":
    main()
