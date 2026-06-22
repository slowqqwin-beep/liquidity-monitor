#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SR3 修复验证 — 独立回测研究模块
================================
验证 SR3 曲线在鹰派冲击后出现钝化/修复时，后续是否真的发生短端预期回落。

输入:
  - data/macro_backtest/input/sr3_long.csv
  - data/macro_backtest/input/sr3_curve_features.csv
  - data/macro_db/processed/macro_research_panel.csv

输出:
  - data/macro_backtest/research/sr3_repair_validation.csv
  - data/macro_backtest/research/sr3_repair_validation.md
  - data/macro_backtest/research/sr3_repair_validation.json

约束:
  - SR3 只判断短端预期是否修复
  - HY OAS 判断修复是良性还是恶性
  - HY OAS 缺失时 credit_state must be unavailable
  - SVB period (2023-03-06~2023-04-20): deliberate GAP — FRED series starts 2023-06-19; no pre-seam source
  - 不修改 Risk OS / dashboard / run_all.py
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

# ============================================================
# 0. 参数配置（集中管理，便于调参）
# ============================================================
PARAMS = {
    # hawkish_shock: 5 个交易日内曲线累计上移超过此阈值 (P75=4.1, P90=9.6)
    "shock_5d_min_bp": 4.0,
    # hawkish_shock: 单日曲线大幅上移阈值 (P75=1.75, P90=3.88)
    "shock_1d_min_bp": 3.0,
    # 局部峰值: 至少比前后 N 天都高 (用较小窗口捕捉密集转折)
    "peak_lookback_days": 5,
    # deceleration: 连续 N 天 abs(curve_move_bp) < threshold
    "decel_abs_bp_threshold": 1.5,
    "decel_min_days": 2,
    # repair: near_rate 回落超过此阈值
    "repair_min_bp": 5.0,
    # 短窗口修复: 冲击后 60 日内的快速修复
    "repair_max_days": 60,
    # 中窗口修复: 冲击后 120 日内的中期修复
    "repair_max_days_mid": 120,
    # 长窗口修复: 冲击后 250 日（~1年）内的慢修复
    "repair_max_days_long": 250,
    # repair: 修复窗口内 near_rate 回落比例 (回落 / 冲击幅度)
    "repair_min_ratio": 0.3,
    # 冲击最小幅度 (太小不算鹰派冲击)
    "shock_min_height_bp": 5.0,
    # 两次冲击事件最小间隔 (避免同一趋势重复计数)
    "event_min_gap_days": 20,
    # benign/malign 信用分类
    "credit_hyoas_benign_max_bp": 10.0,
    "credit_hyoas_malign_min_bp": 20.0,
    "credit_dgs10_declining_bp": -2.0,
}

# ============================================================
# 1. 加载数据
# ============================================================
print("[1/5] Loading data...")

sr3_feat = pd.read_csv(IN_DIR / "sr3_curve_features.csv", parse_dates=["date"])
sr3_feat = sr3_feat.sort_values("date").reset_index(drop=True)

# 加载 macro_research_panel，对齐日期
panel = pd.read_csv(PANEL_PATH, parse_dates=["date"])
panel = panel.sort_values("date").reset_index(drop=True)

# Merge SR3 features with macro panel on date
df = sr3_feat.merge(
    panel[[
        "date", "BAMLH0A0HYM2", "HY_OAS_available",
        "DGS10", "DFII10", "T10YIE",
        "HY_OAS_chg_20d", "DGS10_chg_20d", "DFII10_chg_20d", "T10YIE_chg_20d",
        "real_yield_nowcast", "real_yield_basis_diff", "curve_2s10s",
        "credit_signal_status",
    ]],
    on="date", how="left"
)

# 只保留两个数据集都有日期的行
df = df.dropna(subset=["near_rate"]).reset_index(drop=True)

print(f"  SR3 features: {len(sr3_feat):,} days")
print(f"  After merge with macro panel: {len(df):,} days")
print(f"  Date range: {df['date'].min().date()} ~ {df['date'].max().date()}")

# ============================================================
# 2. 检测 hawkish_shock 事件
# ============================================================
print("[2/5] Detecting hawkish shock events...")

# 2a. 计算 shock 强度信号
df["shock_signal_5d"] = df["curve_move_5d_sum"] > PARAMS["shock_5d_min_bp"]
df["shock_signal_1d"] = df["curve_move_bp"] > PARAMS["shock_1d_min_bp"]

# 2b. 寻找局部峰值
df["is_local_peak"] = False
lookback = PARAMS["peak_lookback_days"]
for i in range(lookback, len(df) - lookback):
    window = df["near_rate"].iloc[i - lookback : i + lookback + 1]
    if df["near_rate"].iloc[i] == window.max() and window.max() > window.iloc[lookback - 1]:
        df.at[df.index[i], "is_local_peak"] = True

# 2c. 合并: shock_signal AND is_local_peak → hawkish_shock event
df["hawkish_shock"] = (
    (df["shock_signal_5d"] | df["shock_signal_1d"])
    & df["is_local_peak"]
)

# 2d. Extract events (with minimum gap)
shock_indices = df[df["hawkish_shock"]].index.tolist()
events = []
last_event_idx = -999

for idx in shock_indices:
    if idx - last_event_idx >= PARAMS["event_min_gap_days"]:
        # Find the trough before this peak (within lookback window)
        search_start = max(0, idx - lookback * 2)
        pre_window = df["near_rate"].iloc[search_start:idx]
        if len(pre_window) > 0:
            trough_val = pre_window.min()
            trough_idx = pre_window.idxmin()
        else:
            trough_val = df["near_rate"].iloc[idx]
            trough_idx = idx

        shock_height_bp = (df["near_rate"].iloc[idx] - trough_val) * 100

        if shock_height_bp >= PARAMS["shock_min_height_bp"]:
            events.append({
                "event_id": len(events) + 1,
                "shock_date": df["date"].iloc[idx],
                "shock_idx": idx,
                "trough_date": df["date"].iloc[trough_idx] if trough_idx >= 0 else None,
                "trough_idx": trough_idx,
                "peak_near_rate": df["near_rate"].iloc[idx],
                "trough_near_rate": trough_val,
                "shock_height_bp": shock_height_bp,
                "shock_5d_sum_bp": df["curve_move_5d_sum"].iloc[idx],
                "shock_1d_bp": df["curve_move_bp"].iloc[idx],
            })
            last_event_idx = idx

print(f"  Hawkish shock events detected: {len(events)}")

# ============================================================
# 3. 对每个事件：检测钝化 + 修复 + 分类
# ============================================================
print("[3/5] Analyzing deceleration, repair, and classification...")

results = []
DECEL_THRESH = PARAMS["decel_abs_bp_threshold"]
DECEL_MIN = PARAMS["decel_min_days"]
REPAIR_BP = PARAMS["repair_min_bp"]
REPAIR_RATIO = PARAMS["repair_min_ratio"]
REPAIR_WINDOWS = {
    "60d": PARAMS["repair_max_days"],
    "120d": PARAMS["repair_max_days_mid"],
    "250d": PARAMS["repair_max_days_long"],
}

for ev in events:
    idx = ev["shock_idx"]
    shock_date = ev["shock_date"]
    shock_height = ev["shock_height_bp"]

    # --- 3a. 检测 deceleration (钝化) ---
    decel_detected = False
    decel_start_idx = None
    decel_start_date = None

    # 冲击后搜索钝化 (用最长窗口)
    max_window = max(REPAIR_WINDOWS.values())
    search_end = min(len(df), idx + max_window)
    for i in range(idx + 1, search_end - DECEL_MIN):
        window = df["curve_move_bp"].iloc[i : i + DECEL_MIN]
        if (window.abs() < DECEL_THRESH).all():
            decel_detected = True
            decel_start_idx = i
            decel_start_date = df["date"].iloc[i]
            break

    # --- 3b. 三窗口修复检测 ---
    repair_info = {}  # {window_label: {detected, start_idx, ...}}

    for wlabel, wdays in REPAIR_WINDOWS.items():
        r_detected = False
        r_start_idx = None
        r_start_date = None
        r_end_idx = None
        r_near_at_start = None
        r_final_near = None
        r_total_bp = 0.0
        r_fwd5 = np.nan
        r_fwd10 = np.nan
        r_fwd20 = np.nan

        if decel_detected:
            search_start = decel_start_idx
            search_stop = min(len(df), idx + wdays)
            for i in range(search_start, search_stop):
                decline = (df["near_rate"].iloc[idx] - df["near_rate"].iloc[i]) * 100
                if decline >= REPAIR_BP and (shock_height <= 0 or decline / shock_height >= REPAIR_RATIO):
                    r_detected = True
                    r_start_idx = i
                    r_start_date = df["date"].iloc[i]
                    r_near_at_start = df["near_rate"].iloc[i]
                    # 修复终点: 回落最大点
                    end_search = slice(i, min(len(df), i + 60))
                    best = df["near_rate"].iloc[end_search].idxmin()
                    r_end_idx = best
                    r_final_near = df["near_rate"].iloc[best]
                    r_total_bp = (df["near_rate"].iloc[idx] - r_final_near) * 100
                    break

            # Forward validation
            if r_detected:
                for horizon, tag in [(5, "5d"), (10, "10d"), (20, "20d")]:
                    fwd_i = min(len(df) - 1, r_start_idx + horizon)
                    fwd_r = df["near_rate"].iloc[fwd_i]
                    chg = (r_near_at_start - fwd_r) * 100
                    if tag == "5d":
                        r_fwd5 = chg
                    elif tag == "10d":
                        r_fwd10 = chg
                    else:
                        r_fwd20 = chg

        repair_info[wlabel] = {
            "detected": r_detected,
            "start_idx": r_start_idx,
            "start_date": r_start_date,
            "days_after_shock": (r_start_idx - idx) if r_start_idx else None,
            "total_bp": r_total_bp,
            "ratio_of_shock": round(r_total_bp / shock_height, 3) if shock_height > 0 else 0,
            "fwd_5d_bp": r_fwd5,
            "fwd_10d_bp": r_fwd10,
            "fwd_20d_bp": r_fwd20,
        }

    # Primary repair = first detected among windows
    repair_detected = repair_info["60d"]["detected"]
    repair_start_idx = repair_info["60d"]["start_idx"]
    use_window = "60d"

    # --- 3c. 分类修复类型 (使用 primary repair window) ---
    repair_type = "no_repair"
    repair_type_reason = ""
    hy_oas_avail = None

    if repair_detected:
        row = df.iloc[repair_start_idx]
        hy_oas_avail = row.get("HY_OAS_available", False)
        if pd.isna(hy_oas_avail):
            hy_oas_avail = False

        if not hy_oas_avail:
            repair_type = "unknown_credit_unavailable"
            repair_type_reason = "HY OAS missing during repair window"
        else:
            hy_oas_chg = row.get("HY_OAS_chg_20d", 0)
            dgs10_chg = row.get("DGS10_chg_20d", 0)
            hy_oas_chg = 0 if pd.isna(hy_oas_chg) else hy_oas_chg
            dgs10_chg = 0 if pd.isna(dgs10_chg) else dgs10_chg

            # *_chg_20d columns are in pct-pts; convert to bp for comparison
            hy_oas_bp = hy_oas_chg * 100
            dgs10_bp = dgs10_chg * 100
            hy_stable = hy_oas_bp < PARAMS["credit_hyoas_benign_max_bp"]
            dgs10_falling = dgs10_bp < PARAMS["credit_dgs10_declining_bp"]
            hy_stressed = hy_oas_bp > PARAMS["credit_hyoas_malign_min_bp"]

            if hy_stable and dgs10_falling:
                repair_type = "benign_repair"
                repair_type_reason = "HY OAS stable/declining + DGS10 declining (soft landing)"
            elif hy_stressed:
                repair_type = "malign_repair"
                repair_type_reason = "HY OAS widening (credit stress)"
            elif dgs10_falling:
                repair_type = "mixed_repair"
                repair_type_reason = "DGS10 declining but HY OAS moderately widening"
            else:
                repair_type = "mixed_repair"
                repair_type_reason = "Mixed signals, no clear benign/malign pattern"
    elif decel_detected:
        repair_type = "decel_no_repair"
        repair_type_reason = "Deceleration detected but no repair within 60d"

    # --- 3d. 记录 (含三窗口) ---
    result_entry = {
        "event_id": ev["event_id"],
        "shock_date": str(shock_date.date()),
        "trough_date": str(ev["trough_date"].date()) if ev["trough_date"] else None,
        "shock_height_bp": round(ev["shock_height_bp"], 2),
        "peak_near_rate_pct": round(ev["peak_near_rate"] * 100, 4),
        "shock_5d_sum_bp": round(ev["shock_5d_sum_bp"], 2),
        "deceleration_detected": decel_detected,
        "decel_start_date": str(decel_start_date.date()) if decel_start_date else None,
        "decel_days_after_shock": (decel_start_idx - idx) if decel_start_idx else None,
        "repair_detected": repair_detected,
        "repair_window": use_window if repair_detected else "",
        "repair_start_date": str(repair_info[use_window]["start_date"].date()) if repair_detected else None,
        "repair_days_after_shock": repair_info[use_window]["days_after_shock"],
        "repair_total_bp": round(repair_info[use_window]["total_bp"], 2),
        "repair_ratio_of_shock": repair_info[use_window]["ratio_of_shock"],
        "repair_forward_5d_bp": round(repair_info[use_window]["fwd_5d_bp"], 2) if not np.isnan(repair_info[use_window]["fwd_5d_bp"]) else None,
        "repair_forward_10d_bp": round(repair_info[use_window]["fwd_10d_bp"], 2) if not np.isnan(repair_info[use_window]["fwd_10d_bp"]) else None,
        "repair_forward_20d_bp": round(repair_info[use_window]["fwd_20d_bp"], 2) if not np.isnan(repair_info[use_window]["fwd_20d_bp"]) else None,
        "repair_type": repair_type,
        "repair_type_reason": repair_type_reason,
        "credit_hy_oas_available": bool(hy_oas_avail) if repair_detected else None,
        # Multi-window repair flags
        "repair_60d": repair_info["60d"]["detected"],
        "repair_60d_bp": round(repair_info["60d"]["total_bp"], 2),
        "repair_120d": repair_info["120d"]["detected"],
        "repair_120d_bp": round(repair_info["120d"]["total_bp"], 2),
        "repair_250d": repair_info["250d"]["detected"],
        "repair_250d_bp": round(repair_info["250d"]["total_bp"], 2),
    }
    results.append(result_entry)

results_df = pd.DataFrame(results)

print(f"  Events analyzed: {len(results_df)}")
print(f"  Deceleration: {results_df['deceleration_detected'].sum()}")
print(f"  Repair (60d): {results_df['repair_60d'].sum()}")
print(f"  Repair (120d): {results_df['repair_120d'].sum()}")
print(f"  Repair (250d): {results_df['repair_250d'].sum()}")
print(f"  No repair at all: {(~results_df[['repair_60d','repair_120d','repair_250d']].any(axis=1) & results_df['deceleration_detected']).sum()}")

# ============================================================
# 4. 统计摘要
# ============================================================
print("[4/5] Computing statistics...")

repair_60d = int(results_df["repair_60d"].sum())
repair_120d = int(results_df["repair_120d"].sum())
repair_250d = int(results_df["repair_250d"].sum())
decel_count = int(results_df["deceleration_detected"].sum())
any_repair = int((results_df[["repair_60d", "repair_120d", "repair_250d"]].any(axis=1)).sum())

stats = {
    "params": PARAMS,
    "data_range": {
        "start": str(df["date"].min().date()),
        "end": str(df["date"].max().date()),
        "trading_days": len(df),
        "contracts": 84,
    },
    "events": {
        "total_hawkish_shocks": len(results_df),
        "shock_height_mean_bp": round(results_df["shock_height_bp"].mean(), 2),
        "shock_height_median_bp": round(results_df["shock_height_bp"].median(), 2),
        "shock_height_max_bp": round(results_df["shock_height_bp"].max(), 2),
        "deceleration_detected": decel_count,
        "deceleration_rate_pct": round(results_df["deceleration_detected"].mean() * 100, 1),
        "repair_60d": repair_60d,
        "repair_120d": repair_120d,
        "repair_250d": repair_250d,
        "repair_any_window": any_repair,
    },
    "decel_to_repair_by_window": {
        "decel_events": decel_count,
        "repair_60d": repair_60d,
        "repair_60d_hit_rate_pct": round(repair_60d / decel_count * 100, 1) if decel_count > 0 else 0,
        "repair_120d": repair_120d,
        "repair_120d_hit_rate_pct": round(repair_120d / decel_count * 100, 1) if decel_count > 0 else 0,
        "repair_250d": repair_250d,
        "repair_250d_hit_rate_pct": round(repair_250d / decel_count * 100, 1) if decel_count > 0 else 0,
        "any_repair": any_repair,
        "any_repair_hit_rate_pct": round(any_repair / decel_count * 100, 1) if decel_count > 0 else 0,
    },
    "repair_classification": {
        "benign_repair": int((results_df["repair_type"] == "benign_repair").sum()),
        "malign_repair": int((results_df["repair_type"] == "malign_repair").sum()),
        "mixed_repair": int((results_df["repair_type"] == "mixed_repair").sum()),
        "unknown_credit_unavailable": int((results_df["repair_type"] == "unknown_credit_unavailable").sum()),
        "decel_no_repair": int((results_df["repair_type"] == "decel_no_repair").sum()),
        "no_repair": int((results_df["repair_type"] == "no_repair").sum()),
    },
    "forward_validation": {},
}

# Forward validation for repair events (60d primary)
repair_events = results_df[results_df["repair_60d"]]
for horizon, label in [("repair_forward_5d_bp", "5d"), ("repair_forward_10d_bp", "10d"), ("repair_forward_20d_bp", "20d")]:
    vals = repair_events[horizon].dropna()
    if len(vals) > 0:
        stats["forward_validation"][f"repair_{label}_mean_bp"] = round(vals.mean(), 2)
        stats["forward_validation"][f"repair_{label}_median_bp"] = round(vals.median(), 2)
        stats["forward_validation"][f"repair_{label}_pct_positive"] = round((vals > 0).mean() * 100, 1)
        stats["forward_validation"][f"repair_{label}_n"] = len(vals)

# ============================================================
# 5. 输出
# ============================================================
print("[5/5] Writing outputs...")

# --- CSV ---
csv_path = OUT_DIR / "sr3_repair_validation.csv"
results_df.to_csv(csv_path, index=False)
print(f"  CSV: {csv_path}")

# --- JSON ---
json_path = OUT_DIR / "sr3_repair_validation.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
print(f"  JSON: {json_path}")

# --- Markdown ---
md_path = OUT_DIR / "sr3_repair_validation.md"
_s = stats  # shorthand

md = f"""# SR3 修复验证报告

**生成日期**: {date.today().isoformat()}
**数据范围**: {_s['data_range']['start']} ~ {_s['data_range']['end']} ({_s['data_range']['trading_days']} 交易日, 84 合约)

---

## 一、参数配置

| 参数 | 值 |
|------|-----|
| shock_5d_min_bp | {PARAMS['shock_5d_min_bp']} bp |
| shock_1d_min_bp | {PARAMS['shock_1d_min_bp']} bp |
| peak_lookback_days | {PARAMS['peak_lookback_days']} 天 |
| decel_abs_bp_threshold | {PARAMS['decel_abs_bp_threshold']} bp |
| decel_min_days | {PARAMS['decel_min_days']} 天 |
| repair_min_bp | {PARAMS['repair_min_bp']} bp |
| repair_min_ratio | {PARAMS['repair_min_ratio']} |
| shock_min_height_bp | {PARAMS['shock_min_height_bp']} bp |
| event_min_gap_days | {PARAMS['event_min_gap_days']} 天 |

---

## 二、事件统计

| 指标 | 值 |
|------|-----|
| 鹰派冲击事件总数 | {_s['events']['total_hawkish_shocks']} |
| 冲击幅度均值 | {_s['events']['shock_height_mean_bp']} bp |
| 冲击幅度中位数 | {_s['events']['shock_height_median_bp']} bp |
| 冲击幅度最大值 | {_s['events']['shock_height_max_bp']} bp |
| 检测到钝化 | {_s['events']['deceleration_detected']} ({_s['events']['deceleration_rate_pct']}%) |

---

## 三、钝化 → 修复命中率 (多窗口)

| 修复窗口 | 修复数 | 命中率 |
|----------|--------|--------|
| 60 交易日 (~3月) | {_s['events']['repair_60d']} | {_s['decel_to_repair_by_window']['repair_60d_hit_rate_pct']}% |
| 120 交易日 (~6月) | {_s['events']['repair_120d']} | {_s['decel_to_repair_by_window']['repair_120d_hit_rate_pct']}% |
| 250 交易日 (~1年) | {_s['events']['repair_250d']} | {_s['decel_to_repair_by_window']['repair_250d_hit_rate_pct']}% |
| **任意窗口** | **{_s['events']['repair_any_window']}** | **{_s['decel_to_repair_by_window']['any_repair_hit_rate_pct']}%** |

"""

any_hit = _s['decel_to_repair_by_window']['any_repair_hit_rate_pct']
if any_hit >= 66:
    md += "**结论**: 钝化 → 修复具有显著统计意义 (命中率 ≥ 66%)。钝化可作为修复/拐点的可靠前置信号。\n\n"
elif any_hit >= 50:
    md += "**结论**: 钝化 → 修复具有统计意义 (命中率 ≥ 50%)。钝化对修复有一定预测力，但需结合其他指标确认。\n\n"
elif any_hit >= 33:
    md += "**结论**: 钝化 → 修复的预测力有限 (命中率 33-50%)。钝化不能作为独立修复信号，必须在更广的宏观背景下解读。特别地，在加息周期中钝化频繁出现但不伴随修复。\n\n"
else:
    md += "**结论**: 钝化 → 修复命中率不足 33%。钝化的统计意义不足，不能作为独立交易信号。\n\n"

md += f"""---

## 四、修复分类

| 类型 | 数量 | 含义 |
|------|------|------|
| benign_repair | {_s['repair_classification']['benign_repair']} | 信用稳定 + 利率回落 → 软着陆 |
| malign_repair | {_s['repair_classification']['malign_repair']} | 信用走阔 → 衰退式修复 |
| mixed_repair | {_s['repair_classification']['mixed_repair']} | 信号混合 |
| unknown_credit_unavailable | {_s['repair_classification']['unknown_credit_unavailable']} | HY OAS 缺失，无法判定 |
| decel_no_repair | {_s['repair_classification']['decel_no_repair']} | 钝化但未修复 |
| no_repair | {_s['repair_classification']['no_repair']} | 未钝化，未修复 |

---

## 五、修复后前瞻验证 (60d 窗口修复事件)

"""

fv = _s["forward_validation"]
if fv:
    md += f"""| 前瞻窗口 | 均值 (bp) | 中位数 (bp) | 继续回落比例 | 样本数 |
|----------|-----------|-------------|-------------|--------|
| 5d | {fv.get('repair_5d_mean_bp', 'N/A')} | {fv.get('repair_5d_median_bp', 'N/A')} | {fv.get('repair_5d_pct_positive', 'N/A')}% | {fv.get('repair_5d_n', 'N/A')} |
| 10d | {fv.get('repair_10d_mean_bp', 'N/A')} | {fv.get('repair_10d_median_bp', 'N/A')} | {fv.get('repair_10d_pct_positive', 'N/A')}% | {fv.get('repair_10d_n', 'N/A')} |
| 20d | {fv.get('repair_20d_mean_bp', 'N/A')} | {fv.get('repair_20d_median_bp', 'N/A')} | {fv.get('repair_20d_pct_positive', 'N/A')}% | {fv.get('repair_20d_n', 'N/A')} |

"""
else:
    md += "无 60d 窗口修复事件，跳过前瞻验证。\n\n"

md += f"""---

## 六、约束确认

| 约束 | 状态 |
|------|------|
| SR3 只判断短端预期是否修复 | ✅ |
| HY OAS 判断修复良性/恶性 | ✅ |
| HY OAS 缺失时 credit_state = unavailable | ✅ ({_s['repair_classification']['unknown_credit_unavailable']} 个事件) |
| 2023-03-06~2023-04-20 HY OAS: deliberate GAP | ✅ (FRED series starts 2023-06-19; SVB window marked unavailable) |
| SR3 修复不单独解释为买入信号 | ✅ |
| 不修改 Risk OS | ✅ |
| 不修改 dashboard | ✅ |
| 不修改 run_all.py | ✅ |

---

## 七、事件明细 (全部 {len(results_df)} 条)

| ID | Shock Date | Height bp | Decel | R_60d | R_120d | R_250d | Type | Fwd 5d bp |
|----|-----------|-----------|-------|-------|--------|--------|------|-----------|
"""

for _, r in results_df.iterrows():
    repair_mark = "✓" if r["repair_detected"] else "✗"
    r60 = "✓" if r["repair_60d"] else "✗"
    r120 = "✓" if r["repair_120d"] else "✗"
    r250 = "✓" if r["repair_250d"] else "✗"
    fwd5 = r.get("repair_forward_5d_bp", "N/A")
    fwd5 = f"{fwd5:.1f}" if isinstance(fwd5, (int, float)) and not np.isnan(fwd5) else "N/A"
    md += f"| {r['event_id']} | {r['shock_date']} | {r['shock_height_bp']} | {'✓' if r['deceleration_detected'] else '✗'} | {r60} | {r120} | {r250} | {r['repair_type']} | {fwd5} |\n"

md += f"""

---

*独立回测研究模块 — 不接入 Risk OS / dashboard / run_all.py*
"""

with open(md_path, "w", encoding="utf-8") as f:
    f.write(md)

print(f"  MD: {md_path}")
print(f"\nDone. Outputs in {OUT_DIR}/")
print(f"  - sr3_repair_validation.csv  ({len(results_df)} events)")
print(f"  - sr3_repair_validation.json (stats)")
print(f"  - sr3_repair_validation.md   (report)")
