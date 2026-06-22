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

输入: sr3_curve_features.csv + macro_research_panel.csv
输出: sr3_repair_watch_latest.json + sr3_repair_watch_latest.md
约束: Research-Only — 不接 Risk OS / dashboard / run_all.py / 仓位
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_DIR = PROJECT_ROOT / "data" / "macro_backtest" / "input"
PANEL_PATH = PROJECT_ROOT / "data" / "macro_db" / "processed" / "macro_research_panel.csv"
OUT_DIR = PROJECT_ROOT / "data" / "macro_backtest" / "research"
OUT_DIR.mkdir(parents=True, exist_ok=True)

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
    panel = pd.read_csv(PANEL_PATH, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df = sr3.merge(panel[[
        "date", "BAMLH0A0HYM2", "HY_OAS_available", "DGS10",
        "HY_OAS_chg_20d", "DGS10_chg_20d",
        "real_yield_nowcast", "real_yield_basis_diff", "credit_signal_status",
    ]], on="date", how="left")
    return df.dropna(subset=["near_rate"]).reset_index(drop=True)


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


def analyze(df, last_shock):
    si = last_shock["shock_idx"]
    shock_peak = last_shock["peak_near_rate"]
    shock_date = last_shock["shock_date"]
    li = len(df) - 1
    ld = df["date"].iloc[li]
    ds = li - si

    # Recent 60d peak as fallback reference
    rws = max(0, li - 60)
    rdf = df.iloc[rws:li + 1]
    rpi = rdf["near_rate"].idxmax()
    rpr = df["near_rate"].iloc[rpi]
    rpd = df["date"].iloc[rpi]

    use_formal = ds <= 60
    ref_rate = shock_peak if use_formal else rpr
    ref_date = shock_date if use_formal else rpd
    ref_idx = si if use_formal else rpi
    ref_label = "formal shock" if use_formal else "recent 60d peak"

    cr = df.iloc[li]
    cnr = cr["near_rate"]
    cmv = cr.get("curve_move_bp", np.nan)
    c5s = cr.get("curve_move_5d_sum", np.nan)

    # Impulse check (near_rate already in %; 2bp ≈ 0.02%)
    near_peak = abs(cnr - ref_rate) < 0.02
    rising = (not pd.isna(c5s)) and c5s > 1.0
    in_impulse = near_peak or ((li - rpi) <= 3 and rising)

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
            hoc = rr.get("HY_OAS_chg_20d", 0); dc = rr.get("DGS10_chg_20d", 0)
            hoc = 0 if pd.isna(hoc) else hoc; dc = 0 if pd.isna(dc) else dc
            hoc_bp = hoc * 100
            dgs10_bp = dc * 100
            hs = hoc_bp < PARAMS["credit_hyoas_benign_max_bp"]
            df10 = dgs10_bp < PARAMS["credit_dgs10_declining_bp"]
            hstr = hoc_bp > PARAMS["credit_hyoas_malign_min_bp"]
            if hs and df10:
                cls = "benign_repair"; reason = "HY OAS stable/declining + DGS10 declining (soft landing)"
            elif hstr:
                cls = "malign_repair"; reason = "HY OAS widening (credit stress)"
            elif df10:
                cls = "mixed_repair"; reason = "DGS10 declining but HY OAS moderately widening"
            else:
                cls = "mixed_repair"; reason = "Mixed signals, no clear benign/malign pattern"
    elif decel:
        cls = "decel_no_repair"; reason = "Deceleration detected but no repair yet"
    elif in_impulse:
        cls = "still_in_impulse"; reason = "Still in hawkish impulse phase"

    # State (descriptive only — research-only, not actionable)
    if cls == "benign_repair":
        st, sl, act = 4, "State 4: Benign Repair", "短端预期：benign repair 确认（利率从参考峰回落 + 信用稳定/收窄）"
    elif level_repair:
        st, sl, act = 3, "State 3: Level Repair", "短端预期：已从参考峰回落 ≥10bp（level repair）；信用端分类见下方"
    elif decel:
        st, sl, act = 2, "State 2: Deceleration", "短端预期：已钝化（曲线移动 <1.5bp），但尚未出现实质性/持续修复"
    else:
        st, sl, act = 1, "State 1: Hawkish Impulse", "短端预期：鹰派冲击未消退；曲线仍在上行或高台维持"

    lr = df.iloc[li]
    ho = lr.get("BAMLH0A0HYM2", None)
    ho = round(float(ho), 2) if not pd.isna(ho) else None
    d10 = lr.get("DGS10", None)
    d10 = round(float(d10), 2) if not pd.isna(d10) else None
    ry = lr.get("real_yield_nowcast", None)
    ry = round(float(ry), 4) if not pd.isna(ry) else None

    return {
        "generated_at": datetime.now().isoformat(),
        "data_date": str(ld.date()),
        "data_age_days": (date.today() - ld.date()).days,
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
                    "curve_move_5d_sum_bp": round(float(c5s), 2) if not pd.isna(c5s) else None,
                    "decline_from_ref_peak_bp": round(float((ref_rate - cnr) * 100), 2),
                    "on_elevated_plateau": bool(cnr > 3.5),
                    "hy_oas_bp": round(ho * 100, 1) if ho is not None else None,
                    "hy_oas_available": bool(lr.get("HY_OAS_available", False)) if not pd.isna(lr.get("HY_OAS_available")) else False,
                    "dgs10_pct": d10, "real_yield_nowcast_pct": ry},
        "state": {"state_number": st, "state_label": sl,
                  "in_hawkish_impulse": st == 1,
                  "deceleration_detected": decel, "decel_start_date": str(dsd.date()) if dsd else None,
                  "level_repair_detected": level_repair,
                  "repair_detected": repair, "repair_start_date": str(rsd.date()) if rsd else None,
                  "repair_bp_from_peak": round(float(rbp), 2),
                  "repair_classification": cls, "repair_classification_reason": reason},
        "action": act,
        "constraints": {"research_only": True, "not_in_risk_os": True,
                        "not_in_dashboard": True, "not_in_run_all": True,
                        "deceleration_not_buy_signal": True},
    }


def write_outputs(r):
    jp = OUT_DIR / "sr3_repair_watch_latest.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False, default=str)

    s = r; sh = s["last_formal_shock"]; rp = s["recent_60d_peak"]
    cu = s["current"]; st = s["state"]
    em = {1: "🔴", 2: "🟡", 3: "🟢", 4: "🟢"}
    md = f"""# SR3 修复监控 — 当前状态

> **生成时间**: {s['generated_at'][:19]} | **数据日**: {s['data_date']}（{s['data_age_days']}d ago）
> **参考峰值**: {s['reference_mode']} | **状态**: Research-Only

---

## {em.get(st['state_number'], '⚪')} {st['state_label']}

> {s['action']}

---

## 四个关键问题

| # | 问题 | 答案 |
|---|------|------|
| 1 | 处于 hawkish impulse？ | **{'是 🔴' if st['in_hawkish_impulse'] else '否'}** |
| 2 | 进入 deceleration？ | **{'是 🟡 — ' + (st['decel_start_date'] or '') if st['deceleration_detected'] else '否'}** |
| 3 | 发生 level repair？ | **{'是 🟢' if st['level_repair_detected'] else '否'}** |
| 4 | 修复分类 | **{st['repair_classification']}** |

---

## 参考峰值

| 来源 | 日期 | 距今 | near_rate | 高度 |
|------|------|------|-----------|------|
| Formal Shock | {sh['date']} | {sh['days_ago']}d | {sh['peak_near_rate_pct']}% | {sh['shock_height_bp']}bp |
| Recent 60d Peak | {rp['date']} | {rp['days_ago']}d | {rp['near_rate_pct']}% | — |

当前使用: **{s['reference_mode']}**

---

## 当前快照

| 指标 | 值 |
|------|-----|
| near_rate | {cu['near_rate_pct']}% |
| 较参考峰回落 | {cu['decline_from_ref_peak_bp']} bp |
| 当日变动 | {cu['curve_move_bp']} bp |
| 5d 累计 | {cu['curve_move_5d_sum_bp']} bp |
| 高台 (>3.5%) | {'⚠️ 是' if cu['on_elevated_plateau'] else '否'} |
| HY OAS | {cu['hy_oas_bp'] or 'N/A'} bp |
| DGS10 | {cu['dgs10_pct'] or 'N/A'}% |
| Real Yield Nowcast | {cu['real_yield_nowcast_pct'] or 'N/A'}% |

---

## 分类详情

| 项目 | 值 |
|------|-----|
| 分类 | **{st['repair_classification']}** |
| 原因 | {st['repair_classification_reason']} |
| level_repair | {'✅' if st['level_repair_detected'] else '❌'} |
| repair | {'✅' if st['repair_detected'] else '❌'} |
| 修复起始日 | {st['repair_start_date'] or 'N/A'} |
| 修复幅度 | {st['repair_bp_from_peak']} bp |

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

## 约束确认

| 约束 | 状态 |
|------|------|
| Research-Only | ✅ |
| 不接 Risk OS / dashboard / run_all.py | ✅ |
| 不影响仓位 | ✅ |
| SR3 deceleration ≠ buy signal | ✅ |

---

*SR3 Repair Watch — {s['generated_at'][:10]}*
"""
    mp = OUT_DIR / "sr3_repair_watch_latest.md"
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md)
    return jp, mp


def main():
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
    print(f"\nDone: {jp}\n      {mp}")


if __name__ == "__main__":
    main()
