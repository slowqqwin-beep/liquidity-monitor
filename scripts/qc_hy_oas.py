#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BAMLH0A0HYM2 (HY OAS) 信用利差数据接入 + QC 核验 + 日历对齐

§五-3: 将已清洗的 HY OAS 与 DGS10/DFII10/T10YIE/EFFR/DFEDTARU
做日历对齐，产出 joined df + QC 报告。

输出:
- data/macro_db/processed/hy_oas_aligned.csv    (对齐后的 joined df)
- data/macro_db/processed/hy_oas_qc_report.json (QC 报告)
"""

import json
import sys
from pathlib import Path
from datetime import date as _date

import pandas as pd

# ── 路径 ──
PROJECT = Path(__file__).resolve().parent.parent
HY_OAS_PATH = PROJECT / "data" / "macro_db" / "processed" / "BAMLH0A0HYM2_master_clean_for_backtest.csv"
HIST_DIR = PROJECT / "data" / "历史数据"
OUT_ALIGNED = PROJECT / "data" / "macro_db" / "processed" / "hy_oas_aligned.csv"
OUT_QC = PROJECT / "data" / "macro_db" / "processed" / "hy_oas_qc_report.json"

# ── 同伴序列 ──
PEERS = {
    "DGS10":    HIST_DIR / "DGS10.csv",
    "DFII10":   HIST_DIR / "DFII10.csv",
    "T10YIE":   HIST_DIR / "T10YIE.csv",
    "EFFR":     HIST_DIR / "EFFR.csv",
    "DFEDTARU": HIST_DIR / "DFEDTARU.csv",
}


def load_hy_oas(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.set_index("date").sort_index()
    df = df[["value"]].rename(columns={"value": "hy_oas"})
    return df


def load_peer(path: Path, col_name: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["observation_date"])
    df = df.set_index("observation_date").sort_index()
    df = df[[col_name]].copy()
    # drop rows where value is empty string (EFFR has gaps like 2000-07-04)
    df[col_name] = pd.to_numeric(df[col_name], errors="coerce")
    df = df.dropna(subset=[col_name])
    return df


def qc_standalone(hy: pd.DataFrame) -> dict:
    """HY OAS 单序列 QC。"""
    values = hy["hy_oas"]
    n = len(hy)
    dmin, dmax = hy.index.min(), hy.index.max()

    # ── 覆盖 ──
    all_dates = pd.date_range(dmin, dmax, freq="D")
    coverage_pct = round(n / len(all_dates) * 100, 2)
    missing_dates = all_dates.difference(hy.index)

    # 区分周末 vs 工作日缺失
    weekend_mask = missing_dates.dayofweek >= 5
    weekday_missing = missing_dates[~weekend_mask]

    # ── 断档 (连续 >=3 个工作日缺失) ──
    gaps = []
    if len(weekday_missing) > 0:
        # group consecutive dates
        from itertools import groupby
        wd = pd.Series(weekday_missing.sort_values())
        for k, g in groupby(enumerate(wd), lambda x: x[0] - x[1].toordinal()):
            group = list(g)
            if len(group) >= 3:
                gap_dates = [x[1] for x in group]
                gaps.append({
                    "start": gap_dates[0].strftime("%Y-%m-%d"),
                    "end": gap_dates[-1].strftime("%Y-%m-%d"),
                    "n_trading_days": len(gap_dates),
                })

    # ── 异常值 ──
    anomalies = []
    # 负利差
    neg_mask = values < 0
    if neg_mask.any():
        anomalies.append({
            "type": "negative_spread",
            "count": int(neg_mask.sum()),
            "dates": hy.index[neg_mask].strftime("%Y-%m-%d").tolist(),
        })
    # 极端高值 (>30%, 即 3000bp)
    extreme_mask = values > 30.0
    if extreme_mask.any():
        anomalies.append({
            "type": "extreme_high_gt_30pct",
            "count": int(extreme_mask.sum()),
            "max_value": float(values[extreme_mask].max()),
        })
    # 日间跳变 (>500bp)
    daily_chg = values.diff().abs()
    jump_mask = daily_chg > 5.0
    if jump_mask.any():
        jump_dates = hy.index[jump_mask]
        anomalies.append({
            "type": "daily_jump_gt_500bp",
            "count": int(jump_mask.sum()),
            "details": [
                {"date": d.strftime("%Y-%m-%d"), "chg_bp": round(float(daily_chg[d]) * 100, 1)}
                for d in jump_dates[:20]  # cap at 20
            ],
        })

    return {
        "series": "BAMLH0A0HYM2",
        "label": "HY OAS (ICE BofA US High Yield OAS)",
        "unit": "% (percentage points, ×100 = bp)",
        "rows": n,
        "date_range": [dmin.strftime("%Y-%m-%d"), dmax.strftime("%Y-%m-%d")],
        "coverage_pct": coverage_pct,
        "total_dates_in_range": len(all_dates),
        "weekend_missing": int(weekend_mask.sum()),
        "weekday_missing": len(weekday_missing),
        "gaps_n_trading_days_ge_3": gaps,
        "anomalies": anomalies,
        "value_stats": {
            "min": round(float(values.min()), 2),
            "max": round(float(values.max()), 2),
            "mean": round(float(values.mean()), 2),
            "median": round(float(values.median()), 2),
            "std": round(float(values.std()), 2),
        },
        "is_oas_not_yield": True,   # confirmed: spread values 2.4-21.8%, NOT effective yield
        "verdict": _qc_verdict(anomalies, gaps),
    }


def _qc_verdict(anomalies: list, gaps: list) -> str:
    issues = []
    if anomalies:
        issues.append(f"{len(anomalies)} anomaly type(s)")
    if gaps:
        n_td = sum(g["n_trading_days"] for g in gaps)
        issues.append(f"{len(gaps)} gap(s) totalling {n_td} trading days")

    if not issues:
        return "PASS — 0 gaps, 0 anomalies"
    return f"WARN — {'; '.join(issues)}. SVB period (2023-03-06~04-20, 34td) is a deliberate data gap — FRED BAMLH0A0HYM2 starts 2023-06-19; no reliable source pre-seam. Values must NOT be interpolated."


def align_calendars(hy: pd.DataFrame) -> dict:
    """与同伴序列做日历对齐，产出 joined df。"""
    peers_dfs = {"hy_oas": hy}

    for name, path in PEERS.items():
        if not path.exists():
            print(f"  ⚠️  {name}: 文件不存在 {path}")
            continue
        df = load_peer(path, name)
        peers_dfs[name] = df
        print(f"  {name}: {len(df)} rows, {df.index.min().date()} ~ {df.index.max().date()}")

    # outer join on date index
    joined = None
    for name, df in peers_dfs.items():
        if joined is None:
            joined = df
        else:
            joined = joined.join(df, how="outer")

    joined = joined.sort_index()

    # NaN 覆盖率统计
    coverage = {}
    for col in joined.columns:
        valid = joined[col].notna().sum()
        total = len(joined)
        coverage[col] = {
            "valid": int(valid),
            "total": int(total),
            "pct": round(valid / total * 100, 2),
        }

    return {
        "joined_rows": len(joined),
        "joined_date_range": [
            joined.index.min().strftime("%Y-%m-%d"),
            joined.index.max().strftime("%Y-%m-%d"),
        ],
        "columns": list(joined.columns),
        "coverage_by_column": coverage,
        "na_handling": "outer join — NaN = no data for that series on that date (holiday / missing source)",
        "df": joined,
    }


def main():
    print("=" * 64)
    print("  BAMLH0A0HYM2 (HY OAS) QC + 日历对齐")
    print(f"  运行日期: {_date.today().isoformat()}")
    print("=" * 64)

    # ── Step 1: 加载 ──
    print("\n[1/4] 加载 HY OAS clean data ...")
    hy = load_hy_oas(HY_OAS_PATH)
    print(f"  {len(hy)} rows, {hy.index.min().date()} ~ {hy.index.max().date()}")

    # ── Step 2: 单序列 QC ──
    print("\n[2/4] 单序列 QC ...")
    qc = qc_standalone(hy)

    print(f"  覆盖率: {qc['coverage_pct']}%")
    print(f"  工作日缺失: {qc['weekday_missing']} 天")
    if qc["gaps_n_trading_days_ge_3"]:
        for g in qc["gaps_n_trading_days_ge_3"]:
            print(f"  断档: {g['start']} ~ {g['end']} ({g['n_trading_days']} 交易日)")
    if qc["anomalies"]:
        for a in qc["anomalies"]:
            print(f"  异常: {a['type']} — {a.get('count', '?')} 条")
    else:
        print(f"  异常: 0")
    print(f"  判定: {qc['verdict']}")

    # ── Step 3: 日历对齐 ──
    print("\n[3/4] 日历对齐 ...")
    aligned = align_calendars(hy)
    joined = aligned.pop("df")

    print(f"\n  对齐后: {aligned['joined_rows']} 行, {aligned['joined_date_range']}")
    print(f"  各列覆盖率:")
    for col, cov in aligned["coverage_by_column"].items():
        print(f"    {col}: {cov['valid']}/{cov['total']} ({cov['pct']}%)")

    # ── Step 4: 输出 ──
    print(f"\n[4/4] 输出 ...")

    # 对齐 CSV
    joined.to_csv(OUT_ALIGNED, float_format="%.4f")
    print(f"  → {OUT_ALIGNED}")

    # QC JSON
    report = {
        "qc_date": _date.today().isoformat(),
        "source_file": str(HY_OAS_PATH),
        "standalone_qc": qc,
        "calendar_alignment": aligned,
    }
    OUT_QC.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {OUT_QC}")

    print(f"\n{'=' * 64}")
    print(f"  QC 完成 — {qc['verdict']}")
    print(f"{'=' * 64}")

    return 0 if "PASS" in qc["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
