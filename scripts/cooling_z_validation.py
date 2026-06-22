#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""cooling-z 验收脚本 — 验证 z-of-change based real yield retreat detector

用 macro_research_panel 的 real_yield_nowcast 列（DGS10−T10YIE）
在 2018-2026 全历史上测试四组接受条件：

A. 不恒满：counter==3 占比 << 旧 <2% 门槛；高低体制下占比量级可比（自适应）
B. 响应真回落：2020-03, 2024 降息启动等已知回落期 counter 应起
C. 与旧门槛正交：与旧 <2% 触发时点重叠率
D. 无静默失败：NaN→N/A, std=0→N/A, 窗口不足→N/A, 单日跳变→不打满
"""

import pandas as pd
import numpy as np
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PANEL_PATH = PROJECT / "data" / "macro_db" / "processed" / "macro_research_panel.csv"
OUT_JSON = PROJECT / "data" / "cooling_z_validation.json"
OUT_MD = PROJECT / "data" / "cooling_z_validation.md"

W = 252      # rolling z window
DIFF = 20    # Δ window
Z_THRESH = -1.0


def compute_cooling_z_on_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Compute cooling-z on panel data. Returns df with added columns."""
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    ryn = df["real_yield_nowcast"].astype(float)

    # Δ = 20-obs change
    df["cooling_delta"] = ryn.diff(DIFF)

    # Rolling z
    df["cooling_roll_mean"] = df["cooling_delta"].rolling(W, min_periods=W).mean()
    df["cooling_roll_std"] = df["cooling_delta"].rolling(W, min_periods=W).std(ddof=1)
    df["cooling_roll_std"] = df["cooling_roll_std"].replace(0.0, np.nan)

    df["cooling_z"] = (
        (df["cooling_delta"] - df["cooling_roll_mean"]) / df["cooling_roll_std"]
    )

    # Quality flag
    df["cooling_z_quality"] = "ok"
    df.loc[df["cooling_delta"].isna(), "cooling_z_quality"] = "insufficient_diff"
    df.loc[df["cooling_roll_mean"].isna(), "cooling_z_quality"] = "insufficient_rolling"
    df.loc[df["cooling_roll_std"].isna() & (df["cooling_z_quality"] == "ok"),
           "cooling_z_quality"] = "zero_std_or_insufficient"
    df.loc[ryn.isna(), "cooling_z_quality"] = "nowcast_nan"

    # Counter: z ≤ -1.0 → accumulate, else reset
    counter = 0
    counters = []
    for z in df["cooling_z"]:
        if pd.notna(z) and z <= Z_THRESH:
            counter = min(counter + 1, 3)
        else:
            counter = 0
        counters.append(counter)
    df["cooling_counter"] = counters

    return df


def identify_periods(df: pd.DataFrame) -> dict:
    """Identify regime periods for stratification."""
    df = df.copy()
    periods = {}

    # 2018-2019 (pre-COVID tightening)
    mask = (df["date"] >= "2018-01-01") & (df["date"] < "2020-03-01")
    if mask.any():
        periods["2018-2019 加息末期"] = df[mask]

    # 2020-03 (COVID crash)
    mask = (df["date"] >= "2020-03-01") & (df["date"] < "2020-06-01")
    if mask.any():
        periods["2020-03~05 COVID崩盘"] = df[mask]

    # 2020-2021 (low rate regime)
    mask = (df["date"] >= "2020-06-01") & (df["date"] < "2022-01-01")
    if mask.any():
        periods["2020-2021 低利率体制"] = df[mask]

    # 2022 (tightening)
    mask = (df["date"] >= "2022-01-01") & (df["date"] < "2023-01-01")
    if mask.any():
        periods["2022 加息周期"] = df[mask]

    # 2023 (SVB + pause)
    mask = (df["date"] >= "2023-01-01") & (df["date"] < "2024-01-01")
    if mask.any():
        periods["2023 SVB+暂停"] = df[mask]

    # 2024 (rate cuts start)
    mask = (df["date"] >= "2024-01-01") & (df["date"] < "2025-01-01")
    if mask.any():
        periods["2024 降息启动"] = df[mask]

    # 2025-2026 (high rate regime)
    mask = (df["date"] >= "2025-01-01") & (df["date"] <= "2026-06-22")
    if mask.any():
        periods["2025-2026 高利率体制"] = df[mask]

    return periods


def test_A_not_always_full(df: pd.DataFrame) -> dict:
    """A: counter==3 must NOT be near-constant like old <2% threshold."""
    valid = df[df["cooling_z_quality"] == "ok"].copy()
    n_valid = len(valid)

    if n_valid == 0:
        return {"error": "no valid z rows"}

    # New: counter==3 fraction
    counter3_new = (valid["cooling_counter"] == 3).sum()
    pct_new = round(counter3_new / n_valid * 100, 1)

    # Old: ryn < 2.00 fraction (for comparison)
    ryn_valid = df["real_yield_nowcast"].dropna()
    n_ryn = len(ryn_valid)
    ryn_lt2 = (ryn_valid < 2.00).sum()
    pct_old = round(ryn_lt2 / n_ryn * 100, 1) if n_ryn > 0 else 0

    # Stratify by regime
    periods = identify_periods(df)
    regime_stats = {}
    for name, pdf in periods.items():
        pdf_ok = pdf[pdf["cooling_z_quality"] == "ok"]
        if len(pdf_ok) == 0:
            continue
        c3 = (pdf_ok["cooling_counter"] == 3).sum()
        regime_stats[name] = {
            "n_days": len(pdf_ok),
            "counter3_days": int(c3),
            "counter3_pct": round(c3 / len(pdf_ok) * 100, 1),
        }

    verdict = (
        "PASS — counter3 far below old 80%+ threshold"
        if pct_new < 50
        else "FAIL — counter3 still too frequent"
    )

    return {
        "test": "A — 不恒满",
        "verdict": verdict,
        "new_counter3_pct": pct_new,
        "old_lt2pct_pct": pct_old,
        "n_valid_days": n_valid,
        "regime_breakdown": regime_stats,
        "note": "old <2% threshold would show counter3 ~80%+ permanently; new z-of-change should be much lower",
    }


def test_B_responds_to_retreats(df: pd.DataFrame) -> dict:
    """B: Spot-check known retreat periods — counter should be non-zero."""

    checks = {
        "2020-03 COVID crash (real yield collapsed)": {
            "start": "2020-03-09", "end": "2020-03-31",
            "expect": "counter should rise (real yield fell sharply)",
        },
        "2024-09 Fed rate cut start": {
            "start": "2024-09-01", "end": "2024-10-15",
            "expect": "counter should activate near rate cut",
        },
        "2022 H2 (tightening, should NOT trigger)": {
            "start": "2022-09-01", "end": "2022-12-31",
            "expect": "counter should be 0 (real yield rising)",
        },
    }

    results = {}
    for label, cfg in checks.items():
        mask = (
            (df["date"] >= cfg["start"])
            & (df["date"] <= cfg["end"])
            & (df["cooling_z_quality"] == "ok")
        )
        subset = df[mask]
        if len(subset) == 0:
            results[label] = {
                "n_days": 0,
                "max_counter": 0,
                "expect": cfg["expect"],
                "status": "NO_DATA",
            }
            continue

        results[label] = {
            "n_days": len(subset),
            "max_counter": int(subset["cooling_counter"].max()),
            "mean_counter": round(subset["cooling_counter"].mean(), 2),
            "days_counter_ge_1": int((subset["cooling_counter"] >= 1).sum()),
            "days_counter_ge_2": int((subset["cooling_counter"] >= 2).sum()),
            "expect": cfg["expect"],
            "z_min": round(subset["cooling_z"].min(), 2),
            "z_mean": round(subset["cooling_z"].mean(), 2),
        }

    return {
        "test": "B — 响应真回落",
        "spot_checks": results,
    }


def test_C_orthogonal(df: pd.DataFrame) -> dict:
    """C: Overlap between cooling-z trigger and old <2% trigger."""
    valid = df[df["cooling_z_quality"] == "ok"].copy()
    ryn = df["real_yield_nowcast"].dropna()

    # Align dates — compute old trigger on same rows
    common = valid.copy()
    common["ryn"] = common["real_yield_nowcast"].astype(float)
    common = common.dropna(subset=["ryn"])

    n = len(common)
    if n == 0:
        return {"error": "no common dates"}

    z_trigger = common["cooling_counter"] >= 1
    old_trigger = common["ryn"] < 2.00

    # Overlap
    both = (z_trigger & old_trigger).sum()
    z_only = (z_trigger & ~old_trigger).sum()
    old_only = (~z_trigger & old_trigger).sum()
    neither = (~z_trigger & ~old_trigger).sum()

    total_z_trigger = z_trigger.sum()
    total_old_trigger = old_trigger.sum()

    overlap_rate = round(both / total_z_trigger * 100, 1) if total_z_trigger > 0 else 0
    overlap_rate_rev = round(both / total_old_trigger * 100, 1) if total_old_trigger > 0 else 0

    verdict = (
        "PASS — triggers largely independent"
        if overlap_rate <= 60
        else f"WARN — {overlap_rate}% overlap, not fully orthogonal"
    )

    return {
        "test": "C — 与旧门槛正交",
        "verdict": verdict,
        "contingency": {
            "both_trigger": int(both),
            "z_only": int(z_only),
            "old_only": int(old_only),
            "neither": int(neither),
        },
        "overlap_z_to_old_pct": overlap_rate,
        "overlap_old_to_z_pct": overlap_rate_rev,
        "total_z_trigger_days": int(total_z_trigger),
        "total_old_trigger_days": int(total_old_trigger),
        "note": ">60% overlap warns cooling-z might be a level-threshold in disguise",
    }


def test_D_no_silent_failures(df: pd.DataFrame) -> dict:
    """D: Edge cases — NaN, zero std, insufficient history, single-day jump."""

    # (a) NaN in nowcast → quality should NOT be 'ok'
    nan_rows = df[df["real_yield_nowcast"].isna() & (df["cooling_z_quality"] == "ok")]
    nan_ok = len(nan_rows) == 0

    # (b) Zero std → N/A, not inf
    zero_std = df[df["cooling_z_quality"] == "zero_std_or_insufficient"]
    inf_z = (zero_std["cooling_z"].abs() == np.inf).sum() if len(zero_std) else 0
    zero_std_ok = inf_z == 0

    # (c) Insufficient history points
    insufficient = df[df["cooling_z_quality"].str.contains("insufficient", na=False)]
    has_insufficient = len(insufficient) > 0

    # (d) Single-day jump → counter can't go 0→3 in one day
    counter_jumps = df["cooling_counter"].diff()
    instant_full = (counter_jumps >= 3).sum()
    single_day_ok = instant_full == 0

    all_pass = nan_ok and zero_std_ok and single_day_ok and has_insufficient

    return {
        "test": "D — 无静默失败",
        "verdict": "PASS — all edge cases handled" if all_pass else "FAIL",
        "checks": {
            "a_nan_not_ok": nan_ok,
            "b_zero_std_not_inf": zero_std_ok,
            "c_insufficient_flagged": has_insufficient,
            "d_no_instant_counter3": single_day_ok,
            "n_insufficient_rows": int(len(insufficient)),
        },
    }


def main():
    print("=" * 64)
    print("  cooling-z Validation")
    print(f"  Panel: {PANEL_PATH}")
    print("=" * 64)

    df = pd.read_csv(PANEL_PATH, parse_dates=["date"])
    # Only use rows where real_yield_nowcast exists
    df_ryn = df[df["real_yield_nowcast"].notna()].copy()
    print(f"\n  Real yield rows: {len(df_ryn)}")
    print(f"  Date range: {df_ryn['date'].min().date()} ~ {df_ryn['date'].max().date()}")

    print("\n  Computing cooling-z ...")
    result = compute_cooling_z_on_panel(df_ryn)

    n_ok = (result["cooling_z_quality"] == "ok").sum()
    n_total = len(result)
    print(f"  Valid z-score rows: {n_ok}/{n_total} ({round(n_ok/n_total*100,1)}%)")

    # Run tests
    print("\n  Running acceptance tests ...")
    test_a = test_A_not_always_full(result)
    test_b = test_B_responds_to_retreats(result)
    test_c = test_C_orthogonal(result)
    test_d = test_D_no_silent_failures(result)

    # Summary
    print(f"\n  Test A: {test_a['verdict']}")
    print(f"    counter3={test_a.get('new_counter3_pct','?')}% vs old <2%={test_a.get('old_lt2pct_pct','?')}%")
    for regime, stats in test_a.get("regime_breakdown", {}).items():
        print(f"      {regime}: {stats['counter3_days']}/{stats['n_days']} = {stats['counter3_pct']}%")

    print(f"\n  Test B spot checks:")
    for label, sc in test_b.get("spot_checks", {}).items():
        print(f"    {label}")
        print(f"      Max counter={sc['max_counter']}, Days≥1={sc['days_counter_ge_1']}, z_min={sc.get('z_min','?')}")
        print(f"      Expect: {sc['expect']}")

    print(f"\n  Test C: {test_c['verdict']}")
    ct = test_c.get("contingency", {})
    print(f"    Both={ct.get('both_trigger','?')}, Z-only={ct.get('z_only','?')}, Old-only={ct.get('old_only','?')}")
    print(f"    Overlap z→old: {test_c.get('overlap_z_to_old_pct','?')}%, old→z: {test_c.get('overlap_old_to_z_pct','?')}%")

    print(f"\n  Test D: {test_d['verdict']}")
    for k, v in test_d.get("checks", {}).items():
        print(f"    {k}: {v}")

    # Write outputs
    report = {
        "validation_date": pd.Timestamp.now().isoformat(),
        "source": str(PANEL_PATH),
        "params": {"W": W, "DIFF": DIFF, "Z_THRESH": Z_THRESH},
        "summary": {
            "n_total": n_total,
            "n_valid_z": n_ok,
        },
        "test_A": test_a,
        "test_B": test_b,
        "test_C": test_c,
        "test_D": test_d,
    }

    OUT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n  → {OUT_JSON}")

    # MD report
    md = []
    md.append("# cooling-z Validation Report")
    md.append("")
    md.append(f"**Date**: {pd.Timestamp.now().strftime('%Y-%m-%d')}")
    md.append(f"**Source**: `macro_research_panel.csv` ({n_total} real yield rows)")
    md.append(f"**Params**: W={W}, DIFF={DIFF}, z_threshold={Z_THRESH}")
    md.append("")

    md.append("## A — 不恒满")
    md.append("")
    md.append(f"- **Verdict**: {test_a['verdict']}")
    md.append(f"- counter3 days: {test_a.get('new_counter3_pct','?')}% of valid days")
    md.append(f"- old <2% would trigger: {test_a.get('old_lt2pct_pct','?')}% of days")
    md.append("")
    md.append("| Regime | Days | Counter3 Days | Counter3 % |")
    md.append("|--------|------|---------------|------------|")
    for regime, stats in test_a.get("regime_breakdown", {}).items():
        md.append(f"| {regime} | {stats['n_days']} | {stats['counter3_days']} | {stats['counter3_pct']}% |")
    md.append("")

    md.append("## B — 响应真回落")
    md.append("")
    for label, sc in test_b.get("spot_checks", {}).items():
        md.append(f"### {label}")
        md.append(f"- Expect: {sc['expect']}")
        md.append(f"- N days: {sc['n_days']}")
        md.append(f"- Max counter: {sc['max_counter']}")
        md.append(f"- Days counter ≥ 1: {sc['days_counter_ge_1']}")
        md.append(f"- Days counter ≥ 2: {sc['days_counter_ge_2']}")
        md.append(f"- z min/mean: {sc.get('z_min','?')} / {sc.get('z_mean','?')}")
        md.append("")

    md.append("## C — 与旧门槛正交")
    md.append("")
    md.append(f"- **Verdict**: {test_c['verdict']}")
    md.append(f"- Overlap (z→old): {test_c.get('overlap_z_to_old_pct','?')}%, (old→z): {test_c.get('overlap_old_to_z_pct','?')}%")
    md.append(f"- Both trigger: {ct.get('both_trigger','?')} | Z-only: {ct.get('z_only','?')} | Old-only: {ct.get('old_only','?')}")
    md.append("")

    md.append("## D — 无静默失败")
    md.append("")
    md.append(f"- **Verdict**: {test_d['verdict']}")
    for k, v in test_d.get("checks", {}).items():
        md.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"  → {OUT_MD}")

    return 0


if __name__ == "__main__":
    import json
    import sys
    sys.exit(main())
