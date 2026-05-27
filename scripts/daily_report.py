"""
Daily Regime Report Generator
==============================
Reads series.json (auto-updated by GitHub Actions) and outputs a
structured daily report: current regime, v3.5 trigger status, curve
regime, HY stress regime, framework indicators.

Usage:
    python scripts/daily_report.py              # print to stdout
    python scripts/daily_report.py --md          # markdown to report/
    python scripts/daily_report.py --json        # JSON summary
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR = Path(__file__).resolve().parent.parent / "report"
SERIES_PATH = DATA_DIR / "series.json"

# FRED series IDs we use for regime computation
HY_OAS_ID = "BAMLH0A0HYM2"
VIX_ID    = "VIXCLS"
DGS2_ID   = "DGS2"
DGS5_ID   = "DGS5"
DGS10_ID  = "DGS10"
DGS30_ID  = "DGS30"
SOFR_ID   = "SOFR"
IORB_ID   = "IORB"
EFFR_ID   = "EFFR"
MOVE_ID   = "MOVE"
RRP_ID    = "RRPONTSYD"
GOLD_ID   = "GOLDAMGBD228NLBM"
STABLE_ID = "STABLECOIN_MCAP_B"
T5Y5Y_ID  = "T5YIFR"
TERMP_ID  = "THREEFYTP10"
TIPS10_ID = "DFII10"
MORT_ID   = "MORTGAGE30US"
DTWEXB_ID = "DTWEXBGS"

# Yahoo Finance
SPY_ID = "SPY"
HYG_ID = "HYG"
FXY_ID = "FXY"

GOLD_RATIO_ID = "GOLD_10Y_RATIO"
SOFR_IORB_ID  = "SOFR_IORB"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_data() -> dict[str, list[dict]]:
    if not SERIES_PATH.exists():
        print(f"[ERROR] {SERIES_PATH} not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)
    with SERIES_PATH.open() as f:
        return json.load(f)


def to_dict(series: list[dict]) -> dict[str, float]:
    return {d["date"]: d["value"] for d in series}


def last_value(series: list[dict]) -> float | None:
    return series[-1]["value"] if series else None


def last_date(series: list[dict]) -> str | None:
    return series[-1]["date"] if series else None


def n_day_ago(series: list[dict], n: int) -> float | None:
    """Get value N trading days ago (approximate with calendar days * 1.4)."""
    if not series or len(series) < n + 1:
        return None
    return series[-n - 1]["value"]


def n_day_change(series: list[dict], n: int) -> float | None:
    """Change over last N trading days."""
    cur = last_value(series)
    ago = n_day_ago(series, n)
    if cur is None or ago is None:
        return None
    return cur - ago


def n_day_ma(series: list[dict], n: int) -> float | None:
    """Simple moving average over last N values."""
    if not series or len(series) < n:
        return None
    vals = [d["value"] for d in series[-n:]]
    return sum(vals) / len(vals)


def n_day_ret_pct(series: list[dict], n: int) -> float | None:
    """Percentage return over last N trading days."""
    cur = last_value(series)
    ago = n_day_ago(series, n)
    if cur is None or ago is None or ago == 0:
        return None
    return (cur - ago) / ago * 100


def trend_arrow(series: list[dict], n: int = 5) -> str:
    """Return ▲ (up), ▼ (down), → (flat) for recent trend."""
    chg = n_day_change(series, n)
    if chg is None:
        return "?"
    threshold = abs(last_value(series) or 1) * 0.005
    if chg > threshold:
        return "▲"
    elif chg < -threshold:
        return "▼"
    return "→"


def compute_dur5(series: list[dict], condition_fn, max_n: int = 5) -> int:
    """Count consecutive days meeting condition from latest backward. Returns 0..max_n."""
    if not series:
        return 0
    count = 0
    for d in reversed(series):
        if condition_fn(d["value"]):
            count += 1
            if count >= max_n:
                return max_n
        else:
            break
    return count


def compute_dur5_either(series: list[dict], cond_a_fn, cond_b_fn, max_n: int = 5) -> int:
    """Count consecutive days meeting condition A OR condition B. Returns 0..max_n."""
    if not series:
        return 0
    count = 0
    for d in reversed(series):
        if cond_a_fn(d["value"]) or cond_b_fn(d["value"]):
            count += 1
            if count >= max_n:
                return max_n
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Regime computations
# ---------------------------------------------------------------------------

def compute_curve_regime(data: dict) -> dict:
    """Classify 2s10s curve regime."""
    dgs2   = data.get(DGS2_ID, [])
    dgs10  = data.get(DGS10_ID, [])
    dgs30  = data.get(DGS30_ID, [])

    if not dgs2 or not dgs10:
        return {"regime": "N/A", "reason": "missing yield data", "spread_2s10s_bp": None, "is_steep_steepening": False, "signal": None}

    y2  = last_value(dgs2)  or 0
    y10 = last_value(dgs10) or 0
    y30 = last_value(dgs30) or 0

    spread_2s10s = y10 - y2
    dgs5_data = data.get(DGS5_ID, [])
    spread_5s30s = y30 - (last_value(dgs5_data) if dgs5_data else 0)

    # Direction over 5d
    chg_2 = n_day_change(dgs2, 5) or 0
    chg_10 = n_day_change(dgs10, 5) or 0
    chg_spread_5d = n_day_change(dgs10, 5) or 0
    if chg_spread_5d is None:
        # Approximate
        spread_ago = (n_day_ago(dgs10, 5) or y10) - (n_day_ago(dgs2, 5) or y2)
        chg_spread_5d = spread_2s10s - spread_ago

    # Steepening vs flattening
    if chg_spread_5d > 0.05:
        direction = "Steepening"
    elif chg_spread_5d < -0.05:
        direction = "Flattening"
    else:
        direction = "Stable"

    # Bear vs Bull (based on 2Y direction as proxy for policy expectations)
    if chg_2 > 0.05:
        bias = "Bear"
    elif chg_2 < -0.05:
        bias = "Bull"
    else:
        bias = ""

    if spread_2s10s > 1.5:
        steepness = "Steep"
    elif spread_2s10s < 0:
        steepness = "Inverted"
    elif spread_2s10s < 0.3:
        steepness = "Flat"
    else:
        steepness = "Normal"

    # Special: Bull Steepener = Steep-Steepening exit → historically +1.81% mean 60d
    is_steep_steepening = spread_2s10s > 1.0 and chg_spread_5d > 0.05 and chg_2 < -0.03

    regime = f"{bias} {direction}" if bias else direction
    if is_steep_steepening:
        regime = "Steep-Steepening ★"

    return {
        "regime": regime,
        "spread_2s10s_bp": round(spread_2s10s * 100, 1),
        "spread_5s30s_bp": round(spread_5s30s * 100, 1) if data.get(DGS5_ID) else None,
        "yield_2y": round(y2, 2),
        "yield_10y": round(y10, 2),
        "yield_30y": round(y30, 2),
        "chg_5d_bp": round(chg_spread_5d * 100, 1),
        "chg_2y_5d_bp": round(chg_2 * 100, 1),
        "chg_10y_5d_bp": round(chg_10 * 100, 1),
        "steepness": steepness,
        "is_steep_steepening": is_steep_steepening,
        "signal": "★ 加仓候选 (Steep-Steepening exit 60d)" if is_steep_steepening else None,
    }


def compute_hy_stress(data: dict) -> dict:
    """Classify HY stress regime based on OAS level & MOVE."""
    hy   = data.get(HY_OAS_ID, [])
    move = data.get(MOVE_ID, [])

    hy_val  = last_value(hy) or 0
    move_val = last_value(move) or 0

    hy_chg_20d = n_day_change(hy, 20) or 0

    # Classification
    if hy_val > 5.0:
        regime = "Stress"
    elif hy_val > 4.0:
        regime = "Widening"
    elif hy_val < 2.5:
        regime = "Compressed"
    else:
        regime = "Abundant"

    return {
        "regime": regime,
        "hy_oas": round(hy_val, 2),
        "hy_oas_unit": "%",
        "hy_oas_300bp": hy_val < 3.0,
        "hy_oas_500bp": hy_val > 5.0,
        "hy_chg_20d_bp": round(hy_chg_20d * 100, 1),
        "move_index": round(move_val, 1),
        "move_above_120": move_val > 120,
    }


def compute_v35_triggers(data: dict) -> dict:
    """Check all v3.5 signal conditions from FRED + Yahoo data."""
    hy   = data.get(HY_OAS_ID, [])
    vix  = data.get(VIX_ID, [])
    move = data.get(MOVE_ID, [])
    spy  = data.get(SPY_ID, [])
    hyg  = data.get(HYG_ID, [])
    fxy  = data.get(FXY_ID, [])

    hy_val  = last_value(hy) or 0
    vix_val = last_value(vix) or 0
    move_val = last_value(move) or 0
    spy_val = last_value(spy) or 0
    hyg_val = last_value(hyg) or 0
    fxy_val = last_value(fxy) or 0

    # Compute SOFR-IORB spread
    sofr = data.get(SOFR_ID, [])
    iorb = data.get(IORB_ID, [])
    sofr_val  = last_value(sofr) or 0
    iorb_val  = last_value(iorb) or 0
    sofr_iorb_bp = (sofr_val - iorb_val) * 100

    # --- Drawdown Warning (primary) ---
    hy_20d_delta_bp = (n_day_change(hy, 20) or 0) * 100
    hy_5d_delta_bp  = (n_day_change(hy, 5) or 0) * 100

    dd_warning = hy_20d_delta_bp > 20  # >20bp

    # --- Short-term supplement ---
    st_warning = hy_5d_delta_bp > 15  # >15bp

    # --- Yahoo-based supplement ---
    spy_200ma = n_day_ma(spy, 200) if spy else None
    spy_below_200ma = spy_val < spy_200ma if (spy_200ma and spy_val) else None
    hyg_5d_ret = n_day_ret_pct(hyg, 5) if hyg else None
    hyg_20d_ret = n_day_ret_pct(hyg, 20) if hyg else None
    hyg_all_time_high = max((d["value"] for d in hyg), default=0) if hyg else 0
    hyg_dd_pct = (hyg_val - hyg_all_time_high) / hyg_all_time_high * 100 if (hyg_all_time_high > 0 and hyg_val) else None
    fxy_5d_ret = n_day_ret_pct(fxy, 5) if fxy else None

    hyg_trigger = hyg_5d_ret is not None and hyg_5d_ret < -1.5
    fxy_trigger = fxy_5d_ret is not None and fxy_5d_ret > 2.5

    # --- Extreme Meltdown (5 conditions) ---
    extreme_hit = []
    if hy_val > 5.0:
        extreme_hit.append("HY OAS > 5%")
    if vix_val > 35:
        extreme_hit.append("VIX > 35")
    if sofr_iorb_bp > 5:
        extreme_hit.append(f"SOFR-IORB > +5bp (now {sofr_iorb_bp:.1f}bp)")
    # EFFR-IORB spike
    effr = data.get(EFFR_ID, [])
    effr_val = last_value(effr) or 0
    effr_iorb_bp = (effr_val - iorb_val) * 100
    if effr_iorb_bp > 5:
        extreme_hit.append(f"EFFR-IORB > +5bp (now {effr_iorb_bp:.1f}bp)")
    # SOFR-IORB spike >+20bp
    if sofr_iorb_bp > 20:
        extreme_hit.append(f"SOFR-IORB spike > +20bp (now {sofr_iorb_bp:.1f}bp)")

    # Missing data note
    missing = []
    if not spy:
        missing.append("SPY (Yahoo Finance)")
    if not hyg:
        missing.append("HYG (Yahoo Finance)")
    if not fxy:
        missing.append("FXY (Yahoo Finance)")

    return {
        "drawdown_warning": dd_warning,
        "hy_oas_20d_delta_bp": round(hy_20d_delta_bp, 1),
        "hy_oas_5d_delta_bp": round(hy_5d_delta_bp, 1),
        "short_term_warning": st_warning,
        "extreme_hit": extreme_hit,
        "hy_oas_pct": round(hy_val, 2),
        "vix": round(vix_val, 1),
        "move": round(move_val, 1),
        "sofr_iorb_bp": round(sofr_iorb_bp, 1),
        "effr_iorb_bp": round(effr_iorb_bp, 1),
        # Yahoo-based signals
        "spy_price": round(spy_val, 1) if spy_val else None,
        "spy_200ma": round(spy_200ma, 1) if spy_200ma else None,
        "spy_below_200ma": spy_below_200ma,
        "hyg_price": round(hyg_val, 1) if hyg_val else None,
        "hyg_5d_ret_pct": round(hyg_5d_ret, 1) if hyg_5d_ret is not None else None,
        "hyg_20d_ret_pct": round(hyg_20d_ret, 1) if hyg_20d_ret is not None else None,
        "hyg_dd_pct": round(hyg_dd_pct, 1) if hyg_dd_pct is not None else None,
        "hyg_trigger": hyg_trigger,
        "fxy_price": round(fxy_val, 1) if fxy_val else None,
        "fxy_5d_ret_pct": round(fxy_5d_ret, 1) if fxy_5d_ret is not None else None,
        "fxy_trigger": fxy_trigger,
        "missing_sources": missing,
    }


def compute_framework(data: dict) -> dict:
    """Layer 3 framework indicators."""
    gold_ratio = last_value(data.get(GOLD_RATIO_ID, []))
    t5y5y      = last_value(data.get(T5Y5Y_ID, []))
    term_p     = last_value(data.get(TERMP_ID, []))
    stable     = last_value(data.get(STABLE_ID, []))
    gold       = last_value(data.get(GOLD_ID, []))
    dtw        = last_value(data.get(DTWEXB_ID, []))
    tips10     = last_value(data.get(TIPS10_ID, []))
    dgs10      = last_value(data.get(DGS10_ID, []))

    return {
        "gold_10y_ratio": round(gold_ratio, 1) if gold_ratio else None,
        "gold_lbma": round(gold, 0) if gold else None,
        "yield_10y": round(dgs10, 2) if dgs10 else None,
        "t5y5y_fwd": round(t5y5y, 2) if t5y5y else None,
        "t5y5y_note": "narrative only (F1=0.13 falsified, no position trigger)",
        "term_premium": round(term_p, 2) if term_p else None,
        "tips_10y_real": round(tips10, 2) if tips10 else None,
        "stablecoin_b": round(stable, 1) if stable else None,
        "dollar_index": round(dtw, 1) if dtw else None,
    }


def compute_liquidity(data: dict) -> dict:
    """Layer 1: system plumbing."""
    rrp       = last_value(data.get(RRP_ID, []))
    sofr_iorb = last_value(data.get(SOFR_IORB_ID, []))
    wresbal   = last_value(data.get("WRESBAL", []))

    return {
        "rrp_b": round(rrp, 1) if rrp else None,
        "rrp_under_100b": rrp is not None and rrp < 100,
        "rrp_tightening_note": "RRP < $100B = Tightening trigger (Task 3 verified)" if (rrp and rrp < 100) else None,
        "sofr_iorb_bp": round(sofr_iorb, 1) if sofr_iorb else None,
        "reserves_b": round(wresbal, 0) if wresbal else None,
    }


# ---------------------------------------------------------------------------
# ABCD Position Framework (v3.5, §0.6)
# ---------------------------------------------------------------------------

POSITION_MATRIX = {
    "R1": {"Primary": 75, "Hedge": 5,  "Cash": 20, "label": "R1 宽松"},
    "R2": {"Primary": 55, "Hedge": 25, "Cash": 20, "label": "R2 正常"},
    "R3": {"Primary": 40, "Hedge": 30, "Cash": 30, "label": "R3 警惕"},
    "R4": {"Primary": 30, "Hedge": 40, "Cash": 30, "label": "R4 防御"},
    "R5": {"Primary": 10, "Hedge": 40, "Cash": 50, "label": "R5 极端"},
}

# A-domain thresholds (近端流动性)
A_THRESHOLDS = {
    "EFFR_IORB": {"🟢": (-15, -7), "🟡": (-7, -3), "🟠": (-3, 0), "🔴": (0, float("inf"))},
    "SOFR_IORB": {"🟢": (-float("inf"), -10), "🟡": (-10, -5), "🟠": (-5, 0), "🔴": (0, float("inf"))},
    "Reserve":  {"🟢": (2.8, float("inf")), "🟡": (2.2, 2.8), "🟠": (1.6, 2.2), "🔴": (-float("inf"), 1.6)},
}
# B-domain thresholds (信用周期)
B_THRESHOLDS = {
    "HY_OAS": {"⚠️": (0, 300), "🟢": (300, 480), "🟡": (480, 650), "🟠": (650, 950), "🔴": (950, float("inf"))},
    "IG_OAS": {"⚠️": (0, 85), "🟢": (85, 170), "🟡": (170, 220), "🟠": (220, 350), "🔴": (350, float("inf"))},
    "Mortgage": {"🟢": (3.5, 5.5), "🟡": (5.5, 6.5), "🟠": (6.5, 7.5), "🔴": (7.5, float("inf"))},
}
# C-domain thresholds (远端风险溢价)
C_THRESHOLDS = {
    "5Y5Y":   {"🟢": (1.90, 2.25), "🟡": (2.25, 2.45), "🟠": (2.45, 2.70), "🔴": (2.70, float("inf"))},
    "DFII10": {"🟢": (-float("inf"), 0.50), "🟡": (0.50, 1.20), "🟠": (1.20, 2.00), "🔴": (2.00, float("inf"))},
    "10Y_BEI":{"🟢": (1.80, 2.25), "🟡": (2.25, 2.50), "🟠": (2.50, 2.80), "🔴": (2.80, float("inf"))},
}
# D-domain thresholds (跨境离岸)
D_THRESHOLDS = {
    "FXY_5d": {"🟢": (-1.5, 1.5), "🟡": (1.5, 2.5), "🟠": (2.5, 4.0), "🔴": (4.0, float("inf"))},
}

COLOR_RANK = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}


def classify_traffic_light(value: float | None, thresholds: dict) -> str:
    """Map a numeric value to 🟢🟡🟠🔴⚠️ using threshold intervals."""
    if value is None:
        return "N/A"
    for color, (lo, hi) in thresholds.items():
        if lo <= value < hi:
            return color
        if hi == float("inf") and value >= lo:
            return color
    return "N/A"


def _indicator_row(
    domain: str, name: str, cur_val, unit: str, delta_20d, thresholds: dict,
    ind_type: str, dur_status: str, *, light_override: str = None,
) -> dict:
    """Build a single indicator row for the 四端快照 table."""
    light = light_override or classify_traffic_light(cur_val, thresholds)
    unit_sfx = "%" if "pct" in unit else "bp" if unit == "bp" else ""
    thresh_str = " / ".join(
        f"{c}{lo}{'~' if lo != -float('inf') else '<'}{hi}{unit_sfx}"
        for c, (lo, hi) in thresholds.items()
        if lo != -float("inf")
    )
    thresh_str = thresh_str.replace("inf" + unit_sfx, "+∞").replace("-inf" + unit_sfx, "-∞") if unit_sfx else thresh_str
    delta_str = f"{delta_20d:+.0f}bp" if delta_20d is not None and unit == "bp" else (
        f"{delta_20d:+.2f}%" if delta_20d is not None and "pct" in unit else (
            f"{delta_20d:+.2f}" if delta_20d is not None else "—"
        )
    )
    val_str = f"{cur_val:.0f}bp" if cur_val is not None and unit == "bp" else (
        f"{cur_val:.2f}%" if cur_val is not None and "pct" in unit else (
            f"{cur_val:.2f}" if cur_val is not None else "N/A"
        )
    )
    return {
        "domain": domain, "name": name, "value_str": val_str, "delta_str": delta_str,
        "thresh_str": thresh_str, "light": light, "type": ind_type, "dur": dur_status,
    }


def compute_abcd_signals(data: dict) -> dict:
    """Evaluate ABCD domain signals with DUR5 + 20d changes. Returns full diagnosis dict."""
    # --- A domain ---
    effr_s     = data.get(EFFR_ID, [])
    iorb_s     = data.get(IORB_ID, [])
    sofr_s     = data.get(SOFR_ID, [])
    wres_s     = data.get("WRESBAL", [])

    effr     = last_value(effr_s)
    iorb     = last_value(iorb_s)
    sofr     = last_value(sofr_s)
    wresbal  = last_value(wres_s)

    effr_iorb_bp = round((effr - iorb) * 100, 1) if (effr is not None and iorb is not None) else None
    sofr_iorb_bp = round((sofr - iorb) * 100, 1) if (sofr is not None and iorb is not None) else None
    reserve_t    = round(wresbal / 1_000_000, 2) if wresbal else None

    # 20d changes
    effr_iorb_20d = n_day_change(effr_s, 20) if effr_s else None
    effr_iorb_20d = round(effr_iorb_20d * 100, 1) if effr_iorb_20d is not None else None
    sofr_iorb_20d = n_day_change(sofr_s, 20) if sofr_s else None
    sofr_iorb_20d = round(sofr_iorb_20d * 100, 1) if sofr_iorb_20d is not None else None
    reserve_20d   = n_day_change(wres_s, 20) if wres_s else None
    reserve_20d_t = round(reserve_20d / 1_000_000, 2) if reserve_20d is not None else None

    a_effr = classify_traffic_light(effr_iorb_bp, A_THRESHOLDS["EFFR_IORB"])
    a_sofr = classify_traffic_light(sofr_iorb_bp, A_THRESHOLDS["SOFR_IORB"])
    a_res  = classify_traffic_light(reserve_t, A_THRESHOLDS["Reserve"])

    # DUR5: EFFR-IORB in 🟠 range (-3 to 0bp) or 🔴 (>0bp)
    effr_iorb_raw = [(d["value"] - iorb) * 100 for d in effr_s if iorb is not None] if effr_s and iorb is not None else []
    dur5_effr = 0
    if effr_iorb_raw:
        count = 0
        for v in reversed(effr_iorb_raw):
            if -3 <= v < 0 or v >= 0:  # 🟠 or 🔴
                count += 1
                if count >= 5:
                    dur5_effr = 5
                    break
            else:
                break
        if count < 5:
            dur5_effr = count

    # DUR5: DFII10 > 2.00%
    dfii_s = data.get("DFII10", [])
    dur5_dfii = sum(1 for d in reversed(dfii_s) if d["value"] >= 2.00) if dfii_s else 0
    dur5_dfii = min(dur5_dfii, 5)

    # Domain worst
    a_signals = [s for s in [a_effr, a_sofr, a_res] if s not in ("N/A",)]
    a_worst = max(a_signals, key=lambda x: COLOR_RANK.get(x, -1)) if a_signals else "N/A"

    # 四端快照 rows for A
    a_rows = [
        _indicator_row("A", "EFFR-IORB", effr_iorb_bp, "bp", effr_iorb_20d,
                       A_THRESHOLDS["EFFR_IORB"], "ABS+DUR5",
                       f"{dur5_effr}/5 {'✅' if dur5_effr >= 5 else ''}"),
        _indicator_row("A", "SOFR-IORB", sofr_iorb_bp, "bp", sofr_iorb_20d,
                       A_THRESHOLDS["SOFR_IORB"], "ABS", "—"),
        _indicator_row("A", "Reserve", reserve_t, "pct", reserve_20d_t,
                       A_THRESHOLDS["Reserve"], "ABS", "周级"),
    ]

    a_details = {
        "EFFR-IORB": {"value_bp": effr_iorb_bp, "light": a_effr, "dur5": dur5_effr},
        "SOFR-IORB": {"value_bp": sofr_iorb_bp, "light": a_sofr},
        "Reserve":   {"value_t": reserve_t,   "light": a_res},
    }

    # --- B domain ---
    hy_s   = data.get(HY_OAS_ID, [])
    ig_s   = data.get("BAMLC0A0CM", [])
    mtg_s  = data.get("MORTGAGE30US", [])

    hy_oas   = last_value(hy_s)
    ig_oas   = last_value(ig_s)
    mortgage = last_value(mtg_s)

    hy_oas_bp = hy_oas * 100 if hy_oas is not None else None
    ig_oas_bp = ig_oas * 100 if ig_oas is not None else None

    hy_20d  = n_day_change(hy_s, 20)
    hy_20d  = round(hy_20d * 100, 0) if hy_20d is not None else None  # bp
    ig_20d  = n_day_change(ig_s, 20)
    ig_20d  = round(ig_20d * 100, 0) if ig_20d is not None else None
    mtg_20d = n_day_change(mtg_s, 20)
    mtg_20d = round(mtg_20d * 100, 0) if mtg_20d is not None else None  # bp

    b_hy  = classify_traffic_light(hy_oas_bp, B_THRESHOLDS["HY_OAS"])
    b_ig  = classify_traffic_light(ig_oas_bp, B_THRESHOLDS["IG_OAS"])
    b_mtg = classify_traffic_light(mortgage, B_THRESHOLDS["Mortgage"])

    # Mortgage conditional
    mtg_cond_met = hy_oas_bp is not None and hy_oas_bp >= 455
    mtg_cond_note = "条件满足" if mtg_cond_met else "条件不满足(HY<455bp)"
    if b_mtg == "🟠" and not mtg_cond_met:
        b_mtg = "🟡"

    b_signals = [s for s in [b_hy, b_ig, b_mtg] if s not in ("N/A", "⚠️")]
    b_worst = "N/A"
    if b_signals:
        b_worst = max(b_signals, key=lambda x: COLOR_RANK.get(x, -1))
    if b_worst == "N/A" and "⚠️" in [b_hy, b_ig, b_mtg]:
        b_worst = "⚠️"

    b_rows = [
        _indicator_row("B", "HY OAS", hy_oas_bp, "bp", hy_20d,
                       B_THRESHOLDS["HY_OAS"], "ROLL+ABS", "—",
                       light_override = "⚠️自满" if b_hy == "⚠️" else b_hy),
        _indicator_row("B", "IG OAS", ig_oas_bp, "bp", ig_20d,
                       B_THRESHOLDS["IG_OAS"], "ROLL+ABS", "—",
                       light_override = "⚠️自满" if b_ig == "⚠️" else b_ig),
        _indicator_row("B", "Mortgage", mortgage, "pct", mtg_20d,
                       B_THRESHOLDS["Mortgage"], "ABS+条件",
                       mtg_cond_note if b_mtg == "🟡" else ("需2周+HY>455bp" if mortgage and mortgage >= 6.5 else "—")),
    ]

    b_details = {
        "HY OAS":   {"value_bp": hy_oas_bp, "light": b_hy},
        "IG OAS":   {"value_bp": ig_oas_bp, "light": b_ig},
        "Mortgage": {"value_pct": round(mortgage, 2) if mortgage else None, "light": b_mtg,
                     "cond_met": mtg_cond_met},
    }

    # --- C domain ---
    t5y5y_s  = data.get(T5Y5Y_ID, [])
    dfii_s   = data.get("DFII10", [])
    t10yie_s = data.get("T10YIE", [])

    t5y5y  = last_value(t5y5y_s)
    dfii10 = last_value(dfii_s)
    t10yie = last_value(t10yie_s)

    t5y5y_20d  = n_day_change(t5y5y_s, 20)
    t5y5y_20d  = round(t5y5y_20d * 100, 0) if t5y5y_20d is not None else None
    dfii_20d   = n_day_change(dfii_s, 20)
    dfii_20d   = round(dfii_20d * 100, 0) if dfii_20d is not None else None
    bei_20d    = n_day_change(t10yie_s, 20)
    bei_20d    = round(bei_20d * 100, 0) if bei_20d is not None else None

    c_5y5y  = classify_traffic_light(t5y5y, C_THRESHOLDS["5Y5Y"])
    c_dfii  = classify_traffic_light(dfii10, C_THRESHOLDS["DFII10"])
    c_bei   = classify_traffic_light(t10yie, C_THRESHOLDS["10Y_BEI"])

    c_signals = [s for s in [c_5y5y, c_dfii, c_bei] if s not in ("N/A", "🟢", "🟡")]
    c_worst = "N/A"
    if c_signals:
        c_worst = max(c_signals, key=lambda x: COLOR_RANK.get(x, -1))
    else:
        c_non_na = [s for s in [c_5y5y, c_dfii, c_bei] if s != "N/A"]
        if c_non_na:
            c_worst = max(c_non_na, key=lambda x: COLOR_RANK.get(x, -1))

    c_rows = [
        _indicator_row("C", "5Y5Y", t5y5y, "pct", t5y5y_20d,
                       C_THRESHOLDS["5Y5Y"], "ROLL", "—"),
        _indicator_row("C", "DFII10", dfii10, "pct", dfii_20d,
                       C_THRESHOLDS["DFII10"], "ABS+DUR5",
                       f"{dur5_dfii}/5 {'✅' if dur5_dfii >= 5 else ''}"),
        _indicator_row("C", "10Y BEI", t10yie, "pct", bei_20d,
                       C_THRESHOLDS["10Y_BEI"], "ROLL", "—"),
    ]

    c_details = {
        "5Y5Y":    {"value_pct": round(t5y5y, 2) if t5y5y else None, "light": c_5y5y},
        "DFII10":  {"value_pct": round(dfii10, 2) if dfii10 else None, "light": c_dfii, "dur5": dur5_dfii},
        "10Y BEI": {"value_pct": round(t10yie, 2) if t10yie else None, "light": c_bei},
    }

    # --- D domain ---
    fxy      = data.get(FXY_ID, [])
    fxy_5d   = n_day_ret_pct(fxy, 5) if fxy else None
    fxy_20d  = n_day_ret_pct(fxy, 20) if fxy else None
    d_light  = classify_traffic_light(fxy_5d, D_THRESHOLDS["FXY_5d"])

    d_rows = [
        _indicator_row("D", "FXY 5d", fxy_5d, "pct", fxy_20d,
                       D_THRESHOLDS["FXY_5d"], "ABS", "—"),
    ]

    d_details = {
        "FXY 5d": {"value_pct": round(fxy_5d, 1) if fxy_5d is not None else None, "light": d_light},
    }

    # --- Cross-domain signal counting ---
    cross_domain_count = 0
    red_domain_count = 0
    has_red = False
    for domain_worst in [a_worst, b_worst, c_worst, d_light]:
        if domain_worst in ("🔴",):
            cross_domain_count += 1
            red_domain_count += 1
            has_red = True
        elif domain_worst in ("🟠",):
            cross_domain_count += 1

    return {
        "A": {"light": a_worst, "details": a_details, "rows": a_rows},
        "B": {"light": b_worst, "details": b_details, "rows": b_rows},
        "C": {"light": c_worst, "details": c_details, "rows": c_rows},
        "D": {"light": d_light, "details": d_details, "rows": d_rows},
        "cross_domain_count": cross_domain_count,
        "red_domain_count": red_domain_count,
        "has_red": has_red,
    }


def compute_trigger_proximity(abcd: dict, data: dict) -> list[dict]:
    """Compute P1/P2 trigger proximity table for 触发距离 section."""
    rows = []

    effr_s   = data.get(EFFR_ID, [])
    iorb_s   = data.get(IORB_ID, [])
    dfii_s   = data.get("DFII10", [])
    hy_s     = data.get(HY_OAS_ID, [])
    mtg_s    = data.get("MORTGAGE30US", [])
    t5y5y_s  = data.get(T5Y5Y_ID, [])

    iorb     = last_value(iorb_s)
    effr_iorb_bp = round((last_value(effr_s) - iorb) * 100, 1) if (last_value(effr_s) is not None and iorb is not None) else None
    dfii10   = last_value(dfii_s)
    hy_oas_bp= last_value(hy_s) * 100 if last_value(hy_s) is not None else None
    mortgage = last_value(mtg_s)
    t5y5y    = last_value(t5y5y_s)

    dur5_effr = abcd["A"]["details"].get("EFFR-IORB", {}).get("dur5", 0)
    dur5_dfii = abcd["C"]["details"].get("DFII10", {}).get("dur5", 0)

    # P1: DFII10
    if dfii10 is not None:
        dist_bp = round((dfii10 - 2.00) * 100, 0) if dfii10 >= 2.00 else round((2.00 - dfii10) * 100, 0)
        status = f"已越线+{dist_bp:.0f}bp" if dfii10 >= 2.00 else f"距触发{dist_bp:.0f}bp"
        trend = trend_arrow(dfii_s, 5) if dfii_s else "?"
        action = "✅ 已确认→R3" if dur5_dfii >= 5 else f"DUR5 {dur5_dfii}/5"
        rows.append({"priority": "P1", "indicator": "DFII10 🔴", "value": f"{dfii10:.2f}%",
                     "trigger": "2.00%", "distance": status, "dur": f"{dur5_dfii}/5",
                     "trend": trend, "action": action})

    # P1: EFFR-IORB
    if effr_iorb_bp is not None:
        dist_to_orange = round(effr_iorb_bp - (-3), 1)   # distance to 🟠 lower bound
        dist_to_red = round(0 - effr_iorb_bp, 1)
        if effr_iorb_bp >= 0:
            status = "已越🔴线"
        elif effr_iorb_bp >= -3:
            status = f"已触及🟠段({effr_iorb_bp}bp)"
        else:
            status = f"距🟠{dist_to_orange:.0f}bp"
        trend = trend_arrow(effr_s, 5) if effr_s else "?"
        action = f"DUR5 {dur5_effr}/5 {'✅' if dur5_effr >= 5 else ''}" if effr_iorb_bp >= -3 else "仅观察"
        rows.append({"priority": "P1", "indicator": "EFFR-IORB 🟠", "value": f"{effr_iorb_bp}bp",
                     "trigger": "−3bp🟠 / 0bp🔴", "distance": status, "dur": f"{dur5_effr}/5",
                     "trend": trend, "action": action})

    # P1: HY OAS complacency
    if hy_oas_bp is not None:
        dist_to_300 = round(300 - hy_oas_bp, 0)
        status = f"距⚠️上沿{dist_to_300:.0f}bp" if hy_oas_bp < 300 else "已脱离自满区"
        trend = trend_arrow(hy_s, 5) if hy_s else "?"
        action = "突破→正常化" if hy_oas_bp >= 300 else "仅观察"
        rows.append({"priority": "P1", "indicator": "HY OAS 自满", "value": f"{hy_oas_bp:.0f}bp",
                     "trigger": "300bp(⚠️上沿)", "distance": status, "dur": "—",
                     "trend": trend, "action": action})

    # P2: Mortgage
    if mortgage is not None:
        dist_to_650 = round((mortgage - 6.50) * 100, 0) if mortgage >= 6.50 else round((6.50 - mortgage) * 100, 0)
        status = f"已触及+{dist_to_650}bp" if mortgage >= 6.50 else f"距触发{dist_to_650}bp"
        trend = trend_arrow(mtg_s, 5) if mtg_s else "?"
        mtg_cond = abcd["B"]["details"].get("Mortgage", {}).get("cond_met", False)
        action = "条件满足✅" if mtg_cond else "条件不满足(HY<455bp)"
        rows.append({"priority": "P2", "indicator": "Mortgage", "value": f"{mortgage:.2f}%",
                     "trigger": "6.50%", "distance": status, "dur": "需2周",
                     "trend": trend, "action": action})

    # P2: 5Y5Y
    if t5y5y is not None:
        dist_to_245 = round((2.45 - t5y5y) * 100, 0) if t5y5y < 2.45 else round((t5y5y - 2.45) * 100, 0)
        status = f"已越🟠线+{dist_to_245}bp" if t5y5y >= 2.45 else f"距🟠{dist_to_245}bp"
        trend = trend_arrow(t5y5y_s, 5) if t5y5y_s else "?"
        rows.append({"priority": "P2", "indicator": "5Y5Y", "value": f"{t5y5y:.2f}%",
                     "trigger": "2.45%(🟠)", "distance": status, "dur": "—",
                     "trend": trend, "action": "仅观察"})

    return rows


def compute_checklist(abcd: dict, pos: dict) -> list[str]:
    """Generate tomorrow checklist items."""
    items = []
    dur5_dfii = abcd["C"]["details"].get("DFII10", {}).get("dur5", 0)
    dur5_effr = abcd["A"]["details"].get("EFFR-IORB", {}).get("dur5", 0)

    if dur5_dfii >= 5:
        items.append("DFII10 是否继续 >2.00%？维持计数已确认，关注是否回落至 ≤2.00%")
    else:
        items.append(f"DFII10 DUR5 计数推进/清零？(当前 {dur5_dfii}/5)")

    if dur5_effr >= 5:
        items.append(f"EFFR-IORB DUR5 确认后是否继续维持在 🟠 区间")
    else:
        items.append(f"EFFR-IORB DUR5 计数推进？(当前 {dur5_effr}/5)")

    items.append("HY OAS / IG OAS 脱离自满区？(突破 300bp / 85bp 将结束 ⚠️ 状态)")
    items.append("Mortgage 连续两周站稳 + HY OAS>P50(455bp)？")
    items.append("背离状态变化？B端是否从⚠️升级为🟡？")
    items.append("D 端新压力信号？")

    return items


def compute_position(abcd: dict, v35: dict) -> dict:
    """Full S1-S5 position computation (v3.5)."""
    cross_count = abcd["cross_domain_count"]
    red_count   = abcd["red_domain_count"]
    has_red     = abcd["has_red"]
    b_light     = abcd["B"]["light"]
    a_light     = abcd["A"]["light"]
    c_light     = abcd["C"]["light"]

    dur5_effr   = abcd["A"]["details"].get("EFFR-IORB", {}).get("dur5", 0)
    dur5_dfii   = abcd["C"]["details"].get("DFII10", {}).get("dur5", 0)

    # --- S1 Regime ---
    if cross_count >= 4 or (v35.get("extreme_hit", []) and has_red):
        regime_key = "R5"
    elif red_count >= 2:
        regime_key = "R4"
    elif cross_count >= 3:
        regime_key = "R4"
    elif cross_count >= 2 or has_red:
        regime_key = "R3"
    elif cross_count == 1 or b_light == "⚠️":
        regime_key = "R2"
    else:
        regime_key = "R1"

    base = dict(POSITION_MATRIX[regime_key])
    pos = {"Primary": base["Primary"], "Hedge": base["Hedge"], "Cash": base["Cash"],
           "regime_key": regime_key, "label": base["label"]}

    steps = []
    prev_regime = "R2"  # assumed prior state
    if regime_key != "R2":
        prev_regime = {
            "R3": "R2", "R4": "R2", "R5": "R2", "R1": "R2"
        }.get(regime_key, "R2")

    s1_note = f"§0.6 第一层：{cross_count}跨域信号"
    if has_red:
        s1_note += f"，{red_count}🔴→{regime_key}"
    elif cross_count >= 2:
        s1_note += f"🟠→{regime_key}"
    elif cross_count == 1:
        s1_note += f"→{regime_key}"
    else:
        s1_note += f"→{regime_key}"

    delta_p = pos["Primary"] - 55  # relative to R2 base
    if delta_p != 0:
        s1_note += f"，Primary {'+' if delta_p > 0 else ''}{delta_p}pp"

    steps.append({"step": "起点", "source": f"{prev_regime}基准",
                  "primary": 55, "hedge": 25, "cash": 20,
                  "note": "§0.6 第二层"})
    steps.append({"step": "S1 Regime", "source": f"跨域信号={cross_count}",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": s1_note})

    # --- S2 Divergence ---
    ab_bearish = a_light in ("🟠", "🔴") and b_light in ("⚠️", "🟢", "N/A")
    cb_bearish = c_light in ("🟠", "🔴") and b_light in ("⚠️", "🟢", "N/A")

    if ab_bearish:
        old_p = pos["Primary"]
        pos["Primary"] = max(pos["Primary"] - 5, 5)
        pos["Hedge"]   = pos["Hedge"] + 5
        steps.append({"step": "S2 背离", "source": "A-B Bearish 🔴",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": f"§0.6 第七层：Hedge +5pp (Primary {old_p}→{pos['Primary']})"})
    elif cb_bearish:
        steps.append({"step": "S2 背离", "source": "C-B Bearish 🟠",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": "§0.6 第七层：仅标注'脆弱均衡'，不触发仓位调整"})

    pos["ab_bearish"] = ab_bearish
    pos["cb_bearish"] = cb_bearish

    # --- S3 Margin (A🟠 DUR5 confirmed → -5pp Primary) ---
    if a_light in ("🟠",) and dur5_effr >= 5 and not ab_bearish:
        old_p = pos["Primary"]
        pos["Primary"] = max(pos["Primary"] - 5, 5)
        pos["Cash"]    = pos["Cash"] + 5
        steps.append({"step": "S3 边际", "source": "A🟠 DUR5确认",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": f"§0.6 第三层：A端🟠 −5pp Primary → +5pp Cash"})

    # --- S4 Circuit Breaker ---
    vix_val = v35.get("vix", 0)
    hy_oas_pct = v35.get("hy_oas_pct", 0)
    effr_iorb_bp = v35.get("effr_iorb_bp", 0)
    sofr_iorb_bp = v35.get("sofr_iorb_bp", 0)
    dfii_val = abcd["C"]["details"].get("DFII10", {}).get("value_pct", 0)

    melt_count = 0
    if hy_oas_pct > 5:
        melt_count += 1
    if vix_val > 35:
        melt_count += 1
    if effr_iorb_bp and effr_iorb_bp > 5:
        melt_count += 1
    if sofr_iorb_bp and sofr_iorb_bp > 20:
        melt_count += 1
    # DFII10 > P90 proxy (~2.7%) as 5th condition
    if dfii_val and dfii_val > 2.7:
        melt_count += 1

    s4_note = f"§0.6 第四层：{melt_count}/5条件满足"
    if melt_count >= 2:
        s4_note += f" → 触发熔断(Hedge+10pp)"
        pos["Hedge"] = pos["Hedge"] + 10
        pos["Cash"]  = pos["Cash"] - 10
    else:
        s4_note += " → 不触发"
    steps.append({"step": "S4 熔断", "source": f"{melt_count}/5条件",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": s4_note})

    # --- S5 Weekend Gap ---
    # Check if today is Friday (weekday() == 4)
    import datetime as _dt
    today_wd = _dt.date.today().weekday()
    is_friday = today_wd == 4
    gap_note = "非周末，不执行Gap buffer" if not is_friday else f"周五→执行Gap buffer(Cash+5pp)"
    if is_friday:
        pos["Primary"] = max(pos["Primary"] - 5, 0)
        pos["Cash"]    = pos["Cash"] + 5

    steps.append({"step": "S5 Weekend", "source": f"周五={'是' if is_friday else '否'}",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": gap_note})

    pos["steps"] = steps
    return pos


# ---------------------------------------------------------------------------
# Report formatters
# ---------------------------------------------------------------------------

def format_text_report(
    curve: dict, hy: dict, v35: dict, fw: dict, liq: dict, abcd: dict, pos: dict,
    prox: list[dict], checklist: list[str],
    data_date: str,
) -> str:
    """Plain text regime report (ABCD v3.5)."""
    lines = []

    # Header
    lines.append("=" * 64)
    lines.append(f"  ABCD v3.5 Daily Regime Report -- {data_date}")
    lines.append("=" * 64)

    # Core diagnosis
    lines.append("")
    lines.append("-" * 48)
    lines.append("  核心诊断")
    lines.append("-" * 48)
    for dk, label in [("A", "近端流动性"), ("B", "信用周期"), ("C", "远端风险溢价"), ("D", "跨境离岸")]:
        lines.append(f"  {dk} ({label}): {abcd[dk]['light']}")
    lines.append(f"  Regime: {pos['label']}  |  跨域信号: {abcd['cross_domain_count']}")
    div_str = "/".join(filter(None, [
        "A-B Bearish" if pos.get("ab_bearish") else "",
        "C-B Bearish" if pos.get("cb_bearish") else "",
    ])) or "无"
    lines.append(f"  背离: {div_str}")

    # v3.5 signals (compact)
    lines.append("")
    lines.append("-" * 48)
    lines.append("  v3.5 SIGNALS")
    lines.append("-" * 48)
    dd_s = "!! TRIGGERED !!" if v35["drawdown_warning"] else "OK"
    lines.append(f"  Drawdown Warning: {dd_s}  (HY OAS={v35['hy_oas_pct']}%, 20dΔ={v35['hy_oas_20d_delta_bp']:+.1f}bp)")
    ex_s = f"!! {len(v35['extreme_hit'])} ACTIVE !!" if v35["extreme_hit"] else "OK"
    lines.append(f"  Extreme Meltdown: {ex_s}  (VIX={v35['vix']}, SOFR-IORB={v35['sofr_iorb_bp']}bp)")

    # Liquidity
    lines.append("")
    lines.append("-" * 48)
    lines.append("  LAYER 1: System Plumbing")
    lines.append("-" * 48)
    if liq["rrp_b"] is not None:
        rrp_note = " !! <$100B !!" if liq["rrp_under_100b"] else ""
        lines.append(f"  ON RRP:    ${liq['rrp_b']:.1f}B{rrp_note}")
    if liq["sofr_iorb_bp"] is not None:
        lines.append(f"  SOFR-IORB: {liq['sofr_iorb_bp']:.1f}bp")
    if liq["reserves_b"] is not None:
        lines.append(f"  Reserves:  ${liq['reserves_b']:.0f}B")

    # Missing data
    if v35["missing_sources"]:
        lines.append("")
        for m in v35["missing_sources"]:
            lines.append(f"  ⚠️  Missing: {m}")

    # 四端快照
    lines.append("")
    lines.append("-" * 48)
    lines.append("  四端快照")
    lines.append("-" * 48)
    for dk in ["A", "B", "C", "D"]:
        for row in abcd[dk].get("rows", []):
            lines.append(f"  {row['name']:12s} {row['value_str']:>10s}  Δ20d={row['delta_str']:>8s}  {row['light']:6s} [{row['type']:10s}] DUR={row['dur']}")

    # 触发距离
    lines.append("")
    lines.append("-" * 48)
    lines.append("  触发距离")
    lines.append("-" * 48)
    for r in prox:
        lines.append(f"  [{r['priority']}] {r['indicator']:16s} {r['value']:>10s}  →{r['trigger']}  {r['distance']:20s}  DUR={r['dur']:5s}  {r['trend']}  {r['action']}")

    # Position
    lines.append("")
    lines.append("-" * 48)
    lines.append(f"  仓位动作 — {pos['label']}")
    lines.append("-" * 48)
    for step in pos["steps"]:
        lines.append(f"  [{step['step']:12s}] {step['source']:20s} P={step['primary']:>3}% H={step['hedge']:>3}% C={step['cash']:>3}% — {step['note']}")

    # Tomorrow checklist
    lines.append("")
    lines.append("-" * 48)
    lines.append("  明日检查")
    lines.append("-" * 48)
    for item in checklist:
        lines.append(f"  [ ] {item}")

    lines.append("")
    lines.append("=" * 64)
    lines.append(f"  ABCD v3.5 — {pos['label']} P{pos['Primary']}% / H{pos['Hedge']}% / C{pos['Cash']}%")
    lines.append("  Sources: FRED + Yahoo Finance (auto-updated daily)")
    lines.append("=" * 64)

    return "\n".join(lines)


def format_markdown_report(
    curve: dict, hy: dict, v35: dict, fw: dict, liq: dict, abcd: dict, pos: dict,
    prox: list[dict], checklist: list[str],
    data_date: str,
) -> str:
    """Markdown report in ABCD v3.5 诊断简报 format."""
    lines = []
    lines.append(f"# {data_date} ABCD 诊断简报（日更版）")
    lines.append("")
    lines.append(f"> 数据：FRED + Yahoo Finance | 快照：{data_date} EOD | SOP：v3.5 | 两轨制：ABS/DUR=生效，ROLL=评估")
    lines.append("")

    # ====== 核心诊断 ======
    lines.append("## 核心诊断")
    lines.append("")
    domain_labels = {"A": "近端流动性", "B": "信用周期", "C": "远端风险溢价", "D": "跨境离岸"}

    # DUR confirmation strings
    dur5_effr = abcd["A"]["details"].get("EFFR-IORB", {}).get("dur5", 0)
    dur5_dfii = abcd["C"]["details"].get("DFII10", {}).get("dur5", 0)
    a_dur_str = f"DUR5={dur5_effr}/5 {'✅' if dur5_effr >= 5 else ''}"
    c_dur_str = f"DUR5={dur5_dfii}/5 {'✅' if dur5_dfii >= 5 else ''}"

    dur_map = {
        "A": a_dur_str,
        "B": "N/A",
        "C": c_dur_str,
        "D": "N/A",
    }
    consume_map = {
        "A": "✅" if dur5_effr >= 5 else "❌",
        "B": "N/A",
        "C": "✅" if dur5_dfii >= 5 else "❌",
        "D": "N/A",
    }

    lines.append("| 端 | 灯色 | DUR 确认 | 仓位消费？ |")
    lines.append("|----|------|---------|----------|")
    for dk in ["A", "B", "C", "D"]:
        light = abcd[dk]["light"]
        dur = dur_map[dk]
        consume = consume_map[dk]
        lines.append(f"| {dk} | {light} | {dur} | {consume} |")
    lines.append("")

    # Divergence notes
    div_notes = []
    if pos.get("ab_bearish"):
        div_notes.append("A-B Bearish 🔴 (+5pp Hedge)")
    if pos.get("cb_bearish"):
        div_notes.append("C-B Bearish 🟠 (仅标注)")
    div_str = " / ".join(div_notes) if div_notes else "无"
    lines.append(f"- **Regime**：**{pos['label']}** ⚡")
    lines.append(f"- **背离**：{div_str}")
    lines.append(f"- **今日一句话**：{pos['label']}，跨域信号={abcd['cross_domain_count']}，🔴={abcd['red_domain_count']}个域")
    lines.append("")

    # ====== v3.5 Signal Status (compact) ======
    dd = "!! TRIGGERED !!" if v35["drawdown_warning"] else "OK"
    ex = f"!! {len(v35['extreme_hit'])} ACTIVE !!" if v35["extreme_hit"] else "OK"
    lines.append("## v3.5 信号检查")
    lines.append("")
    lines.append(f"| 信号 | 状态 | 指标 |")
    lines.append(f"|------|------|------|")
    lines.append(f"| Drawdown Warning | {dd} | HY OAS={v35['hy_oas_pct']}%, 20dΔ={v35['hy_oas_20d_delta_bp']:+.1f}bp |")
    hyg_s = f"!! {v35['hyg_5d_ret_pct']:+.1f}% !!" if v35["hyg_trigger"] else f"OK ({v35['hyg_5d_ret_pct']:+.1f}%)" if v35['hyg_5d_ret_pct'] is not None else "N/A"
    fxy_s = f"!! {v35['fxy_5d_ret_pct']:+.1f}% !!" if v35["fxy_trigger"] else f"OK ({v35['fxy_5d_ret_pct']:+.1f}%)" if v35['fxy_5d_ret_pct'] is not None else "N/A"
    spy_s = f"!! SPY={v35['spy_price']} < 200MA={v35['spy_200ma']} !!" if v35["spy_below_200ma"] else f"OK"
    lines.append(f"| HYG 5d <-1.5% | {hyg_s} | HYG={v35['hyg_price']} |")
    lines.append(f"| FXY 5d >+2.5% | {fxy_s} | FXY={v35['fxy_price']} |")
    lines.append(f"| SPY < 200MA | {spy_s} | — |")
    lines.append(f"| Extreme Meltdown | {ex} | VIX={v35['vix']}, SOFR-IORB={v35['sofr_iorb_bp']}bp |")
    lines.append("")

    # ====== 四端快照 ======
    lines.append("## 四端快照")
    lines.append("")
    lines.append("| 端 | 指标 | 当前值 | 20d Δ | 阈值区间 | 判定 | 类型 | DUR 状态 |")
    lines.append("|----|------|--------|-------|---------|------|------|---------|")
    for dk in ["A", "B", "C", "D"]:
        for row in abcd[dk].get("rows", []):
            lines.append(f"| {row['domain']} | {row['name']} | {row['value_str']} | {row['delta_str']} | {row['thresh_str']} | {row['light']} | {row['type']} | {row['dur']} |")
    lines.append("")

    # ====== 触发距离 ======
    lines.append("## 触发距离")
    lines.append("")
    lines.append("| 优先级 | 指标 | 当前值 | 触发线 | 距离 | DUR 计数 | 趋势 | 动作 |")
    lines.append("|--------|------|--------|--------|------|---------|------|------|")
    for r in prox:
        lines.append(f"| {r['priority']} | {r['indicator']} | {r['value']} | {r['trigger']} | {r['distance']} | {r['dur']} | {r['trend']} | {r['action']} |")
    lines.append("")

    # ====== 仓位动作 ======
    lines.append("## 仓位动作（Step-by-step 审计版）")
    lines.append("")
    lines.append("| Step | 来源 | Primary | Hedge | Cash | 说明 |")
    lines.append("|------|------|---------|-------|------|------|")
    for step in pos["steps"]:
        prefix = "**" if step["step"] == "终点" else ""
        suffix = "**" if step["step"] == "终点" else ""
        lines.append(f"| {step['step']} | {step['source']} | {prefix}{step['primary']}%{suffix} | {prefix}{step['hedge']}%{suffix} | {prefix}{step['cash']}%{suffix} | {step['note']} |")

    # Endpoint row
    lines.append(f"| **终点** | — | **{pos['Primary']}%** | **{pos['Hedge']}%** | **{pos['Cash']}%** | {pos['label']} |")
    lines.append("")

    # ====== 明日检查 ======
    lines.append("## 明日检查")
    lines.append("")
    for item in checklist:
        lines.append(f"- [ ] {item}")
    lines.append("")

    # ====== Layer 1 ======
    lines.append("## Layer 1: System Plumbing")
    lines.append("")
    lines.append("| Indicator | Value | Status |")
    lines.append("|------|------|------|")
    if liq["rrp_b"] is not None:
        rrp_s = "!! <$100B Tightening !!" if liq["rrp_under_100b"] else "Normal"
        lines.append(f"| ON RRP | ${liq['rrp_b']:.1f}B | {rrp_s} |")
    if liq["sofr_iorb_bp"] is not None:
        lines.append(f"| SOFR-IORB | {liq['sofr_iorb_bp']:.1f}bp | — |")
    if liq["reserves_b"] is not None:
        lines.append(f"| Reserves | ${liq['reserves_b']:.0f}B | — |")
    lines.append("")

    lines.append("---")
    lines.append(f"*ABCD v3.5 — mechanized mapping. v3.5 drawdown warning = not directional sell. Sources: FRED + Yahoo Finance.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Force UTF-8 on Windows
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(description="Liquidity Daily Regime Report")
    parser.add_argument("--md", action="store_true", help="Output markdown format")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    args = parser.parse_args()

    raw = load_data()

    # Determine data freshness
    hy_data = raw.get(HY_OAS_ID, [])
    data_date = last_date(hy_data) or date.today().isoformat()

    # Compute all regimes
    curve    = compute_curve_regime(raw)
    hy_stress = compute_hy_stress(raw)
    v35      = compute_v35_triggers(raw)
    fw       = compute_framework(raw)
    liq      = compute_liquidity(raw)
    abcd     = compute_abcd_signals(raw)
    pos      = compute_position(abcd, v35)
    prox     = compute_trigger_proximity(abcd, raw)
    chk      = compute_checklist(abcd, pos)

    # --- JSON output ---
    if args.json:
        report = {
            "date": data_date,
            "curve": curve,
            "hy_stress": hy_stress,
            "v35": v35,
            "framework": fw,
            "liquidity": liq,
            "abcd": {
                "A": abcd["A"]["light"],
                "B": abcd["B"]["light"],
                "C": abcd["C"]["light"],
                "D": abcd["D"]["light"],
                "cross_domain": abcd["cross_domain_count"],
            },
            "position": {
                "regime": pos["label"],
                "regime_key": pos["regime_key"],
                "primary": pos["Primary"],
                "hedge": pos["Hedge"],
                "cash": pos["Cash"],
                "steps": pos["steps"],
            },
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # --- Markdown output ---
    if args.md:
        md = format_markdown_report(curve, hy_stress, v35, fw, liq, abcd, pos, prox, chk, data_date)
        print(md)

        # Also save to report/ dir
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"daily_{data_date}.md"
        (REPORT_DIR / fname).write_text(md, encoding="utf-8")
        print(f"\n[Saved to report/{fname}]")
        return 0

    # --- Default: text report ---
    print(format_text_report(curve, hy_stress, v35, fw, liq, abcd, pos, prox, chk, data_date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
