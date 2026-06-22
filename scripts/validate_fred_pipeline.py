#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FRED / HY OAS 研究链路同步验收
================================
检查 CI 管线下游五个关键产物的最新日期是否一致。
用法: uv run python scripts/validate_fred_pipeline.py
"""

import json
import pandas as pd
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parent.parent

CHECKS = {
    "series.json": ROOT / "data" / "series.json",
    "DGS10 (历史数据)": ROOT / "data" / "历史数据" / "DGS10.csv",
    "HY OAS clean master": ROOT / "data" / "历史数据" / "BAMLH0A0HYM2_master_clean_for_backtest.csv",
    "macro_research_panel": ROOT / "data" / "macro_db" / "processed" / "macro_research_panel.csv",
}

TOLERANCE_DAYS = 1  # FRED 延迟容忍


def get_latest_series_json_date(p: Path) -> date:
    with open(p) as f:
        d = json.load(f)
    max_d = None
    for k, rows in d.items():
        if not rows or not isinstance(rows, list):
            continue
        last = rows[-1]
        ds = last.get("date", last.get("observation_date", None))
        if ds:
            try:
                dt = pd.Timestamp(ds).date()
                if max_d is None or dt > max_d:
                    max_d = dt
            except Exception:
                pass
    return max_d


def get_latest_csv_date(p: Path, date_col: str = None) -> date:
    df = pd.read_csv(p)
    if date_col is None:
        for c in ["observation_date", "date", "DATE"]:
            if c in df.columns:
                date_col = c
                break
    if date_col is None:
        raise ValueError(f"Cannot find date column in {p}, columns: {df.columns.tolist()}")
    return pd.to_datetime(df[date_col]).max().date()


def get_daily_report_date() -> date | None:
    today = date.today()
    candidates = sorted(ROOT.glob("daily_archive/daily_*.md"), reverse=True)
    if candidates:
        return pd.Timestamp(candidates[0].stem.replace("daily_", "")).date()
    return None


def main():
    results = {}

    # 1. series.json
    sj = get_latest_series_json_date(CHECKS["series.json"])
    results["series.json"] = sj

    # 2. DGS10
    dgs = get_latest_csv_date(CHECKS["DGS10 (历史数据)"])
    results["DGS10 (历史数据)"] = dgs

    # 3. HY OAS clean master
    hy = get_latest_csv_date(CHECKS["HY OAS clean master"])
    results["HY OAS clean master"] = hy

    # 4. macro_research_panel
    try:
        mp = get_latest_csv_date(CHECKS["macro_research_panel"])
        results["macro_research_panel"] = mp
    except FileNotFoundError:
        results["macro_research_panel"] = None

    # 5. daily report
    dr = get_daily_report_date()
    results["daily report"] = dr

    # --- 汇总 ---
    print("=" * 60)
    print("FRED / HY OAS 研究链路同步验收")
    print(f"验收时间: {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 60)

    for label, val in results.items():
        mark = ""
        if val is None:
            mark = "  [MISSING]"
        print(f"  {label:<30} {str(val):<14}{mark}")

    # 对齐检查: 取有效日期中的最大值作为锚
    valid = {k: v for k, v in results.items() if v is not None}
    if not valid:
        print("\n[FAIL] No valid data, check CI pipeline")
        return 1

    anchor = max(valid.values())
    print(f"\nAnchor date: {anchor}")

    all_ok = True
    for label, val in results.items():
        if val is None:
            print(f"  [FAIL] {label}: missing")
            all_ok = False
        elif abs((anchor - val).days) > TOLERANCE_DAYS:
            print(f"  [FAIL] {label}: {val} (lag {abs((anchor - val).days)}d)")
            all_ok = False
        elif val != anchor:
            print(f"  [WARN] {label}: {val} (1d lag, FRED tolerance)")

    if all_ok:
        print("\n[PASS] All 5 dates synced — FRED/HY OAS pipeline stable")
        return 0
    else:
        print(f"\n[FAIL] Dates out of sync, check .github/workflows/update-data.yml")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
