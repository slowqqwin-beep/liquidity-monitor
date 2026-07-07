#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SR3 修复监控 — 只读型研究输出
==============================
回答四个问题：
  1. 当前是否仍处于 hawkish impulse
  2. 是否进入 deceleration
  3. 是否发生 level repair
  4. 修复分类 (benign / mixed / malign / unknown / decel_no_repair)

双轨参考峰值:
  - Formal Shock: 最后确认的 hawkish shock (5bp+, event_min_gap 去重)
  - Recent 60d Peak: 若 formal shock 距今 > 60d，切换为近期峰值参考

数据源: TradingView 自动导出 (data/历史数据/100-CME_DL_SR3H2027, 1D.csv)
        每次运行自动清洗列名 → 追加到 sr3_long.csv → 重算 sr3_curve_features.csv
        (已废除 sofr_sr3.csv 手工录入)

输入: sr3_curve_features.csv + macro_research_panel.csv
输出: sr3_repair_watch_latest.json + sr3_repair_watch_latest.md
约束: Research-Only — 不接 Risk OS / dashboard / run_all.py / 仓位
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date, timedelta
import json
from _treasury_yields import fetch_latest_yields, fetch_history, fetch_t10yie

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_DIR = PROJECT_ROOT / "data" / "macro_backtest" / "input"
PANEL_PATH = PROJECT_ROOT / "data" / "macro_db" / "processed" / "macro_research_panel.csv"
OUT_DIR = PROJECT_ROOT / "data" / "macro_backtest" / "research"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── TradingView CSV 自动同步 ──
TV_CSV = PROJECT_ROOT / "data" / "历史数据" / "100-CME_DL_SR3M2026, 1D.csv"
LONG_PATH = IN_DIR / "sr3_long.csv"
FEAT_PATH = IN_DIR / "sr3_curve_features.csv"

# 月份代码 → 月份数字
MONTH_CODE = {"F":1,"G":2,"H":3,"J":4,"K":5,"M":6,"N":7,"Q":8,"U":9,"V":10,"X":11,"Z":12}


def _clean_tv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """清洗 TradingView CSV 列名: 100-SR3X2026 · CME: close → SR3X2026, time→date, close→文件名合约码"""
    # 从文件名提取主合约: 100-CME_DL_SR3M2026, 1D.csv → SR3M2026
    main_contract = "SR3H2027"  # fallback
    try:
        import re as _re
        m = _re.search(r"SR3\w\d{4}", str(TV_CSV.name))
        if m:
            main_contract = m.group(0)
    except Exception:
        pass

    rename = {}
    for c in df.columns:
        if c == "time":
            rename[c] = "date"
        elif c == "close":
            rename[c] = main_contract  # 动态映射：文件名是什么合约，close 就是什么
        else:
            m = re.match(r"100-(SR3\w\d{4})\s*·\s*CME:\s*close", c)
            if m:
                rename[c] = m.group(1)
    return df.rename(columns=rename)





CACHE_JSON_PATH = PROJECT_ROOT / "data" / "treasury_yields_cache.json"


def _upsert_tv_aux_into_series(d: str, col_v9d, col_v3m, col_move, latest):
    """Write MOVE/VIX9D/VIX3M from TV CSV into series.json for VTS/RCV."""
    series_path = PROJECT_ROOT / "data" / "series.json"
    if not series_path.exists():
        return
    sdata = json.loads(series_path.read_text("utf-8"))
    updates = []
    if col_v9d:
        updates.append(("^VIX9D", round(float(latest[col_v9d]), 2)))
    if col_v3m:
        updates.append(("^VIX3M", round(float(latest[col_v3m]), 2)))
    if col_move:
        updates.append(("MOVE", round(float(latest[col_move]), 2)))
    for key, val in updates:
        items = sdata.get(key, [])
        if items and items[-1].get("date") == d:
            items[-1]["value"] = val
        else:
            items.append({"date": d, "value": val})
        sdata[key] = items
    series_path.write_text(json.dumps(sdata, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[SR3 Sync] Upserted MOVE/VIX9D/VIX3M into series.json from TV")

def _sync_treasury_from_tv(raw: pd.DataFrame):
    """Extract US10Y/US02Y/US03M/VIX9D/VIX3M/MOVE from TradingView CSV.
    Updates 2s10s.csv, 2s3m_history.csv, treasury_yields_cache.json, and tv_companion.json."""
    import csv as _csv
    col_10y = None; col_2y = None; col_3m = None
    col_v9d = None; col_v3m = None; col_move = None
    for c in raw.columns:
        cl = c.lower().replace(" ", "").replace("·", "").replace(":", "")
        if "us10y" in cl or "tvcus10y" in cl:
            col_10y = c
        elif "us02y" in cl or "tvcus02y" in cl:
            col_2y = c
        elif "us03my" in cl or "us03m" in cl:
            col_3m = c
        elif "vix9d" in cl or "vix9" in cl:
            col_v9d = c
        elif "vix3m" in cl or "vix3" in cl:
            col_v3m = c
        elif "move" in cl:
            col_move = c
    if not col_10y or not col_2y:
        return

    # Find last row with valid US10Y (06-30 may be empty before US market open)
    latest = None
    for i in range(len(raw) - 1, -1, -1):
        if pd.notna(raw.iloc[i][col_10y]):
            latest = raw.iloc[i]; break
    if latest is None:
        return
    d = str(latest["date"])[:10]
    ten = round(float(latest[col_10y]), 3)
    two = round(float(latest[col_2y]), 3)
    t3m = round(float(latest[col_3m]), 3) if col_3m and pd.notna(latest.get(col_3m)) else None
    print(f"[SR3 Sync] TV: {d} US10Y={ten}, US02Y={two}, US03M={t3m}, 2s10s={round((ten-two)*100,1)}bp")

    # Write 2s10s.csv (TradingView format)
    for csv_path in [PROJECT_ROOT / "2s10s.csv"]:
        existing = []
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                for r in _csv.DictReader(f):
                    existing.append(r)
        updated = False
        for r in existing:
            if r.get("time", "") == d:
                r["close"] = str(ten)
                for k in list(r.keys()):
                    if "us02y" in k.lower().replace(" ", "").replace("·", ""):
                        r[k] = str(two)
                updated = True; break
        if not updated:
            existing.append({"time": d, "close": str(ten), "US02Y · TVC: close": str(two)})
        existing.sort(key=lambda x: x.get("time", ""))
        if existing:
            headers = list(existing[0].keys())
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as fw:
                w = _csv.DictWriter(fw, headers); w.writeheader(); w.writerows(existing)

    # Write twos10s_history.csv (audit format)
    h2_path = PROJECT_ROOT / "docs" / "sr3-watch" / "data" / "twos10s_history.csv"
    h2_existing = []
    if h2_path.exists():
        with open(h2_path, "r", encoding="utf-8-sig") as f:
            for r in _csv.DictReader(f):
                h2_existing.append(r)
    h2_updated = False
    for r in h2_existing:
        if r.get("date", "") == d:
            r["ten_y"] = str(ten); r["two_y"] = str(two)
            r["spread_bp"] = str(round((ten - two) * 100, 1)); h2_updated = True; break
    if not h2_updated:
        h2_existing.append({"date": d, "ten_y": str(ten), "two_y": str(two),
                            "spread_bp": str(round((ten - two) * 100, 1))})
    h2_existing.sort(key=lambda x: x["date"])
    h2_path.parent.mkdir(parents=True, exist_ok=True)
    with open(h2_path, "w", encoding="utf-8-sig", newline="") as fw:
        w = _csv.DictWriter(fw, ["date", "ten_y", "two_y", "spread_bp"])
        w.writeheader(); w.writerows(h2_existing)

    # Write 2Y-3M history
    if t3m is not None:
        c3m_path = PROJECT_ROOT / "docs" / "sr3-watch" / "data" / "two_3m_history.csv"
        existing_3m = []
        if c3m_path.exists():
            with open(c3m_path, "r", encoding="utf-8-sig") as f:
                for r in _csv.DictReader(f):
                    existing_3m.append(r)
        for r in existing_3m:
            if r["date"] == d:
                r["two_y"] = str(two); r["three_m"] = str(t3m)
                r["spread_bp"] = str(round((two - t3m) * 100, 1)); break
        else:
            existing_3m.append({"date": d, "two_y": str(two), "three_m": str(t3m),
                                "spread_bp": str(round((two - t3m) * 100, 1))})
        existing_3m.sort(key=lambda x: x["date"])
        c3m_path.parent.mkdir(parents=True, exist_ok=True)
        with open(c3m_path, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.DictWriter(f, ["date", "two_y", "three_m", "spread_bp"])
            w.writeheader(); w.writerows(existing_3m)

    # Update cache — rebuild from twos10s_history.csv if empty
    try:
        cache = json.loads(CACHE_JSON_PATH.read_text("utf-8")) if CACHE_JSON_PATH.exists() else {"series": []}
    except Exception:
        cache = {"series": []}
    if not cache.get("series"):
        # Cache empty (e.g. deleted) — rebuild from persistent history CSV
        try:
            h2_path = PROJECT_ROOT / "docs" / "sr3-watch" / "data" / "twos10s_history.csv"
            if h2_path.exists():
                with open(h2_path, "r", encoding="utf-8-sig") as f:
                    for r in _csv.DictReader(f):
                        cache["series"].append({
                            "date": r["date"],
                            "ten_y": float(r["ten_y"]),
                            "two_y": float(r["two_y"]),
                            "spread_bp": float(r["spread_bp"]),
                        })
                print(f"[SR3 Sync] Rebuilt treasury_yields_cache from twos10s_history.csv ({len(cache['series'])} rows)")
        except Exception:
            pass
    for s in cache.get("series", []):
        if s["date"] == d:
            s["ten_y"] = ten; s["two_y"] = two; s["spread_bp"] = round((ten - two) * 100, 1); break
    else:
        cache["series"].append({"date": d, "ten_y": ten, "two_y": two,
                                "spread_bp": round((ten - two) * 100, 1)})
    cache["series"].sort(key=lambda x: x["date"])
    cache["fetched_at"] = datetime.now().isoformat()
    CACHE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_JSON_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    # Write TV companion data (VIX9D, VIX3M, MOVE) for daily_report
    companion_path = PROJECT_ROOT / "data" / "tv_companion.json"
    tv_data = {"date": d, "us10y": ten, "us02y": two, "us03m": t3m}
    if col_v9d: tv_data["vix9d"] = round(float(latest[col_v9d]), 1)
    if col_v3m: tv_data["vix3m"] = round(float(latest[col_v3m]), 1)
    if col_move: tv_data["move"] = round(float(latest[col_move]), 1)
    try:
        existing = json.loads(companion_path.read_text("utf-8")) if companion_path.exists() else []
    except Exception:
        existing = []
    existing = [e for e in existing if e.get("date") != d]
    existing.append(tv_data)
    existing.sort(key=lambda x: x["date"])
    companion_path.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[SR3 Sync] TV companion: {tv_data}")

    # Upsert MOVE/VIX9D/VIX3M into series.json so VTS/RCV get fresh data
    _upsert_tv_aux_into_series(d, col_v9d, col_v3m, col_move, latest)


def _sync_from_tradingview():
    """从 TradingView CSV 同步新日期到 sr3_long.csv + 重算 sr3_curve_features.csv。
    幂等：已存在的日期不重复追加。"""
    if not TV_CSV.exists():
        print(f"[SR3 Sync] ⚠ TradingView CSV not found: {TV_CSV}")
        print(f"  → 跳过同步，使用现有 sr3_long.csv / sr3_curve_features.csv")
        return

    print("[SR3 Sync] Reading TradingView CSV...")
    raw = pd.read_csv(TV_CSV, low_memory=False)
    raw = _clean_tv_columns(raw)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw = raw[raw["date"].notna()].copy()
    # 去重列名（e.g. close→SR3H2027 与 100-SR3H2027·CME→SR3H2027 可能冲突）
    raw = raw.loc[:, ~raw.columns.duplicated()]

    # 找到所有合约列 (SR3*)
    contract_cols = [c for c in raw.columns if re.match(r"SR3\w\d{4}", c)]
    if not contract_cols:
        print("[SR3 Sync] ⚠ No SR3 contract columns found after cleaning.")
        return

    print(f"  TV date range: {raw['date'].min().date()} ~ {raw['date'].max().date()}")
    print(f"  Contracts: {len(contract_cols)} ({', '.join(sorted(contract_cols))})")

    # 转长表 (wide → long)
    records = []
    for _, row in raw.iterrows():
        dt = row["date"]
        for col in contract_cols:
            val = row[col]
            if isinstance(val, pd.Series):
                val = val.iloc[0] if len(val) > 0 else np.nan
            try:
                price = float(val)
            except (ValueError, TypeError):
                continue
            if pd.notna(price) and price > 0:
                contract = col  # e.g. "SR3M2026"
                month_char = contract[3]  # 'M'
                year_str = contract[4:]  # '2026'
                year = int(year_str)
                month = MONTH_CODE.get(month_char, 1)
                # TradingView CSV 数值已是利率 (3.xx~4.xx%)，非价格 (96.xx)
                rate = price
                records.append({
                    "date": dt,
                    "contract": contract,
                    "maturity": datetime(year, month, 1),
                    "maturity_year": year,
                    "maturity_month": month,
                    "open": np.nan,
                    "high": np.nan,
                    "low": np.nan,
                    "close": 100.0 - rate,  # 价格格式，向下兼容
                    "implied_rate": rate,     # 利率格式，特征计算用
                    "volume": np.nan,
                    "position": np.nan,
                })

    new_long = pd.DataFrame(records).sort_values(["date", "maturity"]).reset_index(drop=True)
    new_dates = sorted(new_long["date"].unique())
    print(f"  Long format: {len(new_long)} rows, {len(new_dates)} dates")

    # 加载现有长表，覆盖重叠日期（TradingView 数据比旧 sofr_sr3 更可靠）
    if LONG_PATH.exists():
        existing_long = pd.read_csv(LONG_PATH, parse_dates=["date", "maturity"])
        old_dates = set(new_long["date"].dt.date)
        # 删除旧长表中与新数据重叠的日期行
        existing_long = existing_long[~existing_long["date"].dt.date.isin(old_dates)]
    else:
        existing_long = pd.DataFrame()

    new_dates_only = sorted(new_long["date"].unique())
    print(f"  Dates to upsert: {len(new_dates_only)} ({new_dates_only[0].date()} ~ {new_dates_only[-1].date()})")

    # ── 1. 写入 sr3_long.csv（旧数据去掉重叠日期 + 新数据）──
    long_cols = ["date","contract","maturity","maturity_year","maturity_month",
                 "open","high","low","close","implied_rate","volume","position"]
    updated_long = pd.concat([existing_long, new_long[long_cols]], ignore_index=True)
    updated_long = updated_long.sort_values(["date","maturity"]).reset_index(drop=True)
    LONG_PATH.parent.mkdir(parents=True, exist_ok=True)
    updated_long.to_csv(LONG_PATH, index=False)
    print(f"  → sr3_long.csv: {len(updated_long):,} rows (replaced {len(old_dates)} overlapping dates)")

    # ── 2. 为所有 TradingView 日期重新计算曲线特征 ──
    new_features = []
    for dt in new_dates_only:
        grp = new_long[new_long["date"] == dt].sort_values("maturity")
        # 过滤已到期合约（maturity < data_date）
        grp = grp[grp["maturity"] >= pd.Timestamp(dt)]
        if len(grp) < 3:
            continue
        rates = grp["implied_rate"].values
        contracts = grp["contract"].values
        maturities = grp["maturity"].values
        n = len(rates)

        valid_cutoff = max(1, int(n * 2 / 3))
        valid_rates = rates[:valid_cutoff]
        valid_contracts = contracts[:valid_cutoff]
        valid_maturities = maturities[:valid_cutoff]

        terminal_idx = np.argmin(valid_rates)
        peak_idx = np.argmax(valid_rates)
        mid_s = max(0, int(n * 0.2)); mid_e = min(n, int(n * 0.8))
        mid_mean = np.mean(rates[mid_s:mid_e]) if mid_e > mid_s else np.nan

        z6 = grp[grp["contract"]=="SR3Z2026"]["implied_rate"]
        m7 = grp[grp["contract"]=="SR3M2027"]["implied_rate"]
        z6_val = float(z6.values[0]) if len(z6) > 0 else np.nan
        m7_val = float(m7.values[0]) if len(m7) > 0 else np.nan

        new_features.append({
            "date": dt,
            "n_contracts": n,
            "near_rate": rates[0],
            "near_contract": contracts[0],
            "far_rate": rates[-1],
            "far_contract": contracts[-1],
            "terminal_rate": valid_rates[terminal_idx],
            "terminal_contract": valid_contracts[terminal_idx],
            "terminal_maturity": pd.Timestamp(valid_maturities[terminal_idx]),
            "peak_rate": valid_rates[peak_idx],
            "peak_contract": valid_contracts[peak_idx],
            "peak_maturity": pd.Timestamp(valid_maturities[peak_idx]),
            "curve_slope_bp": (rates[-1] - rates[0]) * 100,
            "mid_mean_rate": mid_mean,
            "z6_rate": z6_val,
            "m7_rate": m7_val,
        })

    new_feat_df = pd.DataFrame(new_features).sort_values("date").reset_index(drop=True)

    # ── 3. 合并到 sr3_curve_features.csv + 重算派生列 ──
    if FEAT_PATH.exists():
        old_feat = pd.read_csv(FEAT_PATH, parse_dates=["date","terminal_maturity","peak_maturity"])
    else:
        old_feat = pd.DataFrame()

    combined_feat = pd.concat([old_feat, new_feat_df], ignore_index=True)
    combined_feat = combined_feat.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    combined_feat = combined_feat.sort_values("date").reset_index(drop=True)

    # Recompute derived columns
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

    FEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined_feat.to_csv(FEAT_PATH, index=False, float_format="%.6f")
    print(f"  → sr3_curve_features.csv: {len(combined_feat):,} rows (+{len(new_feat_df)})")

    latest = combined_feat.iloc[-1]
    print(f"  Latest: date={latest['date'].date()}, near_rate={latest['near_rate']:.4f}%, "
          f"curve_move_bp={latest['curve_move_bp']:.2f}, curve_move_5d_sum={latest['curve_move_5d_sum']:.2f}")
    print(f"[SR3 Sync] Done.\n")

    # ── Extract US10Y/US02Y from TV CSV (if user added TVC:US10Y and TVC:US02Y to chart) ──
    _sync_treasury_from_tv(raw)


PARAMS = {
    "shock_5d_min_bp": 4.0, "shock_1d_min_bp": 3.0,
    "peak_lookback_days": 5,
    "decel_abs_bp_threshold": 1.5, "decel_min_days": 2,
    "repair_min_bp": 5.0, "repair_min_ratio": 0.3,
    "shock_min_height_bp": 5.0, "event_min_gap_days": 20,
    "credit_hyoas_benign_max_bp": 10.0,
    "credit_hyoas_malign_min_bp": 20.0,
    "credit_dgs10_declining_bp": -2.0,
    "level_repair_bp": 10.0, "level_repair_min_days": 2,
}


def load_data():
    feat_path = IN_DIR / "sr3_curve_features.csv"
    if not feat_path.exists():
        raise FileNotFoundError(f"SR3 features not found: {feat_path}\nRun scripts/reconstruct_sr3_data.py first")
    sr3 = pd.read_csv(feat_path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    # Unified macro source: series.json (same as daily_report.py)
    _SR = PROJECT_ROOT / "data" / "series.json"
    macro_map: dict = {}
    if _SR.exists():
        try:
            _s = json.loads(_SR.read_text("utf-8"))
            for key in ["BAMLH0A0HYM2", "HY_OAS_available", "HY_OAS_chg_20d",
                         "credit_signal_status", "DGS10", "DGS2"]:
                items = _s.get(key, [])
                for it in items:
                    d = it.get("date", "")[:10]
                    v = it.get("value")
                    if d and v is not None:
                        macro_map.setdefault(d, {})[key] = float(v)
        except Exception:
            pass

    # Merge macro fields into sr3
    for col in ["BAMLH0A0HYM2", "HY_OAS_available", "HY_OAS_chg_20d", "credit_signal_status"]:
        sr3[col] = sr3["date"].apply(lambda d: macro_map.get(str(d)[:10], {}).get(col, np.nan))

    # 20d change from series data (direct compute, not panel)
    hy_vals = sr3["BAMLH0A0HYM2"].values
    hy_chg_20d = np.full(len(hy_vals), np.nan)
    for i in range(20, len(hy_vals)):
        if pd.notna(hy_vals[i]) and pd.notna(hy_vals[i - 20]):
            hy_chg_20d[i] = round(float(hy_vals[i] - hy_vals[i - 20]), 6)
    sr3["HY_OAS_chg_20d"] = hy_chg_20d

    return sr3.dropna(subset=["near_rate"]).reset_index(drop=True)


def find_latest_shock(df):
    df["s5"] = df["curve_move_5d_sum"] > PARAMS["shock_5d_min_bp"]
    df["s1"] = df["curve_move_bp"] > PARAMS["shock_1d_min_bp"]
    lb = PARAMS["peak_lookback_days"]
    df["pk"] = False
    for i in range(lb, len(df) - lb):
        w = df["near_rate"].iloc[i - lb:i + lb + 1]
        if df["near_rate"].iloc[i] == w.max():
            df.at[df.index[i], "pk"] = True
    df["hs"] = (df["s5"] | df["s1"]) & df["pk"]
    idxs = df[df["hs"]].index.tolist()
    events, last = [], -999
    for i in idxs:
        if i - last < PARAMS["event_min_gap_days"]:
            continue
        pw_start = max(0, i - lb * 2)
        pw = df["near_rate"].iloc[pw_start:i]
        tv = pw.min() if len(pw) > 0 else df["near_rate"].iloc[i]
        ti = pw.idxmin() if len(pw) > 0 else i
        h = (df["near_rate"].iloc[i] - tv) * 100
        if h >= PARAMS["shock_min_height_bp"]:
            events.append({"shock_idx": i, "shock_date": df["date"].iloc[i],
                           "trough_idx": ti, "trough_date": df["date"].iloc[ti] if ti >= 0 else None,
                           "peak_near_rate": df["near_rate"].iloc[i], "shock_height_bp": h})
            last = i
    return events


def curve_structure_check(df, ref_date, ref_idx):
    """对比今日全合约 vs 参考日全合约：逐合约隐含利率差。
    返回: {ref_date, n_below, n_total, avg_dev_bp, all_below, detail_list}"""
    if not LONG_PATH.exists():
        return None
    long_df = pd.read_csv(LONG_PATH, parse_dates=["date", "maturity"])
    long_df = long_df.sort_values(["date", "maturity"])

    li = len(df) - 1
    today = df["date"].iloc[li]
    today_date = pd.Timestamp(today).date() if hasattr(today, 'date') else pd.Timestamp(today).date()

    # 拿今日和参考日的合约快照
    today_snap = long_df[long_df["date"].dt.date == today_date]
    ref_snap = long_df[long_df["date"].dt.date == pd.Timestamp(ref_date).date()]

    if len(today_snap) == 0 or len(ref_snap) == 0:
        return None

    # 按 contract 对齐
    merged = today_snap[["contract", "implied_rate"]].merge(
        ref_snap[["contract", "implied_rate"]],
        on="contract", suffixes=("_today", "_ref")
    )
    if len(merged) < 3:
        return None

    merged["dev_bp"] = (merged["implied_rate_today"] - merged["implied_rate_ref"]) * 100
    n_total = len(merged)
    n_below = int((merged["dev_bp"] < 0).sum())
    avg_dev = float(merged["dev_bp"].mean())
    all_below = n_below == n_total
    n_above = int((merged["dev_bp"] > 0).sum())

    detail = []
    for _, r in merged.sort_values("maturity" if "maturity" in merged.columns else "contract").iterrows():
        detail.append({
            "contract": r["contract"],
            "today_pct": round(float(r["implied_rate_today"]), 4),
            "ref_pct": round(float(r["implied_rate_ref"]), 4),
            "dev_bp": round(float(r["dev_bp"]), 2),
        })

    return {
        "ref_date": str(pd.Timestamp(ref_date).date()),
        "today_date": str(today_date),
        "n_contracts": n_total,
        "n_below": n_below,
        "n_above": n_above,
        "avg_deviation_bp": round(avg_dev, 2),
        "all_below_ref": all_below,
        "detail": detail,
    }


def analyze(df, last_shock):
    si = last_shock["shock_idx"]
    shock_peak = last_shock["peak_near_rate"]
    shock_date = last_shock["shock_date"]
    li = len(df) - 1
    ld = df["date"].iloc[li]
    ds = li - si

    # Recent 60d peak as fallback reference (EXCLUDE today: peak can't be "0d ago")
    rws = max(0, li - 60)
    rdf = df.iloc[rws:li]  # exclude today (index li) so reference peak ≠ today
    if len(rdf) > 0:
        rpi = rdf["near_rate"].idxmax()
        rpr = df["near_rate"].iloc[rpi]
        rpd = df["date"].iloc[rpi]
    else:
        rpi, rpr, rpd = li, df["near_rate"].iloc[li], df["date"].iloc[li]

    use_formal = ds <= 60
    ref_rate = shock_peak if use_formal else rpr
    ref_date = shock_date if use_formal else rpd
    ref_idx = si if use_formal else rpi
    ref_label = "Current Event Peak (Hike-over)" if use_formal else "recent 60d peak"

    cr = df.iloc[li]
    cnr = cr["near_rate"]
    cmv = cr.get("curve_move_bp", np.nan)
    c5s = cr.get("curve_move_5d_sum", np.nan)

    # 结构对比优先用近期 60 日峰（vs 参考日），不是 formal shock
    # 因为结构松动是视觉信号：今天曲线比最近峰值低
    struct_ref_date = rpd if li - rpi < ds else ref_date
    struct = curve_structure_check(df, struct_ref_date, ref_idx)

    # Impulse check (near_rate already in %; 2bp ≈ 0.02%)
    near_peak = abs(cnr - ref_rate) < 0.02
    rising = (not pd.isna(c5s)) and c5s > 1.0
    # 结构降级：全合约低于参考峰 → 即使 near_rate 还在峰值附近，也算松动
    structural_easing = struct and struct["all_below_ref"] and struct["n_contracts"] >= 4
    in_impulse = (near_peak or ((li - rpi) <= 3 and rising)) and not structural_easing

    # Deceleration
    decel = False; dsi = None; dsd = None
    sf = ref_idx + 1
    if sf < li:
        for i in range(sf, li - PARAMS["decel_min_days"] + 2):
            w = df["curve_move_bp"].iloc[i:i + PARAMS["decel_min_days"]]
            if w.abs().max() < PARAMS["decel_abs_bp_threshold"]:
                decel = True; dsi = i; dsd = df["date"].iloc[i]; break
    if not decel and sf <= li:
        r = df["curve_move_bp"].iloc[max(sf, li - PARAMS["decel_min_days"] + 1):li + 1]
        if len(r) >= PARAMS["decel_min_days"] and r.abs().max() < PARAMS["decel_abs_bp_threshold"]:
            decel = True; dsi = li - len(r) + 1; dsd = df["date"].iloc[dsi]

    # Repair
    repair = False; rsi = None; rsd = None; rbp = 0.0
    if decel:
        sh = max(last_shock["shock_height_bp"], 0.1) if use_formal else max((rpr - df["near_rate"].iloc[max(0, rpi - 10):rpi].min()) * 100, 0.1)
        for i in range(max(ref_idx + 1, dsi), li + 1):
            d = (ref_rate - df["near_rate"].iloc[i]) * 100
            if d >= PARAMS["repair_min_bp"] and d / sh >= PARAMS["repair_min_ratio"]:
                repair = True; rsi = i; rsd = df["date"].iloc[i]; rbp = d; break

    level_repair = False
    if repair and rsi is not None:
        cd = (ref_rate - cnr) * 100
        cnt = 0
        for j in range(li, rsi - 1, -1):
            if (ref_rate - df["near_rate"].iloc[j]) * 100 >= PARAMS["level_repair_bp"]:
                cnt += 1
            else:
                break
        if cd >= PARAMS["level_repair_bp"] and cnt >= PARAMS["level_repair_min_days"]:
            level_repair = True

    # Classification
    cls = "unknown"; reason = ""
    if repair and rsi is not None:
        rr = df.iloc[rsi]
        hoa = bool(rr.get("HY_OAS_available", False)) if not pd.isna(rr.get("HY_OAS_available")) else False
        if not hoa:
            cls = "unknown_credit_unavailable"; reason = "HY OAS missing — cannot classify"
        else:
            hoc = rr.get("HY_OAS_chg_20d", 0)
            hoc = 0 if pd.isna(hoc) else hoc
            hoc_bp = hoc * 100
            # US10Y 20d change from yfinance (no FRED lag)
            hs = hoc_bp < PARAMS["credit_hyoas_benign_max_bp"]
            df10 = us10y_20d_bp is not None and us10y_20d_bp < PARAMS["credit_dgs10_declining_bp"]
            hstr = hoc_bp > PARAMS["credit_hyoas_malign_min_bp"]
            if hs and df10:
                cls = "benign_repair"; reason = "HY OAS stable/declining + US10Y declining (soft landing)"
            elif hstr:
                cls = "malign_repair"; reason = "HY OAS widening (credit stress)"
            elif df10:
                cls = "mixed_repair"; reason = "US10Y declining but HY OAS moderately widening"
            else:
                cls = "mixed_repair"; reason = "Mixed signals, no clear benign/malign pattern"
    elif decel:
        cls = "decel_no_repair"; reason = "Deceleration detected but no repair yet"
    elif in_impulse:
        cls = "still_in_impulse"; reason = "Still in hawkish impulse phase"
    elif structural_easing:
        # 5d sum direction
        fived = round(float(c5s), 2) if not pd.isna(c5s) else None
        if fived is not None and fived < 0:
            cls = "structural_easing_confirming"
            reason = (f"全线合约低于参考峰({ref_date.date() if hasattr(ref_date,'date') else ref_date})，"
                      f"且 5d累计转负({fived:.1f}bp) — 结构松动获得动能确认")
        else:
            cls = "structural_easing"
            reason = (f"全线合约低于参考峰({ref_date.date() if hasattr(ref_date,'date') else ref_date})，"
                      f"但动能信号仍不干净 — 结构松动先于动能")

    # State (descriptive only — research-only, not actionable)
    if cls == "benign_repair":
        st, sl, act = 4, "State 4: Benign Repair", "短端预期：benign repair 确认（利率从参考峰回落 + 信用稳定/收窄）"
    elif level_repair:
        st, sl, act = 3, "State 3: Level Repair", "短端预期：已从参考峰回落 ≥10bp（level repair）；信用端分类见下方"
    elif decel:
        st, sl, act = 2, "State 2: Deceleration", "短端预期：已钝化（曲线移动 <1.5bp），但尚未出现实质性/持续修复"
    elif structural_easing:
        st, sl, act = 2, "State 2: Deceleration", "短端预期：全线合约低于参考峰（结构松动），但动能信号仍在鹰派区；结构性下降领先"
    else:
        st, sl, act = 1, "State 1: Hawkish Impulse", "短端预期：鹰派冲击未消退；曲线仍在上行或高台维持"

    lr = df.iloc[li]
    # ── yfinance 直接抓 US10Y / US02Y / 20d 变动（不依赖本地 CSV）──
    us10y_yf, us2y_yf = fetch_latest_yields()
    # 20d change from cached history
    hist = fetch_history(60)
    us10y_20d_bp = None
    if len(hist) >= 21:
        us10y_20d_bp = round((hist[-1]["ten_y"] - hist[-21]["ten_y"]) * 100, 1)
    # ── Macro fallback: 面板未追到时从 series.json 兜底 ──
    def _macro_fallback(key, pre_key=None):
        v = lr.get(pre_key or key, None)
        if v is not None and not pd.isna(v):
            return v
        try:
            series = json.loads((PROJECT_ROOT / "data" / "series.json").read_text(encoding="utf-8"))
            items = series.get(key, [])
            if items:
                return float(items[-1].get("value", items[-1] if isinstance(items[-1], (int, float)) else np.nan))
        except Exception:
            pass
        return None
    ho = _macro_fallback("BAMLH0A0HYM2")
    ho = round(float(ho), 2) if ho is not None else None

    # ── US10Y：跟 2s10s 缓存同源（yfinance ^TNX，无时滞）──
    us10y = None
    if hist:
        raw = hist[-1].get("ten_y")
        us10y = round(raw, 3) if raw else None
    if us10y is None and us10y_yf is not None:
        us10y = us10y_yf
    if us10y is None:
        try:
            US10Y_PATH = PROJECT_ROOT / "data" / "历史数据" / "TVC_US10Y, 1D.csv"
            if US10Y_PATH.exists():
                us10y_df = pd.read_csv(US10Y_PATH)
                us10y = round(float(us10y_df.iloc[-1]["close"]), 2)
        except Exception:
            pass
    if us10y is None:
        us10y = _macro_fallback("DGS10")
        us10y = round(float(us10y), 2) if us10y is not None else None

    # ── T10YIE：FRED 直播（无 API key，备选本地 CSV / series.json）──
    t10yie = fetch_t10yie()
    if t10yie is None:
        T10YIE_PATH = PROJECT_ROOT / "data" / "历史数据" / "T10YIE.csv"
        try:
            if T10YIE_PATH.exists():
                t10yie_df = pd.read_csv(T10YIE_PATH)
                t10yie = round(float(t10yie_df.iloc[-1]["T10YIE"]), 3)
        except Exception:
            pass
    if t10yie is None:
        try:
            series = json.loads((PROJECT_ROOT / "data" / "series.json").read_text(encoding="utf-8"))
            items = series.get("T10YIE", [])
            if items:
                t10yie = round(float(items[-1].get("value", 0)), 3)
        except Exception:
            pass
    real_yield = round(us10y - t10yie, 3) if us10y is not None and t10yie is not None else None

    # ── 合约日差价：今日全合约 close vs 前一交易日 ──
    contract_diffs = []
    if LONG_PATH.exists():
        long_all = pd.read_csv(LONG_PATH, parse_dates=["date"])
        long_all = long_all.sort_values(["date", "maturity"])
        today_date = pd.Timestamp(ld).date() if hasattr(ld, 'date') else pd.Timestamp(ld).date()
        today_rows = long_all[long_all["date"].dt.date == today_date]
        if len(today_rows) > 0:
            prev_date = sorted(long_all["date"].dt.date.unique())[-2]
            prev_rows = long_all[long_all["date"].dt.date == prev_date]
            merged = today_rows[["contract","close","implied_rate"]].merge(
                prev_rows[["contract","close","implied_rate"]],
                on="contract", suffixes=("", "_prev"), how="left"
            )
            for _, r in merged.iterrows():
                prev_close = r.get("close_prev")
                chg = float(r["close"] - prev_close) if pd.notna(prev_close) and pd.notna(r["close"]) else None
                chg_bp = (float(r["implied_rate"] - r["implied_rate_prev"]) * 100) if pd.notna(r.get("implied_rate_prev")) and pd.notna(r["implied_rate"]) else None
                contract_diffs.append({
                    "contract": r["contract"],
                    "close": round(float(r["close"]), 4),
                    "close_chg": round(chg, 4) if chg is not None else None,
                    "implied_rate_pct": round(float(r["implied_rate"]), 4),
                    "implied_chg_bp": round(chg_bp, 2) if chg_bp is not None else None,
                })

    # ── 当日变动：从合约差价表取近端合约的 implied_chg_bp（比 curve_move_bp 更可靠）──
    contract_daily_bp = None
    if contract_diffs:
        for c in contract_diffs:
            if c.get("implied_chg_bp") is not None:
                contract_daily_bp = c["implied_chg_bp"]; break

    # ── 逐合约 FOMC 修复表：baseline (06-16) → peak (06-22) → now ──
    retracement = _compute_retracement(ld)

    # US trade date: China morning download → previous day's US close
    # TradingView bar labeled N = US trading day N-1 (from China timezone perspective)
    us_trade_date = (ld - pd.Timedelta(days=1)).date()
    return {
        "generated_at": datetime.now().isoformat(),
        "data_date": str(us_trade_date),
        "data_age_days": (date.today() - us_trade_date).days,
        "reference_mode": ref_label,
        "last_formal_shock": {"date": str(shock_date.date()), "days_ago": ds,
                              "peak_near_rate_pct": round(float(shock_peak), 4),
                              "shock_height_bp": round(last_shock["shock_height_bp"], 2),
                              "still_active": use_formal},
        "recent_60d_peak": {"date": str(rpd.date()), "days_ago": li - rpi,
                            "near_rate_pct": round(float(rpr), 4),
                            "used_as_reference": not use_formal},
        "current": {"near_rate_pct": round(float(cnr), 4),
                    "curve_move_bp": round(float(cmv), 2) if not pd.isna(cmv) else None,
                    "contract_daily_bp": contract_daily_bp,  # from contract_diffs (more reliable)
                    "curve_move_5d_sum_bp": round(float(c5s), 2) if not pd.isna(c5s) else None,
                    # decline_from_ref_peak uses contract-matched struct comparison (not near_rate)
                    "decline_from_ref_peak_bp": round(float(struct["avg_deviation_bp"]), 2) if struct else None,
                    "near_contract": struct["detail"][0]["contract"] if struct and struct.get("detail") else None,
                    "on_elevated_plateau": bool(cnr > 3.5),
                    "hy_oas_bp": round(ho * 100, 1) if ho is not None else None,
                    "hy_oas_available": bool(lr.get("HY_OAS_available", False)) if not pd.isna(lr.get("HY_OAS_available")) else False,
                    "us10y_pct": us10y, "t10yie_pct": t10yie, "real_yield_pct": real_yield},
        "state": {"state_number": st, "state_label": sl,
                  "in_hawkish_impulse": st == 1,
                  "structural_easing_detected": bool(structural_easing),
                  "deceleration_detected": decel, "decel_start_date": str(dsd.date()) if dsd else None,
                  "level_repair_detected": level_repair,
                  "repair_detected": repair, "repair_start_date": str(rsd.date()) if rsd else None,
                  "repair_bp_from_peak": round(float(rbp), 2),
                  "repair_classification": cls, "repair_classification_reason": reason},
        "contract_diffs": contract_diffs,
        "retracement": retracement,
        "action": act,
        "curve_structure": struct or {},
        "constraints": {"research_only": True, "not_in_risk_os": True,
                        "not_in_dashboard": True, "not_in_run_all": True,
                        "deceleration_not_buy_signal": True},
    }


def _compute_retracement(latest_date):
    """逐合约 FOMC retracement: baseline (06-16) → peak (06-22) → now.
    Returns list of {contract, baseline, peak, now, overshoot_bp, retraced_bp, repair_pct}."""
    if not LONG_PATH.exists():
        return []
    try:
        long_all = pd.read_csv(LONG_PATH, parse_dates=["date"])
        long_all = long_all.sort_values(["date", "maturity"])
        baseline_dt = pd.Timestamp("2026-06-16")
        peak_dt = pd.Timestamp("2026-06-22")
        now_dt = pd.Timestamp(latest_date).date() if hasattr(latest_date, 'date') else pd.Timestamp(latest_date).date()

        def _get_rates(dt):
            rows = long_all[long_all["date"].dt.date == (dt.date() if hasattr(dt, 'date') else dt)]
            return {r["contract"]: r["implied_rate"] for _, r in rows.iterrows()
                    if pd.notna(r.get("implied_rate"))}

        bl = _get_rates(baseline_dt)
        pk = _get_rates(peak_dt)
        nw = _get_rates(now_dt)

        result = []
        for ct in sorted(set(bl) & set(pk) & set(nw)):
            b, p, n = bl[ct], pk[ct], nw[ct]
            over = round((p - b) * 100, 1)
            retr = round((p - n) * 100, 1)
            pct = round(retr / over * 100, 1) if over > 0.5 else None
            result.append({
                "contract": ct,
                "baseline_pct": round(float(b), 4),
                "peak_pct": round(float(p), 4),
                "now_pct": round(float(n), 4),
                "overshoot_bp": over,
                "retraced_bp": retr,
                "repair_pct": pct,
            })
        return result
    except Exception:
        return []


def _format_diffs(cd):
    """Format contract diff data into MD table string."""
    if not cd:
        return "| — | — | — | — | 数据不可用 |\n"
    lines = ["\n| 合约 | 收盘价 | 日变 | 隐含利率 | 日变(bp) |",
             "|------|--------|------|----------|----------|"]
    for d in cd:
        chg_str = f"{d['close_chg']:+.4f}" if d.get('close_chg') is not None else "—"
        bp_str = f"{d['implied_chg_bp']:+.1f}" if d.get('implied_chg_bp') is not None else "—"
        lines.append(f"| {d['contract']} | {d['close']:.4f} | {chg_str} | {d['implied_rate_pct']:.3f}% | {bp_str} |")
    return "\n" + "\n".join(lines)


def _format_yield_curve_section():
    """Read 2s10s and 2s3m from cache and format MD table."""
    import csv as _csv
    lines = []

    # ── 2s10s from treasury_yields_cache ──
    CACHE_PATH = PROJECT_ROOT / "data" / "treasury_yields_cache.json"
    ten = two = spread = d10 = d2 = d5 = structure = None
    try:
        cache = json.loads(CACHE_PATH.read_text("utf-8"))
        series = cache.get("series", [])
        if len(series) >= 6:
            cur = series[-1]; prev = series[-2]; base5 = series[-6]
            ten = cur.get("ten_y"); two = cur.get("two_y")
            spread = round((ten - two) * 100, 1) if ten and two else None
            d10 = round((ten - prev["ten_y"]) * 100, 1) if ten and prev.get("ten_y") else None
            d2 = round((two - prev["two_y"]) * 100, 1) if two and prev.get("two_y") else None
            d5 = round(spread - (base5["ten_y"] - base5["two_y"]) * 100, 1) if spread else None
            # Structure classification
            if d10 is not None and d2 is not None:
                if d10 < 0 and d2 < 0:
                    if d5 and d5 > 0: structure = "牛陡"
                    elif d5 and d5 < 0: structure = "牛平"
                    else: structure = "Bull / 收益率下行"
                elif d10 > 0 and d2 > 0:
                    if d5 and d5 > 0: structure = "熊陡"
                    elif d5 and d5 < 0: structure = "熊平"
                    else: structure = "Bear / 收益率上行"
                else:
                    structure = "Mixed / 混合"
    except Exception:
        pass

    # ── 2s3m from two_3m_history.csv ──
    C3M_PATH = PROJECT_ROOT / "docs" / "sr3-watch" / "data" / "two_3m_history.csv"
    s3m = d3m = d2y = s3m_5d = s3m_struct = None
    try:
        if C3M_PATH.exists():
            with open(C3M_PATH, "r", encoding="utf-8-sig") as f:
                m3r = list(_csv.DictReader(f))
            if len(m3r) >= 6:
                cur3 = m3r[-1]; prev3 = m3r[-2]; base3_5 = m3r[-6]
                y2_v = float(cur3["two_y"]); y3m_v = float(cur3["three_m"])
                s3m = round(float(cur3["spread_bp"]), 1)
                d2y = round((y2_v - float(prev3["two_y"])) * 100, 1)
                d3m = round((y3m_v - float(prev3["three_m"])) * 100, 1)
                s3m_5d = round(s3m - float(base3_5["spread_bp"]), 1)
                if s3m_5d and s3m_5d > 1: s3m_struct = "走阔 / Steepening"
                elif s3m_5d and s3m_5d < -1: s3m_struct = "收窄 / Flattening"
                else: s3m_struct = "Stable / 稳定"
    except Exception:
        pass

    # ── Build table ──
    lines.append("| 指标 | 当前 | 日变 | 5日变 | 结构 |")
    lines.append("|---|---:|---:|---:|")
    t2s = f"{spread}bp" if spread else "N/A"
    t3s = f"{s3m}bp" if s3m else "N/A"
    d10s = f"{d10}bp" if d10 is not None else "N/A"
    d5s = f"{d5}bp" if d5 is not None else "N/A"
    lines.append(f"| 2s10s | {t2s} | {d10s} | {d5s} | {structure or 'N/A'} |")
    d3ms = f"{d3m}bp" if d3m is not None else "N/A"
    d5_3m = f"{s3m_5d}bp" if s3m_5d is not None else "N/A"
    lines.append(f"| 2s3m | {t3s} | {d3ms} | {d5_3m} | {s3m_struct or 'N/A'} |")

    # One-liner interpretation
    if structure and "牛" in str(structure):
        interp = "✅ 现货曲线确认利率下行"
    elif structure and "Bear" in str(structure):
        interp = "🔴 现货曲线未配合SR3修复"
    else:
        interp = "🟡 现货曲线混合信号 — SR3修但现货未完全确认"

    lines.append("")
    lines.append(f"> {interp}")
    return "\n".join(lines)


def _format_structure(cs):
    """Format curve structure data into MD table string."""
    if not cs or not cs.get('detail'):
        return "\n| — | — | — | 数据不可用 |\n"
    lines = ["\n| 合约 | 今日 | 参考日 | 偏离 |",
             "|------|------|--------|------|"]
    for d in cs['detail']:
        lines.append(f"| {d['contract']} | {d['today_pct']:.3f}% | {d['ref_pct']:.3f}% | {d['dev_bp']:+.1f}bp |")
    status = "✅ 全线低于参考峰" if cs.get('all_below_ref') else "⚠️ 仍有合约高于参考峰"
    lines.append("")
    lines.append(f"> {status}：{cs['n_below']}/{cs['n_contracts']} 合约低于参考峰，平均偏离 {cs['avg_deviation_bp']:+.1f}bp")
    return "\n" + "\n".join(lines)


def write_outputs(r):
    jp = OUT_DIR / "sr3_repair_watch_latest.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False, default=str)

    s = r; sh = s["last_formal_shock"]; rp = s["recent_60d_peak"]
    cu = s["current"]; st = s["state"]
    em = {1: "🔴", 2: "🟡", 3: "🟢", 4: "🟢"}
    md = f"""# SR3 修复监控 — 当前状态

> **生成时间**: {s['generated_at'][:19]} | **数据日**: {s['data_date']}（{s['data_age_days']}d ago）
> **当前峰值口径**: {s['reference_mode']} | **状态**: Research-Only

---

## {em.get(st['state_number'], '⚪')} {st['state_label']}

> {s['action']}

---

## 四个关键问题

| # | 问题 | 答案 |
|---|------|------|
| 1 | 处于 hawkish impulse？ | **{'是 🔴' if st['in_hawkish_impulse'] else '否'}** |
| 2 | 进入 deceleration / 结构松动？ | **{'是 🟡 — ' + (st['decel_start_date'] or ('structural_easing' if st['structural_easing_detected'] else '全线低于参考峰')) if (st['deceleration_detected'] or st['structural_easing_detected']) else '否'}** |
| 3 | 发生 level repair？ | **{'是 🟢' if st['level_repair_detected'] else '否'}** |
| 4 | 修复分类 | **{st['repair_classification']}** |

---

## 参考峰值

| 来源 | 日期 | 距今 | ref_near_rate | 高度 |
|------|------|------|-----------|------|
| Current Event Peak (Hike-over) | {sh['date']} | {sh['days_ago']}d | {sh['peak_near_rate_pct']}% | {sh['shock_height_bp']}bp |
| Recent 60d Peak | {rp['date']} | {rp['days_ago']}d | {rp['near_rate_pct']}% | — |

当前使用: **{s['reference_mode']}**

---

## 当前快照

| 指标 | 值 |
|------|-----|
| near_rate | {cu['near_rate_pct']}% |
| 全曲线平均较峰值回落 | {cu['decline_from_ref_peak_bp']} bp |
| 当日变动 | {(cu['contract_daily_bp'] or cu['curve_move_bp'])} bp |
| 5d 累计 | {cu['curve_move_5d_sum_bp']} bp |
| 高台 (>3.5%) | {'⚠️ 是' if cu['on_elevated_plateau'] else '否'} |
| HY OAS | {cu['hy_oas_bp'] or 'N/A'} bp |
| US10Y | {cu['us10y_pct'] or 'N/A'}% |
| T10YIE | {cu['t10yie_pct'] or 'N/A'}% |
| Real Yield (10Y-T10YIE) | {cu['real_yield_pct'] or 'N/A'}% |

> * 当日变动来源：{'合约差价表 (contract-level)' if cu.get('contract_daily_bp') else 'sr3_curve_features.csv (near/far avg)'} — 若与下方合约表不一致，以合约表为准。

---

## 收益率曲线结构 — 2s10s / 2s3m

""" + _format_yield_curve_section() + f"""

---

## 曲线结构 — 逐合约对比今日 vs 参考峰 ({s.get('curve_structure',{}).get('ref_date','N/A')})
""" + _format_structure(s.get('curve_structure', {})) + f"""

---

## 分类详情

| 项目 | 值 |
|------|-----|
| 分类 | **{st['repair_classification']}** |
| 原因 | {st['repair_classification_reason']} |
| 结构修复已启动 | {'✅' if (st.get('structural_easing_detected') or st.get('deceleration_detected')) else '❌'} |
| formal repair | {'✅' if st['repair_detected'] else '❌'} |
| level repair | {'✅' if st['level_repair_detected'] else '❌'} |
| formal repair 起始日 | {st['repair_start_date'] or 'N/A'} |
| formal repair 幅度 | {st['repair_bp_from_peak']} bp |

{f'''⚠️ **注意**：当前分类为 `mixed_repair`，不代表买入信号；它只表示 SR3 冲击已钝化但尚未完成 level repair，且 benign repair 条件未完全满足。''' if st['repair_classification'] == 'mixed_repair' else ''}

---

## 信号组合速查 (research-only — 非交易指令)

| 条件 | 信号含义 |
|------|---------|
| 信用不扩 + SR3 钝化 | 鹰派动能衰竭，但短端预期尚未回落 |
| 信用不扩 + SR3 level repair + real yield 不再创新高 | 短端预期已明显回落，信用未恶化 |
| 信用不扩 + SR3 benign repair + 分子兑现 | 软着陆情景：利率回落 + 信用收窄 |
| SR3 钝化但不修复 | 暂停后利率继续上行，不构成拐点信号 |

---

## 合约收盘价 & 日变动
""" + _format_diffs(s.get('contract_diffs', [])) + f"""

---

*SR3 Repair Watch — {s['generated_at'][:10]}*
"""
    mp = OUT_DIR / "sr3_repair_watch_latest.md"
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md)
    return jp, mp


def _write_web_json(r):
    """转换嵌套分析结果为网页 JS 期望的扁平 JSON"""
    s, sh, rp = r, r["last_formal_shock"], r["recent_60d_peak"]
    cu, st, cs, cd = r["current"], r["state"], r.get("curve_structure", {}) or {}, r.get("contract_diffs", []) or []

    # ── Z26-H27-M27 曲线数据（兼容两种合约名格式）──
    curve_comparison = []
    curve_bp_changes = []
    # Z26/H27/M27 的两种命名：SR3Z2026 / SR3_Z26 等
    contracts_zmh = [("SR3Z2026","SR3_Z26","Z26"), ("SR3H2027","SR3_H27","H27"), ("SR3M2027","SR3_M27","M27")]
    ref_date_for_zmh = None
    try:
        if LONG_PATH.exists():
            long_all = pd.read_csv(LONG_PATH, parse_dates=["date"])
            long_all = long_all.sort_values("date")
            all_dates = sorted(long_all["date"].dt.date.unique())
            # 最近 5 个交易日
            recent = all_dates[-5:]
            for d in recent:
                snap = long_all[long_all["date"].dt.date == d]
                rates = {}
                for c_tv, c_usc, label in contracts_zmh:
                    row = snap[(snap["contract"] == c_tv) | (snap["contract"] == c_usc)]
                    rates[label] = round(float(row["implied_rate"].values[0]), 4) if len(row) > 0 else None
                curve_comparison.append({"date": str(d), "label": str(d), "rates": rates})
            # BP 变化 vs 最早日
            if len(recent) >= 2:
                first_date = recent[0]
                latest_date = recent[-1]
                first_snap = long_all[long_all["date"].dt.date == first_date]
                latest_snap = long_all[long_all["date"].dt.date == latest_date]
                for c_tv, c_usc, label in contracts_zmh:
                    fv = first_snap[(first_snap["contract"] == c_tv) | (first_snap["contract"] == c_usc)]["implied_rate"]
                    lv = latest_snap[(latest_snap["contract"] == c_tv) | (latest_snap["contract"] == c_usc)]["implied_rate"]
                    if len(fv) > 0 and len(lv) > 0:
                        curve_bp_changes.append({
                            "label": f"{label} ({first_date}→{latest_date})",
                            "bp_change": round(float(lv.values[0] - fv.values[0]) * 100, 1)
                        })
            if all_dates:
                ref_date_for_zmh = str(all_dates[-2])  # 前一天作为参考
    except Exception:
        pass

    # ── 信号矩阵 ──
    signal_matrix = [
        {"condition":"信用不扩 + SR3 钝化","meaning":"鹰派动能衰竭，但短端预期尚未回落"},
        {"condition":"信用不扩 + SR3 level repair + real yield 不再创新高","meaning":"短端预期已明显回落，信用未恶化"},
        {"condition":"信用不扩 + SR3 benign repair + 分子兑现","meaning":"软着陆情景：利率回落 + 信用收窄"},
        {"condition":"SR3 钝化但不修复","meaning":"暂停后利率继续上行，不构成拐点信号"},
    ]

    web = {
        "generated_at": r["generated_at"],
        "data_date": r["data_date"],
        "reference_peak": r["reference_mode"],
        "status": "Research-Only",
        "state": st["state_label"],
        "state_note": r["action"],
        "hawkish_impulse": st.get("in_hawkish_impulse", False),
        "deceleration": st.get("deceleration_detected", False) or st.get("structural_easing_detected", False),
        "deceleration_since": st.get("decel_start_date") or (cs.get("ref_date") if st.get("structural_easing_detected") else None),
        "level_repair": st.get("level_repair_detected", False),
        "classification": st["repair_classification"],
        "classification_reason": st["repair_classification_reason"],
        "repair": st.get("repair_detected", False),
        "repair_start_date": st.get("repair_start_date"),
        "repair_magnitude_bp": st.get("repair_bp_from_peak", 0),
        "mixed_repair_warning": "mixed_repair 不是买入信号；它只表示 SR3 冲击已钝化但尚未完成 level repair，且 benign repair 条件未完全满足。" if st["repair_classification"] == "mixed_repair" else "",
        "near_rate": cu["near_rate_pct"],
        "drawdown_from_peak_bp": cu["decline_from_ref_peak_bp"],
        "daily_change_bp": cu.get("contract_daily_bp") or cu.get("curve_move_bp"),
        "five_day_change_bp": cu.get("curve_move_5d_sum_bp"),
        "high_plateau": cu.get("on_elevated_plateau", False),
        "hy_oas": cu.get("hy_oas_bp"),
        "us10y": cu.get("us10y_pct"),
        "t10yie": cu.get("t10yie_pct"),
        "real_yield_nowcast": cu.get("real_yield_pct"),
        "constraints": {
            "research_only": True,
            "standalone_sr3_watch": True,
            "no_risk_os": True,
            "no_existing_dashboard_merge": True,
            "no_run_all": True,
            "no_position_impact": True,
            "deceleration_not_buy_signal": True,
        },
        "reference_peaks": [
            {"source":"Current Event Peak","date":sh["date"],"distance":f"{sh['days_ago']}d",
             "near_rate":sh["peak_near_rate_pct"],"height":f"{sh['shock_height_bp']}bp"},
            {"source":"Recent 60d Peak","date":rp["date"],"distance":f"{rp['days_ago']}d",
             "near_rate":rp["near_rate_pct"],"height":"—"},
        ],
        "signal_matrix": signal_matrix,
        "curve_comparison": curve_comparison,
        "curve_bp_changes": curve_bp_changes,
        "curve_warning": None if curve_comparison else "Z26-H27-M27 曲线数据不可用",
        "contract_diffs": cd,
        "retracement": r.get("retracement", []),
    }
    web_path = PROJECT_ROOT / "docs" / "sr3-watch" / "data" / "sr3_repair_watch_latest.json"
    with open(web_path, "w", encoding="utf-8") as f:
        json.dump(web, f, indent=2, ensure_ascii=False, default=str)
    return web_path


def main():
    # ── Step 0: 从 TradingView CSV 自动同步新数据到 sr3_long + 重算特征 ──
    _sync_from_tradingview()

    print("[SR3 Watch] Loading...")
    df = load_data()
    print(f"  {df['date'].min().date()} ~ {df['date'].max().date()} ({len(df)} days)")
    events = find_latest_shock(df)
    ls = events[-1] if events else {"shock_idx": 0, "shock_date": df["date"].iloc[0],
                                     "trough_idx": 0, "trough_date": df["date"].iloc[0],
                                     "peak_near_rate": df["near_rate"].iloc[-1], "shock_height_bp": 0}
    print(f"  Last formal shock: {ls['shock_date'].date() if hasattr(ls['shock_date'], 'date') else ls['shock_date']}")
    r = analyze(df, ls)
    print(f"  State: {r['state']['state_label']} | {r['state']['repair_classification']}")
    jp, mp = write_outputs(r)
    # 拷贝到项目根目录方便直接打开
    import shutil
    root_copy = PROJECT_ROOT / "_sr3_watch.md"
    shutil.copy(mp, root_copy)
    # 同步到 SR3 网页 → docs/sr3-watch/data/（扁平 JSON + MD）
    web_data = PROJECT_ROOT / "docs" / "sr3-watch" / "data"
    web_data.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp, web_data / "sr3_repair_watch_latest.md")
    web_json = _write_web_json(r)
    print(f"\nDone: {jp}\n      {mp}\n      → {root_copy}\n      → {web_json}")


if __name__ == "__main__":
    main()
