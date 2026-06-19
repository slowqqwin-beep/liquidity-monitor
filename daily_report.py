"""
Daily Regime Report Generator
==============================
Reads series.json (auto-updated by GitHub Actions) and outputs a
structured daily report: current regime, v3.5 trigger status, curve
regime, HY stress regime, framework indicators.

Usage:
    python v3.5/daily_report.py                  # print to stdout
    python v3.5/daily_report.py --md              # markdown + paper_trade
    python v3.5/daily_report.py --json            # JSON summary
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORT_DIR = Path(__file__).resolve().parent / "report"
ARCHIVE_DIR = Path(__file__).resolve().parent / "daily_archive"
SERIES_PATH = DATA_DIR / "series.json"

# FRED series IDs we use for regime computation
HY_OAS_ID = "BAMLH0A0HYM2"
VIX_ID    = "VIXCLS"         # FRED, typically T-1
YAHOO_VIX_ID = "^VIX"        # Yahoo same-day, preferred for CASC alignment
YAHOO_VIX3M_ID = "^VIX3M"   # §0.8 VTS: CBOE 3-month VIX (Yahoo)
YAHOO_VIX9D_ID = "^VIX9D"   # §0.8 VTS: CBOE 9-day VIX (Yahoo)
YAHOO_TNX_ID = "^TNX"    # C_RealYield_Nowcast: 10Y名义收益率 (Yahoo, 需÷10转换)

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


# Yahoo Finance
SPY_ID = "SPY"
HYG_ID = "HYG"
FXY_ID    = "FXY"
USDJPY_ID = "USDJPY=X"        # §0.7 CASC FX腿 fallback

GOLD_RATIO_ID = "GOLD_10Y_RATIO"
SOFR_IORB_ID  = "SOFR_IORB"

# 利率路径(代理) 阈值 — 可调常量，待数据校准
# DGS2 − IORB (bp): 负值越大→定价降息越多; 转正→未定价降息/加息风险
RATE_PATH_THRESHOLDS: dict[str, tuple[float, float]] = {
    "显著定价降息":              (-float("inf"), -50),
    "温和定价降息":              (-50, -15),
    "中性/按兵不动":             (-15, 15),
    "降息被price out / 加息风险": (15, float("inf")),
}


# Series frequency map for stale detection
# "default" = daily; weekly = FRED H.4.1 / Freddie Mac Thursday releases
SERIES_FREQ: dict[str, str] = {
    "MORTGAGE30US": "weekly",
    "WRESBAL": "weekly",
    "WALCL": "weekly",
    "WTREGEN": "weekly",
    "THREEFYTP10": "monthly",  # NY Fed ACM term premium, monthly release
    # Derived series that inherit their source frequency
    "MORTGAGE_SPREAD": "weekly",  # derived from MORTGAGE30US
    # DTWEXBGS: daily series but FRED publishes with ~weekly lag
    "DTWEXBGS": "weekly",
    # ^TNX: Yahoo Yahoo 10Y yield, known intermittent availability
    "^TNX": "weekly",
}

# Stale tracker persistence
STALE_DB_PATH = DATA_DIR / "stale_tracker.json"


def _read_aux_banner() -> str | None:
    """Read auxiliary-series degradation banner from fetch_data.py output.

    Lifecycle is managed entirely by fetch_data.py (delete-before-write),
    so this reader does NOT unlink — a same-day re-run keeps the banner visible.
    """
    banner_path = DATA_DIR / "_aux_degraded.txt"
    if banner_path.exists():
        try:
            return banner_path.read_text().strip()
        except Exception:
            return None
    return None


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


def _nth_value_from_end(series: list[dict], n: int) -> float | None:
    """Get value n positions from end (0 = last, 1 = second-to-last, etc)."""
    if len(series) > n:
        return series[-(n + 1)]["value"]
    return None


def _vix_data(data: dict) -> list[dict]:
    """Yahoo ^VIX first (same-day as MOVE/FXY/HYG), FRED VIXCLS fallback."""
    yahoo = data.get(YAHOO_VIX_ID, [])
    if yahoo and last_value(yahoo) is not None:
        return yahoo
    return data.get(VIX_ID, [])


def _clamp_weekday(d: date) -> date:
    """If d falls on weekend, roll back to previous Friday."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _biz_days_between(earlier: date, later: date) -> int:
    """Count weekdays strictly between earlier (exclusive) and later (inclusive)."""
    count = 0
    d = earlier
    while d < later:
        d += timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return count


# FRED series IDs for vintage computation
_FRED_VINTAGE_IDS = [
    HY_OAS_ID, "BAMLC0A0CM", "BAMLEMCBPIOAS",
    VIX_ID, DGS2_ID, DGS5_ID, DGS10_ID, DGS30_ID,
    SOFR_ID, IORB_ID, EFFR_ID, RRP_ID,
    TIPS10_ID, "T10YIE", T5Y5Y_ID, TERMP_ID,
    MORT_ID,
    "WRESBAL", "WTREGEN", "WALCL", "MOVE",
]
# Yahoo series IDs — include VIX family for staleness tracking (CASC/VTS all depend on them)
_YAHOO_VINTAGE_IDS = [SPY_ID, HYG_ID, FXY_ID, "GLD", "^MOVE", "^VIX", "^VIX3M", "^VIX9D"]


def compute_vintages(data: dict) -> dict:
    """Return FRED & Yahoo vintage dates + T-N (trading days behind today)."""
    today = date.today()
    fred_latest = max(
        (last_date(data.get(sid, [])) for sid in _FRED_VINTAGE_IDS if data.get(sid)),
        default=None
    )
    yahoo_latest = max(
        (last_date(data.get(sid, [])) for sid in _YAHOO_VINTAGE_IDS if data.get(sid)),
        default=None
    )
    fred_d = _clamp_weekday(date.fromisoformat(fred_latest)) if fred_latest else today
    yahoo_d = _clamp_weekday(date.fromisoformat(yahoo_latest)) if yahoo_latest else today

    return {
        "fred_date": fred_d.isoformat(),
        "yahoo_date": yahoo_d.isoformat(),
        "fred_tn": _biz_days_between(fred_d, today) if fred_d < today else 0,
        "yahoo_tn": _biz_days_between(yahoo_d, today) if yahoo_d < today else 0,
    }


# ── C_RealYield_Nowcast ──────────────────────────────────────────────────
NOWCAST_CSV_PATH = DATA_DIR / "real_yield_nowcast_history.csv"
COOLING_JSON_PATH = DATA_DIR / "real_yield_cooling_counter.json"

NOWCAST_LEVEL_THRESHOLDS = [
    (2.00, "🔴", "实际利率高压"),
    (1.20, "🟠", "实际利率偏高"),
    (0.50, "🟡", "实际利率中性偏高"),
    (-float("inf"), "🟢", "实际利率宽松"),
]

NOWCAST_DIRECTION_THRESHOLDS = [
    (-float("inf"), -0.07, "🟢", "明显回落"),
    (-0.07, -0.03, "🟡", "小幅回落"),
    (-0.03, 0.03, "⚪", "基本持平"),
    (0.03, 0.07, "🟠", "小幅上行"),
    (0.07, float("inf"), "🔴", "明显上行"),
]


def _estimate_us10y_from_futu(dgs10_val: float, dgs10_date: str,
                              target_date: str | None = None) -> float | None:
    """Estimate 10Y yield on target_date from IEF price delta vs DGS10 anchor.

    IEF (iShares 7-10Y Treasury ETF) effective duration ≈ 7.2 years.
    Δyield_10Y ≈ −ΔIEF% / duration_IEF.

    If target_date is None, estimates to the latest available IEF close.
    Otherwise estimates to the specific target_date (must satisfy: IEF K-line
    has data on both dgs10_date and target_date).

    Returns estimated 10Y yield (%), or None if Futu unavailable.
    """
    try:
        from futu import OpenQuoteContext, RET_OK, KLType, AuType

        q = OpenQuoteContext(host="127.0.0.1", port=11111)
        # pull enough K-lines to cover anchor→target window
        ret, kline, _ = q.request_history_kline(
            code="US.IEF",
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
            start=dgs10_date,
            max_count=10,
        )
        q.close()

        if ret != RET_OK or kline.empty:
            return None

        ief_anchor = None
        ief_target = None
        found_target_date = None

        for _, row in kline.iterrows():
            dt = str(row["time_key"])[:10]
            if dt == dgs10_date:
                ief_anchor = row["close"]
            if target_date and dt == target_date:
                ief_target = row["close"]
                found_target_date = dt
            # keep latest as fallback (for no target_date mode)
            if ief_target is None:
                ief_target = row["close"]
                found_target_date = dt

        if ief_anchor is None or ief_target is None or ief_anchor == 0:
            return None

        IEF_DURATION = 7.2  # effective duration in years
        delta_pct = (ief_target - ief_anchor) / ief_anchor
        delta_yield = -delta_pct / IEF_DURATION  # decimal
        estimated_10y = round(dgs10_val + delta_yield * 100, 2)

        # Guardrail: reject unreasonable jumps (>15bp/day)
        if found_target_date and found_target_date > dgs10_date:
            from datetime import date
            days_diff = (date.fromisoformat(found_target_date) - date.fromisoformat(dgs10_date)).days
            if days_diff > 0 and abs(delta_yield * 100) > 15 * days_diff:
                return None

        # If target_date specified but not found in K-line, degrade gracefully
        if target_date and not found_target_date:
            return None

        return estimated_10y
    except Exception:
        return None


def compute_real_yield_nowcast(data: dict) -> dict:
    """C_RealYield_Nowcast: 10Y实际利率实时估算.

    Returns dict with all nowcast fields, or degraded status on failure.
    """
    result: dict[str, Any] = {
        "status": "ok",
        "us10y_latest": None,
        "us10y_latest_date": None,
        "us10y_source": None,
        "bei10_latest": None,
        "bei10_latest_date": None,
        "bei10_source": None,
        "dfii10_official": None,
        "dfii10_date": None,
        "dfii10_source": None,
        "real_yield_nowcast": None,
        "nowcast_delta_1d": None,
        "nowcast_delta_5d": None,
        "nowcast_level_light": "N/A",
        "nowcast_level_label": "N/A",
        "nowcast_direction": "N/A",
        "nowcast_direction_light": "⚪",
        "real_yield_gap": None,
        "divergence_status": "N/A",
        "cooling_counter": 0,
        "cooling_target": 3,
        "data_status": "ok",
        "degradation_reason": None,
        "asset_map": [],
        # basis calibration (^TNX−T10YIE vs DFII10)
        "basis_median": None,
        "basis_std": None,
        "basis_n_obs": 0,
        "real_yield_nowcast_raw": None,
    }

    # ── 0. Extract source series ──
    tnx_s = data.get(YAHOO_TNX_ID, [])
    dgs10_s = data.get(DGS10_ID, [])
    tnx_date = last_date(tnx_s) if tnx_s else None
    dgs10_date = last_date(dgs10_s) if dgs10_s else None
    dgs10_val = last_value(dgs10_s) if dgs10_s else None

    t10yie_s = data.get("T10YIE", [])
    bei_date_raw = last_date(t10yie_s) if t10yie_s else None

    # ── 1. US10Y nominal (date-matched to BEI when possible) ──
    # Key insight: real_yield_nowcast = US10Y − T10YIE, so both must be
    # on the same date.  FRED T10YIE (BEI) is often 1 day fresher than
    # DGS10.  Use Futu IEF to forward-estimate US10Y to BEI date.
    selected = False

    # Tier 0: BEI date > DGS10 date → estimate 10Y to BEI date via Futu IEF
    if (dgs10_date and dgs10_val is not None and bei_date_raw
            and bei_date_raw > dgs10_date):
        ief_est = _estimate_us10y_from_futu(
            dgs10_val, dgs10_date, target_date=bei_date_raw)
        if ief_est is not None:
            result["us10y_latest"] = ief_est
            result["us10y_latest_date"] = bei_date_raw  # ISO date = BEI date
            result["us10y_source"] = f"Futu IEF estimate for {bei_date_raw} (anchor DGS10 {dgs10_date})"
            selected = True

    # Tier 1: DGS10 already covers BEI date → use DGS10 directly
    if not selected and dgs10_date and dgs10_val is not None:
        if (bei_date_raw and dgs10_date >= bei_date_raw) or dgs10_date:
            result["us10y_latest"] = round(dgs10_val, 2)
            result["us10y_latest_date"] = dgs10_date
            result["us10y_source"] = "FRED DGS10"
            selected = True

    # Tier 2: fresher-date comparison DGS10 vs ^TNX
    if not selected:
        if tnx_s and last_value(tnx_s) is not None and dgs10_date and tnx_date:
            if dgs10_date > tnx_date:
                result["us10y_latest"] = round(dgs10_val, 2)
                result["us10y_latest_date"] = dgs10_date
                result["us10y_source"] = "FRED DGS10"
            else:
                raw_val = last_value(tnx_s)
                us10y = raw_val / 10.0 if raw_val > 10 else raw_val
                result["us10y_latest"] = round(us10y, 2)
                result["us10y_latest_date"] = tnx_date
                result["us10y_source"] = "Yahoo ^TNX"
        elif tnx_s and last_value(tnx_s) is not None:
            raw_val = last_value(tnx_s)
            us10y = raw_val / 10.0 if raw_val > 10 else raw_val
            result["us10y_latest"] = round(us10y, 2)
            result["us10y_latest_date"] = tnx_date
            result["us10y_source"] = "Yahoo ^TNX"
        elif dgs10_s and dgs10_val is not None:
            result["us10y_latest"] = round(dgs10_val, 2)
            result["us10y_latest_date"] = dgs10_date
            result["us10y_source"] = "FRED DGS10"
        else:
            result["status"] = "degraded"
            result["data_status"] = "missing_us10y"
            result["degradation_reason"] = "C_RealYield_Nowcast: missing_us10y (no ^TNX or DGS10)"
            return result

    # ── 2. 10Y BEI ──
    t10yie_s = data.get("T10YIE", [])
    if t10yie_s and last_value(t10yie_s) is not None:
        result["bei10_latest"] = round(last_value(t10yie_s), 2)
        result["bei10_latest_date"] = last_date(t10yie_s)
        result["bei10_source"] = "FRED T10YIE"

        # Check BEI staleness vs US10Y
        if result["bei10_latest_date"] and result["us10y_latest_date"]:
            bei_d = date.fromisoformat(result["bei10_latest_date"])
            us10y_d = date.fromisoformat(result["us10y_latest_date"])
            bei_lag = _biz_days_between(bei_d, us10y_d)
            if bei_lag > 2:
                result["data_status"] = "bei_stale"
    else:
        result["status"] = "degraded"
        result["data_status"] = "missing_bei10"
        result["degradation_reason"] = "C_RealYield_Nowcast: missing_bei10 (no T10YIE)"
        return result

    # ── 3. Official DFII10 ──
    dfii_s = data.get("DFII10", [])
    if dfii_s and last_value(dfii_s) is not None:
        result["dfii10_official"] = round(last_value(dfii_s), 2)
        result["dfii10_date"] = last_date(dfii_s)
        result["dfii10_source"] = "FRED DFII10"

        # Check DFII10 staleness
        if result["dfii10_date"] and result["us10y_latest_date"]:
            dfii_d = date.fromisoformat(result["dfii10_date"])
            us10y_d = date.fromisoformat(result["us10y_latest_date"])
            if _biz_days_between(dfii_d, us10y_d) > 1:
                if result["data_status"] == "ok":
                    result["data_status"] = "dfii_stale"
    else:
        result["degradation_reason"] = (result.get("degradation_reason", "") +
            " | DFII10 official missing").strip(" |")

    # ── 4. Core: real_yield_nowcast = US10Y - BEI ──
    if result["us10y_latest"] is not None and result["bei10_latest"] is not None:
        result["real_yield_nowcast"] = round(result["us10y_latest"] - result["bei10_latest"], 2)

    # ── 5. Basis calibration: ^TNX−T10YIE vs DFII10 ──
    _calibrate_basis(result, data)

    # ── 6. Direction (1d/5d) from history CSV ──
    _load_nowcast_deltas(result, data)

    # ── 7. Gap vs official ──
    if result["real_yield_nowcast"] is not None and result["dfii10_official"] is not None:
        result["real_yield_gap"] = round(result["real_yield_nowcast"] - result["dfii10_official"], 2)
        if abs(result["real_yield_gap"]) >= 0.05:
            result["divergence_status"] = "nowcast_diverges_from_official"
        else:
            result["divergence_status"] = "aligned"

    # ── 8. Level light ──
    ryn = result["real_yield_nowcast"]
    if ryn is not None:
        for lo, light, label in NOWCAST_LEVEL_THRESHOLDS:
            if ryn >= lo:
                result["nowcast_level_light"] = light
                result["nowcast_level_label"] = label
                break

    # ── 9. Direction light ──
    d1 = result["nowcast_delta_1d"]
    if d1 is not None:
        for lo, hi, light, label in NOWCAST_DIRECTION_THRESHOLDS:
            if lo <= d1 < hi:
                result["nowcast_direction"] = label
                result["nowcast_direction_light"] = light
                break

    # ── 10. Cooling counter ──
    _update_cooling_counter(result)

    # ── 11. Asset map ──
    result["asset_map"] = _build_asset_map(result)

    # ── 12. Append to history CSV ──
    _append_nowcast_history(result)

    return result


def _load_nowcast_deltas(result: dict, data: dict) -> None:
    """Load 1d/5d nowcast deltas from history CSV or derive from DFII10."""
    today_str = date.today().isoformat()
    prev_rows: list[dict] = []
    if NOWCAST_CSV_PATH.exists():
        try:
            import csv
            with NOWCAST_CSV_PATH.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                prev_rows = list(reader)
        except Exception:
            pass

    if prev_rows:
        # Find last row strictly BEFORE today (to avoid comparing today vs today)
        try:
            prev_row = None
            for row in reversed(prev_rows):
                if row.get("date", "") < today_str:
                    prev_row = row
                    break
            if prev_row is not None:
                prev_nc = float(prev_row.get("real_yield_nowcast", "nan"))
                if not math.isnan(prev_nc) and result["real_yield_nowcast"] is not None:
                    result["nowcast_delta_1d"] = round(result["real_yield_nowcast"] - prev_nc, 2)
        except (ValueError, KeyError):
            pass

        # Find 5d-ago row (skip today's row)
        try:
            from datetime import timedelta
            target_d = date.today() - timedelta(days=7)  # ~5 biz days
            target_s = target_d.isoformat()
            for row in prev_rows:
                row_d = row.get("date", "")
                if row_d < today_str and row_d >= target_s:
                    nc5 = float(row.get("real_yield_nowcast", "nan"))
                    if not math.isnan(nc5) and result["real_yield_nowcast"] is not None:
                        result["nowcast_delta_5d"] = round(result["real_yield_nowcast"] - nc5, 2)
                    break
        except (ValueError, KeyError):
            pass

    # Fallback: use DFII10 delta if history not available
    dfii_s = data.get("DFII10", [])
    if result["nowcast_delta_1d"] is None and dfii_s and len(dfii_s) >= 2:
        dfii_now = last_value(dfii_s)
        dfii_prev = dfii_s[-2]["value"] if len(dfii_s) >= 2 else None
        if dfii_now is not None and dfii_prev is not None:
            result["nowcast_delta_1d"] = round(dfii_now - dfii_prev, 2)
            result["nowcast_delta_1d_warming"] = True
    if result["nowcast_delta_5d"] is None and dfii_s and len(dfii_s) >= 6:
        n = _nth_value_from_end(dfii_s, 5)
        if n is not None and last_value(dfii_s) is not None:
            result["nowcast_delta_5d"] = round(last_value(dfii_s) - n, 2)
            result["nowcast_delta_5d_warming"] = True


def _calibrate_basis(result: dict, data: dict) -> None:
    """Calibrate ^TNX−T10YIE vs DFII10 basis spread.

    ^TNX (CBOE 10Y yield index, Yahoo) and DGS10 (FRED CMT) have a persistent
    quoting-convention spread.  This inflates the naïve nowcast = ^TNX − T10YIE
    relative to the official DFII10 real yield.

    We compute basis(t) = (^TNX/10 − T10YIE) − DFII10 for every date where all
    three series overlap, take the *252-trading-day rolling median* as the
    expected basis, and subtract it from the raw nowcast.
    """
    tnx_s = data.get("^TNX", [])
    t10yie_s = data.get("T10YIE", [])
    dfii_s = data.get("DFII10", [])

    if not tnx_s or not t10yie_s or not dfii_s:
        return

    # Build date-indexed dicts
    tnx_d = {r["date"]: r["value"] for r in tnx_s}
    t10yie_d = {r["date"]: r["value"] for r in t10yie_s}
    dfii_d = {r["date"]: r["value"] for r in dfii_s}

    # Common dates across all three series
    common_dates = sorted(set(tnx_d.keys()) & set(t10yie_d.keys()) & set(dfii_d.keys()))
    if len(common_dates) < 1:
        result["basis_note"] = "insufficient overlap for basis calibration"
        return

    # Compute basis on each common date
    basis_pairs: list[tuple[str, float]] = []
    for d in common_dates:
        # Same ^TNX decode logic as compute_real_yield_nowcast
        raw_val = tnx_d[d]
        us10y = raw_val / 10.0 if raw_val > 10 else raw_val
        implied_real = us10y - t10yie_d[d]
        basis = implied_real - dfii_d[d]
        basis_pairs.append((d, basis))

    # 252-trading-day rolling window (or all available if fewer)
    n_lookback = min(252, len(basis_pairs))
    recent = basis_pairs[-n_lookback:]
    basis_vals = [b for _, b in recent]

    # Median
    s = sorted(basis_vals)
    m = len(s)
    if m % 2 == 1:
        basis_median = s[m // 2]
    else:
        basis_median = (s[m // 2 - 1] + s[m // 2]) / 2

    # Standard deviation (sample std, requires n ≥ 2)
    if m >= 2:
        mean = sum(basis_vals) / m
        basis_std = math.sqrt(sum((b - mean) ** 2 for b in basis_vals) / (m - 1))
    else:
        basis_std = 0.0

    result["basis_median"] = round(basis_median, 4)
    result["basis_std"] = round(basis_std, 4)
    result["basis_n_obs"] = m
    result["basis_last_date"] = recent[-1][0]

    # ── Apply calibration ──
    raw = result.get("real_yield_nowcast")
    if raw is not None:
        result["real_yield_nowcast_raw"] = raw
        result["real_yield_nowcast"] = round(raw - basis_median, 2)


def _update_cooling_counter(result: dict) -> None:
    """Persist and update C_real_yield_cooling_counter."""
    ryn = result["real_yield_nowcast"]
    if ryn is None:
        result["cooling_counter"] = 0
        return

    prev_counter = 0
    if COOLING_JSON_PATH.exists():
        try:
            prev = json.loads(COOLING_JSON_PATH.read_text(encoding="utf-8"))
            prev_counter = prev.get("cooling_counter", 0)
        except Exception:
            pass

    if ryn < 2.00:
        result["cooling_counter"] = min(prev_counter + 1, result["cooling_target"])
    else:
        result["cooling_counter"] = 0

    # Persist
    try:
        COOLING_JSON_PATH.write_text(json.dumps({
            "cooling_counter": result["cooling_counter"],
            "last_update": date.today().isoformat(),
        }, indent=2), encoding="utf-8")
    except Exception:
        pass


def _build_asset_map(result: dict) -> list[dict]:
    """Generate asset implication rows based on nowcast state."""
    ryn = result["real_yield_nowcast"]
    direction = result["nowcast_direction"]
    level = result["nowcast_level_label"]
    d_warming = result.get("nowcast_delta_1d_warming", False)
    d_meaningful = not d_warming and direction != "N/A"

    rows = []
    # Gold
    if d_meaningful and direction in ("明显回落", "小幅回落"):
        gld_note = "实际利率回落→黄金压力边际缓和"
    elif ryn is not None and ryn >= 2.00:
        gld_note = "实际利率>2%，黄金仍在顶部区承压，只能称为'松动'，非趋势反转"
    elif d_meaningful and direction in ("明显上行", "小幅上行"):
        gld_note = "实际利率上行→黄金压力加大"
    else:
        gld_note = "等待方向确认"

    # Industrial metals
    bei_val = result["bei10_latest"]
    if bei_val is not None and bei_val >= 2.0 and (not d_meaningful or direction not in ("明显上行",)):
        ind_note = "BEI稳定，工业金属可交易再通胀/供给冲击路径"
    elif d_meaningful and direction in ("明显上行",):
        ind_note = "实际利率上行+BEI走弱→工业金属承压"
    else:
        ind_note = "关注BEI与信用OAS联动"

    # High-valuation tech — conditioned on actual direction
    if ryn is not None and ryn >= 2.00:
        if d_meaningful and direction in ("明显回落", "小幅回落"):
            tech_note = f"实际利率仍>{2.00}%，高估值科技受绝对水平压制。Nowcast回落利于反弹，但估值压力未完全解除"
        elif d_meaningful and direction in ("明显上行", "小幅上行"):
            tech_note = f"实际利率仍>{2.00}%，Nowcast继续上行→高估值科技压力强化"
        else:
            tech_note = f"实际利率仍>{2.00}%，高估值科技受绝对水平压制。方向待确认或方向数据累积中。"
    else:
        tech_note = "实际利率<2%，估值压力有所缓解"

    # Broad equity
    if ryn is not None and ryn < 2.00:
        eq_note = "信用端稳定+Nowcast回落，宽基beta风险下降"
    elif d_meaningful and direction in ("明显回落", "小幅回落"):
        eq_note = "实际利率边际回落，宽基压力缓和"
    elif d_meaningful and direction in ("明显上行", "小幅上行"):
        eq_note = "实际利率继续上行，宽基估值承压"
    else:
        eq_note = "实际利率高位运行，宽基估值承压"

    return [
        {"asset": "黄金/贵金属", "note": gld_note},
        {"asset": "工业金属/有色", "note": ind_note},
        {"asset": "高估值科技", "note": tech_note},
        {"asset": "宽基权益", "note": eq_note},
    ]


def _append_nowcast_history(result: dict) -> None:
    """Append a row to real_yield_nowcast_history.csv."""
    today_str = date.today().isoformat()
    row = {
        "date": today_str,
        "us10y_latest": result.get("us10y_latest", ""),
        "us10y_date": result.get("us10y_latest_date", ""),
        "bei10_latest": result.get("bei10_latest", ""),
        "bei10_date": result.get("bei10_latest_date", ""),
        "dfii10_official": result.get("dfii10_official", ""),
        "dfii10_date": result.get("dfii10_date", ""),
        "real_yield_nowcast": result.get("real_yield_nowcast", ""),
        "nowcast_delta_1d": result.get("nowcast_delta_1d", ""),
        "nowcast_delta_5d": result.get("nowcast_delta_5d", ""),
        "data_status": result.get("data_status", ""),
        "note": result.get("degradation_reason", ""),
    }
    try:
        import csv
        fieldnames = list(row.keys())
        file_exists = NOWCAST_CSV_PATH.exists()
        with NOWCAST_CSV_PATH.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            # Dedup: skip if today already exists
            if file_exists:
                try:
                    with NOWCAST_CSV_PATH.open("r", encoding="utf-8") as rf:
                        existing = list(csv.DictReader(rf))
                    if any(r.get("date") == today_str for r in existing):
                        return
                except Exception:
                    pass
            writer.writerow(row)
    except Exception:
        pass


def data_source_vintage_str(vint: dict) -> str:
    """Format vintage line — 'fetch' date, not per-series as-of.
    Individual series as-of dates are shown in per-component tables (e.g. Nowcast block)."""
    parts = []
    if vint["fred_date"]:
        parts.append(f"FRED fetch: {vint['fred_date'][-5:]} (T-{vint['fred_tn']})")
    if vint["yahoo_date"]:
        parts.append(f"Yahoo fetch: {vint['yahoo_date'][-5:]} (T-{vint['yahoo_tn']})")
    return " | ".join(parts)


# --- Stale detection (frequency-aware) ---

def _last_dates_snapshot(data: dict) -> dict[str, str]:
    """Capture the last data date for every series as {series_id: date_str}."""
    snap: dict[str, str] = {}
    for sid, series in data.items():
        ld = last_date(series)
        if ld:
            snap[sid] = ld
    return snap


def load_stale_tracker() -> dict:
    if STALE_DB_PATH.exists():
        try:
            with STALE_DB_PATH.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_stale_tracker(tracker: dict) -> None:
    STALE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STALE_DB_PATH.open("w") as f:
        json.dump(tracker, f, indent=2)


def check_staleness(data: dict) -> list[str]:
    """Compare current last-dates against previous snapshot; flag series that
    haven't advanced within their frequency tolerance.
    Returns list of warning strings (empty = no staleness).
    """
    prev = load_stale_tracker()
    cur = _last_dates_snapshot(data)
    today = date.today()

    warnings: list[str] = []
    for sid, cur_date_str in sorted(cur.items()):
        freq = SERIES_FREQ.get(sid, "daily")
        cur_d = date.fromisoformat(cur_date_str)

        if freq == "monthly":
            # Monthly: allow up to 35 calendar days without update
            tolerance_days = 35
        elif freq == "weekly":
            # Weekly: allow up to 10 calendar days without update
            # Normal: Thu→Thu=7d + 1d holiday buffer + 2d FRED ingestion lag
            tolerance_days = 10
        else:
            # Daily: allow up to 5 calendar days (covers long weekends)
            tolerance_days = 5

        days_since = (today - cur_d).days
        if days_since > tolerance_days:
            warnings.append(f"⚠️  {sid} 可能未更新 (last: {cur_date_str})")

    # Also catch series that existed in prev but vanished from cur
    for sid in prev:
        if sid not in cur and prev.get(sid):
            warnings.append(f"⚠️  {sid} 已消失 (last known: {prev[sid]})")

    # Persist current snapshot for next run
    save_stale_tracker(cur)
    return warnings


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
    vix  = _vix_data(data)          # Yahoo ^VIX preferred (same-day alignment)
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
    }


def compute_liquidity(data: dict) -> dict:
    """Layer 1: system plumbing."""
    rrp       = last_value(data.get(RRP_ID, []))
    sofr_iorb = last_value(data.get(SOFR_IORB_ID, []))
    wresbal   = last_value(data.get("WRESBAL", []))

    # WRESBAL from FRED is in millions of $; convert to trillions for display
    reserves_t = round(wresbal / 1_000_000, 2) if wresbal else None

    return {
        "rrp_b": round(rrp, 1) if rrp else None,
        "rrp_under_100b": rrp is not None and rrp < 100,
        "rrp_tightening_note": "RRP < $100B = Tightening trigger (Task 3 verified)" if (rrp and rrp < 100) else None,
        "sofr_iorb_bp": round(sofr_iorb, 1) if sofr_iorb else None,
        "reserves_t": reserves_t,
    }


# ---------------------------------------------------------------------------
# 利率路径(代理) — 纯观察项，不进 regime / 仓位
# ---------------------------------------------------------------------------

def _classify_rate_path_level(gap_bp: float) -> str:
    """Map gap_bp to a descriptive level label via RATE_PATH_THRESHOLDS."""
    for label, (lo, hi) in RATE_PATH_THRESHOLDS.items():
        if lo <= gap_bp < hi:
            return label
        if hi == float("inf") and gap_bp >= lo:
            return label
    return "N/A"


def compute_rate_path_proxy(data: dict) -> dict:
    """利率路径(代理): DGS2 − IORB → 市场预期未来~2年平均政策利率 − 当前政策利率。

    纯观察项，绝不进 regime、不进仓位、不参与打分。
    含期限溢价 → 方向/变化比绝对水平更可靠。
    标签含"代理非OIS"，禁止写成 OIS / 精确路径。
    """
    dgs2_s = data.get(DGS2_ID, [])
    iorb_s = data.get(IORB_ID, [])

    dgs2 = last_value(dgs2_s)
    iorb = last_value(iorb_s)

    # N/A if either is missing
    if dgs2 is None or iorb is None:
        return {
            "gap_bp": None, "gap_5d_chg": None,
            "level_label": "N/A(数据缺失)", "direction_str": "",
            "display_str": "利率路径(代理): N/A(数据缺失)",
            "dgs2_pct": None, "iorb_pct": None,
        }

    gap_bp = round((dgs2 - iorb) * 100, 1)

    # 5d change: gap today − gap 5 trading days ago
    dgs2_5d_ago = n_day_ago(dgs2_s, 5)
    iorb_5d_ago = n_day_ago(iorb_s, 5) if (iorb_s and len(iorb_s) >= 6) else iorb

    if dgs2_5d_ago is not None and iorb_5d_ago is not None:
        gap_5d_ago = round((dgs2_5d_ago - iorb_5d_ago) * 100, 1)
        gap_5d_chg = round(gap_bp - gap_5d_ago, 1)
    else:
        gap_5d_chg = None

    level_label = _classify_rate_path_level(gap_bp)

    # Direction string with ±3bp noise filter
    if gap_5d_chg is None:
        direction_str = "5dΔ: N/A"
    elif gap_5d_chg < -3:
        direction_str = f"5dΔ {gap_5d_chg:+.1f}bp ▼ 降息预期升温"
    elif gap_5d_chg > 3:
        direction_str = f"5dΔ {gap_5d_chg:+.1f}bp ▲ 降息被price out"
    else:
        direction_str = f"5dΔ {gap_5d_chg:+.1f}bp → 稳定"

    display_str = f"利率路径(代理) | DGS2−IORB = {gap_bp}bp | {direction_str} | [{level_label} · 代理非OIS]"

    return {
        "gap_bp": gap_bp,
        "gap_5d_chg": gap_5d_chg,
        "level_label": level_label,
        "direction_str": direction_str,
        "display_str": display_str,
        "dgs2_pct": round(dgs2, 3),
        "iorb_pct": round(iorb, 3),
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
    """Map a numeric value to 🟢🟡🟠🔴⚠️ using threshold intervals.

    **区间约定**: 左闭右开 [lo, hi)，即 lo ≤ x < hi。
    - 例如 EFFR-IORB 🟡[-7,-3) → -7.0∈🟡, -3.0∈🟠
    - 上界 inf 时: x ≥ lo 即入该档
    """
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
    delta_unit: str | None = None,
    stale_note: str = "",
) -> dict:
    """Build a single indicator row for the 四端快照 table.
    stale_note: if non-empty, appended to indicator name as inline freshness label.

    *unit* controls formatting of cur_val and threshold display.
    *delta_unit* (if given) overrides the delta suffix independently — use
    when the value is a percentage but the 20d change is in bp (e.g. DFII10
    at 2.07% with Δ20d = +13bp).
    """
    light = light_override or classify_traffic_light(cur_val, thresholds)
    unit_sfx = "%" if "pct" in unit else "bp" if unit == "bp" else ""
    thresh_str = " / ".join(
        f"{c}{lo}{'~' if lo != -float('inf') else '<'}{hi}{unit_sfx}"
        for c, (lo, hi) in thresholds.items()
        if lo != -float("inf")
    )
    thresh_str = thresh_str.replace("inf" + unit_sfx, "+∞").replace("-inf" + unit_sfx, "-∞") if unit_sfx else thresh_str
    # Delta formatting: use delta_unit when provided, else infer from unit
    effective_delta_unit = delta_unit if delta_unit else unit
    if delta_20d is not None and effective_delta_unit == "bp":
        delta_str = f"{delta_20d:+.0f}bp"
    elif delta_20d is not None and "pct" in effective_delta_unit:
        delta_str = f"{delta_20d:+.2f}%"
    elif delta_20d is not None:
        delta_str = f"{delta_20d:+.2f}"
    else:
        delta_str = "—"
    val_str = f"{cur_val:.0f}bp" if cur_val is not None and unit == "bp" else (
        f"${cur_val:.2f}T" if cur_val is not None and unit == "trillion" else (
            f"{cur_val:.2f}%" if cur_val is not None and "pct" in unit else (
                f"{cur_val:.2f}" if cur_val is not None else "N/A"
            )
        )
    )
    return {
        "domain": domain, "name": name + stale_note, "value_str": val_str, "delta_str": delta_str,
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
        _indicator_row("A", "Reserve", reserve_t, "trillion", reserve_20d_t,
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

    # Mortgage conditional — 显示保留原始灯色，聚合不受未激活条件污染
    mtg_cond_met = hy_oas_bp is not None and hy_oas_bp >= 455
    mtg_cond_note = "条件满足" if mtg_cond_met else "条件不满足(HY<455bp)"
    b_mtg_display = b_mtg                      # 原始分类（用于表格显示）
    if b_mtg_display == "🟠" and not mtg_cond_met:
        b_mtg_display = "🟡"                    # 🟠→🟡 降级显示
    b_mtg_agg = b_mtg if mtg_cond_met else "🟢"  # 聚合：条件不满足=无信号

    b_signals = [s for s in [b_hy, b_ig, b_mtg_agg] if s not in ("N/A", "⚠️")]
    b_worst = "N/A"
    if b_signals:
        b_worst = max(b_signals, key=lambda x: COLOR_RANK.get(x, -1))
    if b_worst == "N/A" and "⚠️" in [b_hy, b_ig, b_mtg_agg]:
        b_worst = "⚠️"

    # B/D DUR tracking
    # HY OAS: consecutive days in 🟡(480-650bp) / 🟠(650-950bp) / 🔴(>950bp)
    hy_dur_count = 0
    hy_dur_target = 0  # 0=no DUR needed, 5=🟡, 3=🟠, 0=🔴即时
    if hy_s and hy_oas_bp is not None and b_hy not in ("N/A", "⚠️", "🟢"):
        for d in reversed(hy_s):
            hval = d["value"] * 100
            hlight = classify_traffic_light(hval, B_THRESHOLDS["HY_OAS"])
            if hlight == b_hy:
                hy_dur_count += 1
            else:
                break
        hy_dur_target = {"🟡": 5, "🟠": 3, "🔴": 1}.get(b_hy, 0)

    # IG OAS: consecutive days in 🟡/🟠/🔴
    ig_dur_count = 0
    ig_dur_target = 0
    if ig_s and ig_oas_bp is not None and b_ig not in ("N/A", "⚠️", "🟢"):
        for d in reversed(ig_s):
            ival = d["value"] * 100
            ilight = classify_traffic_light(ival, B_THRESHOLDS["IG_OAS"])
            if ilight == b_ig:
                ig_dur_count += 1
            else:
                break
        ig_dur_target = {"🟡": 5, "🟠": 3, "🔴": 1}.get(b_ig, 0)

    # Mortgage fresh label
    mtg_last_d = last_date(mtg_s)
    mtg_stale_note = ""
    if mtg_last_d:
        from datetime import date as _dt
        try:
            _mtg_dt = _dt.fromisoformat(mtg_last_d)
            _days = (_dt.today() - _mtg_dt).days
            if _days >= 2:
                mtg_stale_note = f" ({mtg_last_d}, {_days}d stale)"
        except ValueError:
            pass

    b_rows = [
        _indicator_row("B", "HY OAS", hy_oas_bp, "bp", hy_20d,
                       B_THRESHOLDS["HY_OAS"], "ROLL+ABS", "—",
                       light_override = "⚠️自满" if b_hy == "⚠️" else b_hy),
        _indicator_row("B", "IG OAS", ig_oas_bp, "bp", ig_20d,
                       B_THRESHOLDS["IG_OAS"], "ROLL+ABS", "—",
                       light_override = "⚠️自满" if b_ig == "⚠️" else b_ig),
        _indicator_row("B", "Mortgage 30Y (PMMS)", mortgage, "pct", mtg_20d,
                       B_THRESHOLDS["Mortgage"], "ABS+条件",
                       mtg_cond_note if b_mtg_display in ("🟡", "🟠") else ("需2周+HY>455bp" if mortgage and mortgage >= 6.5 else "—"),
                       delta_unit="bp",
                       stale_note=mtg_stale_note),
    ]

    b_details = {
        "HY OAS":   {"value_bp": hy_oas_bp, "light": b_hy,
                     "dur_count": hy_dur_count, "dur_target": hy_dur_target},
        "IG OAS":   {"value_bp": ig_oas_bp, "light": b_ig,
                     "dur_count": ig_dur_count, "dur_target": ig_dur_target},
        "Mortgage": {"value_pct": round(mortgage, 2) if mortgage else None, "light": b_mtg_display,
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
                       C_THRESHOLDS["5Y5Y"], "ROLL", "—",
                       delta_unit="bp"),
        _indicator_row("C", "DFII10", dfii10, "pct", dfii_20d,
                       C_THRESHOLDS["DFII10"], "ABS+DUR5",
                       f"{dur5_dfii}/5 {'✅' if dur5_dfii >= 5 else ''}",
                       delta_unit="bp"),
        _indicator_row("C", "10Y BEI", t10yie, "pct", bei_20d,
                       C_THRESHOLDS["10Y_BEI"], "ROLL", "—",
                       delta_unit="bp"),
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

    # FXY 5d DUR: 🟠/🔴=即时(1日), 🟡=—, 🟢=—
    fxy_dur_count = 0
    fxy_dur_target = 0
    if fxy and d_light in ("🟠", "🔴"):
        for d in reversed(fxy):
            vals = [d["value"]]
            if len(fxy) >= 6:  # need at least 6 days for 5d return
                idx = fxy.index(d)
                if idx >= 5:
                    ago5 = fxy[idx - 5]["value"]
                    r5d = (d["value"] - ago5) / ago5 * 100
                    rlight = classify_traffic_light(r5d, D_THRESHOLDS["FXY_5d"])
                    if rlight == d_light:
                        fxy_dur_count += 1
                    else:
                        break
                else:
                    break
            else:
                break
        fxy_dur_target = 1  # instant for 🟠/🔴

    d_rows = [
        _indicator_row("D", "FXY 5d", fxy_5d, "pct", fxy_20d,
                       D_THRESHOLDS["FXY_5d"], "ABS", "—"),
    ]

    d_details = {
        "FXY 5d": {"value_pct": round(fxy_5d, 1) if fxy_5d is not None else None, "light": d_light,
                   "dur_count": fxy_dur_count, "dur_target": fxy_dur_target},
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


# ---------------------------------------------------------------------------
# §0.7 跨资产应力确认层 (CASC — Cross-Asset Stress Confirmation)
#
# 设计原则：
#   ① CASC 门只收 D 端（唯一由反身 5d 信号驱动的端），不收 A/B/C。
#      A/B/C 的灯全由慢变量 (ABS/DUR/ROLL) 判，不需要 cross-asset vol 确认。
#   ② CASC 门不设熔断抑制。
#      HYG 5d、SPY Drawdown Warning、VIX>35 等反身信号只进 v3.5 信号检查 →
#      喂 S4 熔断。熔断是"大额去风险"动作，假阴性(漏掉真崩)远危险于假阳性
#      (白减仓)，给它加确认门会压制触发 → 触发端要保持 trigger-happy。
#   ③ Role B (C端有序/失序) phase-1 仅打标，不动仓位。
#      MOVE 应力/失序时标"失序·利率管道应力"，但不触发 +1 档/R4 评估。
#      待观察几轮 MOVE-C 端联动后再接线。接线规格：§spec §4 —
#      "MOVE 应力(≥125或突变) + C端🟠/🔴 → C端叠加升档(+1档或入R4评估)"。
# ---------------------------------------------------------------------------

# ═══════════════════════════════════════════════════════════════════════════
# §0.8 VIX 期限结构 VTS — 升级 CASC 股票腿确认 + 再入场/降档门
# ═══════════════════════════════════════════════════════════════════════════

VTS_CONTANGO    = 0.95   # VIX/VIX3M < 0.95 = contango·平静
VTS_NEUTRAL     = 1.00   # 0.95 ≤ ratio < 1.00 = 中性
VTS_INVERTED    = 1.00   # ratio ≥ 1.00 = 倒挂·应力 (Use-1 确认阈值)
VTS_ACUTE       = 1.10   # ratio > 1.10 = 倒挂·急性
VTS_NORM_TARGET = 0.95   # ratio ≤ 0.95 = 重建 contango (Use-2 正常化目标)
VTS_NORM_DAYS   = 3      # 持续 ≥3 交易日的 contango 才算正常化

VTS_FRONT_CALM   = 0.95  # VIX9D/VIX < 0.95 = 前端平静
VTS_FRONT_TENSE  = 1.05  # VIX9D/VIX ≥ 0.95 = 前端紧张; > 1.05 = 前端急性


def compute_vts(data: dict) -> dict:
    """§0.8 VIX 期限结构 (VTS) — VIX/VIX3M 主信号 + VIX9D/VIX 可选前端。

    Returns dict:
        available          : bool — VIX3M data present
        vix, vix3m, vix9d  : float | None
        ratio_vix_vix3m    : float | None
        structure          : str — contango / 中性 / 倒挂 / 倒挂·急性 / N/A
        ratio_vix9d_vix    : float | None
        front_structure    : str — 前端平静 / 前端紧张 / 前端急性 / N/A
        was_inverted       : bool — lookback 中曾 ≥1.00
        normalization_days : int — 连续 ≤0.95 的交易日数
        re_entry_gate      : str — 未启用 / 候选 / 放行(需宏观同向) / ABSTAIN
        abstain            : bool — 缺数据时 True (Use-1 回退 level-only, Use-2 暂停)
    """
    vix_s = _vix_data(data)
    vix3m_s = data.get(YAHOO_VIX3M_ID, [])
    vix9d_s = data.get(YAHOO_VIX9D_ID, [])

    vix_val = last_value(vix_s)
    vix3m_val = last_value(vix3m_s)
    vix9d_val = last_value(vix9d_s)

    vix3m_available = vix_val is not None and vix3m_val is not None

    result: dict[str, Any] = {
        "available": vix3m_available,
        "vix": round(vix_val, 2) if vix_val else None,
        "vix3m": round(vix3m_val, 2) if vix3m_val else None,
        "vix9d": round(vix9d_val, 2) if vix9d_val else None,
        "ratio_vix_vix3m": None,
        "structure": "N/A",
        "ratio_vix9d_vix": None,
        "front_structure": "N/A",
        "was_inverted": False,
        "normalization_days": 0,
        "re_entry_gate": "未启用",
        "abstain": not vix3m_available,
    }

    if not vix3m_available:
        return result

    # ── Primary: VIX / VIX3M ──
    ratio = vix_val / vix3m_val
    result["ratio_vix_vix3m"] = round(ratio, 3)

    if ratio >= VTS_ACUTE:
        result["structure"] = "倒挂·急性"
    elif ratio >= VTS_INVERTED:
        result["structure"] = "倒挂"
    elif ratio >= VTS_CONTANGO:
        result["structure"] = "中性"
    else:
        result["structure"] = "contango"

    # ── Optional: VIX9D / VIX (front-end) ──
    if vix9d_val is not None and vix_val is not None:
        front_ratio = vix9d_val / vix_val
        result["ratio_vix9d_vix"] = round(front_ratio, 3)
        if front_ratio >= VTS_FRONT_TENSE:
            result["front_structure"] = "前端急性"
        elif front_ratio >= VTS_FRONT_CALM:
            result["front_structure"] = "前端紧张"
        else:
            result["front_structure"] = "前端平静"

    # ── Use-2: Normalization detection ──
    # Count consecutive days of contango (ratio ≤ 0.95) from most recent backward
    if vix3m_s and vix_s:
        n = min(len(vix_s), len(vix3m_s))
        norm_days = 0
        was_inverted = False

        # Phase 1: count consecutive contango days
        for i in range(1, n + 1):
            v = vix_s[-i].get("value")
            v3 = vix3m_s[-i].get("value")
            if v is None or v3 is None:
                break
            r = v / v3
            if r <= VTS_NORM_TARGET:
                norm_days += 1
            else:
                break

        result["normalization_days"] = norm_days

        # Phase 2: scan backward beyond normalization streak for prior inversion
        if norm_days > 0:
            for j in range(norm_days + 1, n + 1):
                v = vix_s[-j].get("value")
                v3 = vix3m_s[-j].get("value")
                if v is None or v3 is None:
                    break
                r = v / v3
                if r >= VTS_INVERTED:
                    was_inverted = True
                    break
                # Dead-cat bounce guard: if between norm streak and inversion
                # we see re-inversion, reset (the inversion we see is the "current"
                # event, not a prior one we're recovering from)
                if ratio >= VTS_INVERTED:
                    # Still inverted now → was_inverted is about the current episode
                    pass  # continue scanning for truly prior inversion

        result["was_inverted"] = was_inverted

    # ── Re-entry gate determination ──
    if not vix3m_available:
        result["re_entry_gate"] = "ABSTAIN"
    elif result["normalization_days"] >= VTS_NORM_DAYS and result["was_inverted"]:
        result["re_entry_gate"] = "候选"
    elif ratio >= VTS_INVERTED:
        result["re_entry_gate"] = "未启用(仍在倒挂)"
    else:
        result["re_entry_gate"] = "未启用"

    return result


# ═══════════════════════════════════════════════════════════════════════════
# §0.9 利率曲线分段波动 RCV — 补 MOVE 长端盲区 + 利率应力 character
# ═══════════════════════════════════════════════════════════════════════════

RCV_WINDOW       = 20        # rolling window for RV (days)
RCV_HISTORY      = 252       # z-score lookback (trading days)
RCV_MIN_HISTORY  = 60        # minimum history for z-score
RCV_Z_THRESHOLD  = 1.0       # z ≥ 1.0 = elevated vs own history
RCV_Z_ELEVATED   = 1.0       # severity threshold: elevated
RCV_Z_ACUTE      = 2.0       # severity threshold: acute (vol 右偏,z≥2 比高斯更罕见)
RCV_TILT_NEUTRAL = 1.0       # |z_ratio| ≤ 1.0 = no tilt (parallel/broad)
RCV_TENORS       = ["DGS2", "DGS10", "DGS30"]
RCV_TENOR_LABELS = {"DGS2": "2y", "DGS10": "10y", "DGS30": "30y"}


def compute_rcv(data: dict) -> dict:
    """§0.9 利率曲线分段波动 (RCV) — realized rate vol by curve tenor.

    Algorithm: daily bp change → rolling 20d de-meaned sample std → annualized √252.
    Per-tenor (DGS2/DGS10/DGS30), normalized via z-score vs own ~252d history.

    Character:
      - max(z) < 1.0           → balanced/calm
      - leader=2y  & z_2y≥1.0  → front-led  (Fed/政策路径应力)
      - leader=10y & z_10y≥1.0 → belly-led
      - leader=30y & z_30y≥1.0 → long-led   (term premium/财政/拍卖/LDI 应力)

    Returns:
        available, abstain, degradation — data-quality flags
        rv_2y/rv_10y/rv_30y — annualized bp realized vol
        z_2y/z_10y/z_30y    — z-score vs 252d history
        leader, character, long_led — classification
        ratio_2y_30y, z_ratio       — front/long cross-check
    """
    # ── Fetch tenors ──
    tenor_series: dict[str, list[dict]] = {}
    for tid in RCV_TENORS:
        s = data.get(tid, [])
        tenor_series[tid] = s

    available_tenors = [t for t in RCV_TENORS if len(tenor_series.get(t, [])) >= 22]
    abstain = len(available_tenors) < 2

    result: dict[str, Any] = {
        "available": not abstain,
        "abstain": abstain,
        "degradation": "",
        "rv_2y": None, "rv_10y": None, "rv_30y": None,
        "z_2y": None, "z_10y": None, "z_30y": None,
        "leader": "N/A",
        "severity": "N/A",
        "tilt": "N/A",
        "character": "N/A",
        "long_led": False,
        "ratio_2y_30y": None,
        "z_ratio": None,
    }

    if abstain:
        result["degradation"] = f"RCV ABSTAIN: 可得tenor={len(available_tenors)}<2"
        result["character"] = "ABSTAIN"
        return result

    if "DGS30" not in available_tenors:
        result["degradation"] = "RCV 降级:无长端,S3 利率前兆盲"

    # ── Helper: rolling RV series for a tenor ──
    def _rv_series(ts: list[dict]) -> tuple[list[dict], float | None]:
        """Compute rolling RV series. Returns (rv_list, latest_rv)."""
        if len(ts) < RCV_WINDOW + 1:
            return [], None
        # Daily bp changes
        daily_bp: list[tuple[str, float]] = []
        for i in range(1, len(ts)):
            cur_v = ts[i].get("value")
            prv_v = ts[i - 1].get("value")
            if cur_v is None or prv_v is None:
                continue
            daily_bp.append((ts[i]["date"], (cur_v - prv_v) * 100))
        # Rolling 20d std, annualized
        rv_vals: list[dict] = []
        for i in range(RCV_WINDOW - 1, len(daily_bp)):
            window_bps = [bp for _, bp in daily_bp[i - RCV_WINDOW + 1:i + 1]]
            mean = sum(window_bps) / RCV_WINDOW
            variance = sum((x - mean) ** 2 for x in window_bps) / (RCV_WINDOW - 1)
            std_annual = math.sqrt(variance * 252)
            rv_vals.append({"date": daily_bp[i][0], "value": round(std_annual, 1)})
        latest = rv_vals[-1]["value"] if rv_vals else None
        return rv_vals, latest

    # ── Compute RV per tenor ──
    rv_series_map: dict[str, list[dict]] = {}
    for tid in RCV_TENORS:
        rvs, rv_val = _rv_series(tenor_series.get(tid, []))
        rv_series_map[tid] = rvs
        label = RCV_TENOR_LABELS[tid]
        result[f"rv_{label}"] = rv_val

    # ── Z-scores ──
    def _z_score(rv_list: list[dict], latest: float | None) -> float | None:
        if latest is None or len(rv_list) < RCV_MIN_HISTORY:
            return None
        hist = [d["value"] for d in rv_list[-RCV_HISTORY:]]
        if len(hist) < RCV_MIN_HISTORY:
            return None
        mu = sum(hist) / len(hist)
        variance = sum((x - mu) ** 2 for x in hist) / (len(hist) - 1)
        sigma = math.sqrt(variance)
        if sigma < 0.01:
            return 0.0
        return round((latest - mu) / sigma, 2)

    for tid in RCV_TENORS:
        label = RCV_TENOR_LABELS[tid]
        rv_val = result[f"rv_{label}"]
        rvs = rv_series_map.get(tid, [])
        z_val = _z_score(rvs, rv_val)
        result[f"z_{label}"] = z_val

    # ── Front/Long ratio and z_ratio ──
    rv2 = result["rv_2y"]
    rv30 = result["rv_30y"]
    if rv2 is not None and rv30 is not None:
        result["ratio_2y_30y"] = round(rv2 / rv30, 3) if rv30 > 0 else None

    if rv2 is not None and rv30 is not None and rv30 > 0:
        # Compute ratio time series for z-score
        rvs2 = rv_series_map.get("DGS2", [])
        rvs30 = rv_series_map.get("DGS30", [])
        ratio_series: list[float] = []
        rv2_dict = {d["date"]: d["value"] for d in rvs2}
        rv30_dict = {d["date"]: d["value"] for d in rvs30}
        common = sorted(set(rv2_dict) & set(rv30_dict))
        for dt in common:
            if rv30_dict[dt] > 0:
                ratio_series.append(rv2_dict[dt] / rv30_dict[dt])
        if len(ratio_series) >= RCV_MIN_HISTORY:
            hist = ratio_series[-RCV_HISTORY:]
            mu_r = sum(hist) / len(hist)
            var_r = sum((x - mu_r) ** 2 for x in hist) / (len(hist) - 1)
            sigma_r = math.sqrt(var_r)
            if sigma_r > 0.001:
                result["z_ratio"] = round((result["ratio_2y_30y"] - mu_r) / sigma_r, 2)

    # ── Character determination: severity × tilt 二维 ──
    # 单轴 argmax 会在三段一起飙时误标 front-led（2y 险胜），实际是全曲线 parallel 应力
    # severity = leader z 的强度（calm < elevated < acute）
    # tilt     = z_ratio 的方向（front / neutral / long）
    z_map = {}
    for tid in RCV_TENORS:
        label = RCV_TENOR_LABELS[tid]
        z = result[f"z_{label}"]
        if z is not None:
            z_map[tid] = z

    if not z_map:
        result["character"] = "N/A"
        return result

    max_tid = max(z_map, key=z_map.get)
    max_z = z_map[max_tid]
    zr = result.get("z_ratio")

    # ── Severity ──
    if max_z < RCV_Z_ELEVATED:
        result["severity"] = "calm"
        result["leader"] = "balanced"
        result["character"] = "balanced/calm"
        result["tilt"] = "N/A"
        return result

    if max_z >= RCV_Z_ACUTE:
        result["severity"] = "acute"
    else:
        result["severity"] = "elevated"

    # ── Tilt (via z_ratio, independent axis) ──
    if zr is None:
        result["tilt"] = "N/A"
    elif zr > RCV_TILT_NEUTRAL:
        result["tilt"] = "front"
    elif zr < -RCV_TILT_NEUTRAL:
        result["tilt"] = "long"
    else:
        result["tilt"] = "neutral"

    # ── Leader tenor (which curve segment dominates the stress) ──
    if max_tid == "DGS2":
        result["leader"] = "2y"
    elif max_tid == "DGS10":
        result["leader"] = "10y"
    elif max_tid == "DGS30":
        result["leader"] = "30y"

    # ── Character composite ──
    sev = result["severity"]
    tl  = result["tilt"]

    if tl in ("N/A", "neutral"):
        result["character"] = f"{sev}-broad"
    elif tl == "front":
        result["character"] = f"{sev}-front-tilt"
    elif tl == "long":
        result["character"] = f"{sev}-long-tilt"
        result["long_led"] = True
    else:
        result["character"] = f"{sev}-{tl}"

    return result


def compute_vts_rcv_interlock(vts: dict, rcv: dict) -> dict:
    """§0.8+§0.9 跨资产 vol 探针互锁 — 迷你 CASC。

    VTS (股票 vol 探针) + RCV (利率 vol 探针) 分别观测前端/远端，
    两者一致时形成跨资产确认/否定。

    States:
      agree-front     — VTS前端急性 + RCV front-led → 近端事件风险、非系统性
      agree-systemic  — VTS倒挂/急性 + RCV ∈ {long-led(任意档), acute-broad} → 真要升档,§0.7 Role B 触发
      divergent       — 单资产技术性（一头急、一头平）→ CASC假阳性守卫
      calm            — 两端都平静

    Returns dict with: state, state_label, vts_hot, rcv_hot, front_confirmed, systemic_confirmed
    """
    # ── VTS 端判定 ──
    vts_structure = vts.get("structure", "N/A")
    vts_front_structure = vts.get("front_structure", "N/A")
    vts_inverted = vts_structure in ("倒挂", "倒挂·急性")
    vts_front_hot = vts_front_structure in ("前端紧张", "前端急性")

    # ── RCV 端判定 ──
    rcv_abstain = rcv.get("abstain", True)
    rcv_char = rcv.get("character", "N/A")
    rcv_severity = rcv.get("severity", "N/A")
    rcv_tilt = rcv.get("tilt", "N/A")
    rcv_front_led = rcv_severity in ("elevated", "acute") and rcv_tilt == "front"
    # 系统性味的利率状态:
    #   long-led(任意档): 30y领头的反转 = 长端在裂 → 永远算 systemic
    #   acute-broad: 全曲线急飙 = 利率侧广义应力 → 只有 acute 档才算
    rcv_long_led = rcv.get("long_led", False) and rcv_severity in ("elevated", "acute")
    rcv_acute_broad = rcv_char == "acute-broad"
    rcv_systemic = rcv_long_led or rcv_acute_broad
    rcv_hot = rcv_severity in ("elevated", "acute")

    # ── Default: one or both probes missing ──
    vts_missing = vts_structure == "N/A"
    if rcv_abstain and vts_missing:
        return {
            "state": "N/A", "state_label": "双探针均无数据·无法互锁",
            "vts_hot": False,
            "rcv_hot": False,
            "front_confirmed": False, "systemic_confirmed": False,
        }
    if vts_missing:
        rcv_desc = f"RCV={rcv_severity}" if rcv_severity != "N/A" else "RCV无数据"
        return {
            "state": "vts_missing", "state_label": f"VTS缺数据·{rcv_desc}·单探针无法确认双探针共振",
            "vts_hot": False,
            "rcv_hot": rcv_hot,
            "front_confirmed": False, "systemic_confirmed": False,
        }
    if rcv_abstain:
        return {
            "state": "N/A", "state_label": "RCV无数据",
            "vts_hot": vts_inverted or vts_front_hot,
            "rcv_hot": False,
            "front_confirmed": False, "systemic_confirmed": False,
        }

    # ── Interlock logic ──
    vts_hot = vts_inverted or vts_front_hot

    if vts_front_hot and rcv_front_led:
        return {
            "state": "agree-front", "state_label": "双探针前端一致·近端事件风险·非系统性",
            "vts_hot": True, "rcv_hot": True,
            "front_confirmed": True, "systemic_confirmed": False,
        }
    elif vts_inverted and rcv_systemic:
        return {
            "state": "agree-systemic", "state_label": "双探针长端一致·系统性·§0.7 Role B 触发",
            "vts_hot": True, "rcv_hot": True,
            "front_confirmed": False, "systemic_confirmed": True,
        }
    elif vts_hot and not rcv_hot:
        return {
            "state": "divergent", "state_label": "VTS热·RCV平→股票单资产技术性",
            "vts_hot": True, "rcv_hot": False,
            "front_confirmed": False, "systemic_confirmed": False,
        }
    elif rcv_hot and not vts_hot:
        return {
            "state": "divergent", "state_label": "RCV热·VTS平→利率单资产技术性",
            "vts_hot": False, "rcv_hot": True,
            "front_confirmed": False, "systemic_confirmed": False,
        }
    elif vts_hot and rcv_hot:
        # Both hot but directions don't agree (e.g. VTS inverted + RCV front-led, or VTS front + RCV long)
        return {
            "state": "divergent", "state_label": "双端热·方向背离→各自独立、非同一事件",
            "vts_hot": True, "rcv_hot": True,
            "front_confirmed": False, "systemic_confirmed": False,
        }
    else:
        return {
            "state": "calm", "state_label": "探针平静",
            "vts_hot": False, "rcv_hot": False,
            "front_confirmed": False, "systemic_confirmed": False,
        }


# ---------------------------------------------------------------------------
# §0.7 CASC — 跨资产应力确认
# ---------------------------------------------------------------------------

CASC_VIX_THRESHOLDS = [
    ("平静", 0, 18),
    ("抬升", 18, 25),
    ("应力", 25, 35),
    ("恐慌", 35, float("inf")),
]
CASC_MOVE_THRESHOLDS = [
    ("平静", 0, 100),
    ("抬升", 100, 125),
    ("应力", 125, 145),
    ("失序", 145, float("inf")),
]
# ── §0.7 Proxy thresholds (realized vol < implied in calm due to vol risk premium) ──
# MOVE隐含波动含vol risk premium → 平静期系统高于实现波动。
# 代理若套MOVE原生阈值会钝化（更晚报"失序"），对"宁灵敏"的门是错方向。
# 下移~15bp对齐实现波动量级；backtest三段(2024-08/2023-03/2022)会精校准。
CASC_MOVE_PROXY_THRESHOLDS = [
    ("平静", 0, 85),
    ("抬升", 85, 110),
    ("应力", 110, 130),
    ("失序", 130, float("inf")),
]
CASC_VIX_MUTATION       = 5.0      # 5dΔ ≥ +5pt
CASC_MOVE_MUTATION       = 20.0    # 5dΔ ≥ +20  (MOVE implied)
CASC_MOVE_PROXY_MUTATION = 15.0    # 5dΔ ≥ +15  (realized, lower base → lower Δ threshold)
CASC_HY_CONFIRM          = 30.0    # HY OAS 20dΔ ≥ +30bp
CASC_FX_MUTATION         = 2.5     # FXY 5d ≥ +2.5%


def _classify_casc_state(value: float | None, thresholds: list[tuple]) -> str:
    """Classify a value into a state label using ordered thresholds."""
    if value is None:
        return "N/A"
    for label, lo, hi in thresholds:
        if lo <= value < hi:
            return label
    return thresholds[-1][0]


def compute_casc(data: dict, v35: dict, abcd: dict) -> dict:
    """§0.7 Cross-Asset Stress Confirmation layer.
    
    Evaluates four legs (VIX/MOVE/HY OAS Δ/FX) and gates reflexive signals
    that lack cross-asset confirmation. Returns leg states, downgrade list,
    and C-end ordered/disorderly label.
    """
    # ── Raw data ──
    vix_s  = _vix_data(data)        # Yahoo ^VIX preferred (same-day alignment)
    move_s = data.get(MOVE_ID, [])
    fxy_s  = data.get(FXY_ID, [])

    vix_val  = last_value(vix_s)
    move_val = last_value(move_s)
    fxy_val  = last_value(fxy_s)

    # ── §0.8 VTS: compute before CASC legs ──
    vts = compute_vts(data)
    vts_inverted = vts.get("ratio_vix_vix3m") is not None and vts["ratio_vix_vix3m"] >= VTS_INVERTED
    rcv = compute_rcv(data)    # §0.9: rate curve vol character (severity × tilt)
    vts_rcv_lock = compute_vts_rcv_interlock(vts, rcv)   # §0.8+0.9 跨资产探针互锁

    # ── VIX leg (§0.8 Use-1: 5dΔ OR VTS 倒挂 → confirmation) ──
    vix_5d = n_day_change(vix_s, 5)
    vix_5d = round(vix_5d, 1) if vix_5d is not None else None
    # §0.8 Use-1: 倒挂比纯 level 跳更高质量 → 5dΔ≥+5pt OR VIX/VIX3M≥1.00
    vix_mutated = (vix_5d is not None and vix_5d >= CASC_VIX_MUTATION) or vts_inverted
    vix_confirm_source = []
    if vix_5d is not None and vix_5d >= CASC_VIX_MUTATION:
        vix_confirm_source.append("5dΔ")
    if vts_inverted:
        vix_confirm_source.append("VTS倒挂")
    vix_confirm_label = "+".join(vix_confirm_source) if vix_confirm_source else None
    vix_state = _classify_casc_state(vix_val, CASC_VIX_THRESHOLDS)
    vix_available = vix_val is not None

    # ── MOVE leg (primary: MOVE index; fallback: DGS10 realized vol proxy) ──
    move_source   = "MOVE"
    move_s_used   = move_s
    move_5d = n_day_change(move_s, 5)
    move_5d = round(move_5d, 1) if move_5d is not None else None
    move_mutated = move_5d is not None and move_5d >= CASC_MOVE_MUTATION
    move_state = _classify_casc_state(move_val, CASC_MOVE_THRESHOLDS)
    move_available = move_val is not None

    # MOVE-proxy fallback — if MOVE unavailable, try DGS2+DGS10 realized vol blend
    if not move_available:
        proxy_s = data.get("MOVE_PROXY", [])
        proxy_val = last_value(proxy_s)
        if proxy_val is not None:
            move_source    = "MOVE-proxy·realized"
            move_s_used    = proxy_s
            move_val       = proxy_val
            move_5d        = n_day_change(proxy_s, 5)
            move_5d        = round(move_5d, 1) if move_5d is not None else None
            # §0.7 Proxy uses own (lower) thresholds — implied > realized in calm
            move_mutated   = move_5d is not None and move_5d >= CASC_MOVE_PROXY_MUTATION
            move_state     = _classify_casc_state(move_val, CASC_MOVE_PROXY_THRESHOLDS)
            move_available = True

    # ── HY OAS leg (credit confirmation) ──
    hy_20d_delta = v35.get("hy_oas_20d_delta_bp", 0) or 0
    hy_confirmed = hy_20d_delta >= CASC_HY_CONFIRM
    hy_available = v35.get("hy_oas_pct", 0) is not None and v35.get("hy_oas_pct", 0) > 0

    # ── FX leg (primary: FXY; fallback: USDJPY) ──
    fx_source    = "FXY"
    fx_val_used  = fxy_val
    fxy_5d       = v35.get("fxy_5d_ret_pct")
    fx_mutated   = fxy_5d is not None and fxy_5d >= CASC_FX_MUTATION
    fx_available = fxy_val is not None

    # USDJPY fallback — if FXY stale/unavailable, try USDJPY=X
    usdjpy_s = data.get(USDJPY_ID, [])
    usdjpy_val = last_value(usdjpy_s)
    if not fx_available and usdjpy_val is not None:
        fx_source    = "USDJPY"
        fx_val_used  = usdjpy_val
        usdjpy_5d    = n_day_ret_pct(usdjpy_s, 5)
        # USDJPY direction is inverse: USDJPY↓ = yen strengthening = risk-off FX
        fx_mutated   = usdjpy_5d is not None and usdjpy_5d <= -CASC_FX_MUTATION
        fx_available = True
        fxy_5d       = usdjpy_5d  # reuse slot for display
    elif not fx_available:
        # Neither FXY nor USDJPY available
        fx_val_used = None

    # ── Per-leg mutation/confirmation status ──
    leg_status = {
        "VIX":        {"available": vix_available, "mutated": vix_mutated},
        "MOVE":       {"available": move_available, "mutated": move_mutated},
        "HY OAS 20dΔ": {"available": hy_available, "mutated": hy_confirmed},
        "FX":         {"available": fx_available, "mutated": fx_mutated},
    }

    # ── Abstention threshold (§0.7 边界) ──
    # When <2 non-FX legs are available for confirmation, the gate ABSTAINS —
    # signal passes through intact, marked low-confidence. This prevents the
    # "missing legs → C=0 → mechanical false downgrade" masking bug.
    CASC_MIN_CONFIRMATION_LEGS = 2

    def _non_source_available(source: str) -> int:
        return sum(1 for k, v in leg_status.items()
                   if k != source and v["available"])

    def _non_source_confirmed(source: str) -> int:
        return sum(1 for k, v in leg_status.items()
                   if k != source and v["available"] and v["mutated"])

    # ── Check reflexive signals for downgrades ──
    downgrades  = []
    abstentions = []

    d_light = abcd["D"]["light"]
    if d_light in ("🟠", "🔴"):
        non_fx_avail = _non_source_available("FX")
        non_fx       = _non_source_confirmed("FX")

        if not fx_available:
            # FX leg itself unavailable — no reflexive FX signal to confirm;
            # D端 🟠 driven by other sub-signals (CNH-CNY etc.), gate abstains
            abstentions.append({
                "signal": f"D端 (FX源N/A)",
                "light":  d_light,
                "reason": ("CASC ABSTAIN·FX腿无数据(FXY/USDJPY皆缺失)"
                           "·信号非FX驱动·原样放行·低置信"),
            })
        elif non_fx_avail < CASC_MIN_CONFIRMATION_LEGS:
            # ABSTAIN — not enough legs; pass signal through, mark low confidence
            abstentions.append({
                "signal": f"D端 {fx_source} 5d",
                "light":  d_light,
                "reason": (f"CASC ABSTAIN·确认腿不足({non_fx_avail}/{CASC_MIN_CONFIRMATION_LEGS})"
                           f"·信号原样放行·低置信"),
            })
        elif non_fx == 0:
            downgrades.append({
                "signal": f"D端 {fx_source} 5d",
                "light":  d_light,
                "reason": (f"未获跨资产确认(C-over-FX=0/{non_fx_avail})"
                           f"·疑似单资产技术性/假阳性 → 不计入跨域信号"),
            })

    # ── JPY intervention guard ──
    # FX mutation AND {VIX, MOVE, HY OAS} all NOT confirmed → suspect intervention
    # (requires all 3 non-FX legs to be available; missing legs → skip guard)
    jp_intervention = False
    if (fx_mutated and vix_available and move_available and hy_available
            and not vix_mutated and not move_mutated and not hy_confirmed):
        jp_intervention = True
        # If D wasn't already downgraded above, add a specific intervention downgrade
        if not any("D端" in d["signal"] for d in downgrades):
            downgrades.append({
                "signal": f"D端 {fx_source} 5d(疑似干预)",
                "light":  d_light,
                "reason": "日元干预假阳性 → D端维持上一档,不喂regime",
            })

    # ── Total confirmed (for display) ──
    total_confirmed = sum(1 for v in leg_status.values() if v["available"] and v["mutated"])

    # ── Ordered/Disorderly for C-end (phase-1: cosmetic only, not wired to position) ──
    c_light = abcd["C"]["light"]
    c_ordered = True
    c_label = ""
    proxy_note = " [MOVE-proxy]" if move_source != "MOVE" else ""
    if c_light in ("🟠", "🔴") and move_available:
        if move_state in ("平静",) and not move_mutated:
            c_ordered = True
            c_label = "有序重定价·估值压缩" + proxy_note
        elif move_state in ("应力", "失序") or move_mutated:
            c_ordered = False
            c_label = "失序·利率管道应力 [phase-1打标·未接升档]" + proxy_note
        else:
            c_label = "C端压力·MOVE居中" + proxy_note
    elif c_light in ("🟠", "🔴") and not move_available:
        c_label = "C端压力·MOVE缺失"

    # §0.9 Role B: RCV long-led → 标失序候选（只标，不单独驱动升档）
    if rcv.get("long_led") and c_label:
        c_label += " · RCV:长端失序候选"

    # §0.8+0.9 跨资产探针互锁摘要 → CASC mini 确认
    lock_state = vts_rcv_lock.get("state", "N/A")
    if lock_state == "agree-systemic" and c_label:
        c_label += " · 双探针:agree-systemic"
    elif lock_state == "agree-front":
        pass  # 这个状态本身就是"非系统性"确认，不追加标签以免混淆
    elif lock_state == "divergent" and c_label:
        c_label += " · 双探针:divergent"

    return {
        "legs": {
            "VIX":        {"value": round(vix_val, 1) if vix_val else None, "state": vix_state,
                           "delta_5d": vix_5d, "mutated": vix_mutated,
                           "confirm_source": vix_confirm_label,
                           "vts_structure": vts.get("structure", "N/A"),
                           "vts_ratio": vts.get("ratio_vix_vix3m")},
        "MOVE":       {"value": round(move_val, 1) if move_val else None, "state": move_state,
                       "delta_5d": move_5d, "mutated": move_mutated, "source": move_source},
            "HY OAS 20dΔ": {"delta_bp": round(hy_20d_delta, 1), "confirmed": hy_confirmed},
            "FX":         {"value": round(fx_val_used, 1) if fx_val_used else None,
                           "mutated": fx_mutated, "source": fx_source,
                           "delta_5d": round(fxy_5d, 1) if fxy_5d is not None else None},
        },
        "confirmation_count": total_confirmed,
        "legs_available": sum(1 for v in leg_status.values() if v["available"]),
        "jp_intervention_suspect": jp_intervention,
        "downgrades": downgrades,
        "abstentions": abstentions,
        "c_ordered": c_ordered,
        "c_label": c_label,
        "vts": vts,
        "rcv": rcv,
        "vts_rcv_lock": vts_rcv_lock,
    }


def apply_casc_gate(abcd: dict, casc: dict) -> dict:
    """Apply CASC confirmation gate: strip unconfirmed reflexive signals 
    from cross-domain counting. Does NOT change ABCD light colors.

    Only downgrades strip D from cross-domain count; abstentions pass through
    intact (marked low-confidence but still counted)."""
    downgrades  = casc.get("downgrades", [])
    abstentions = casc.get("abstentions", [])

    # If neither downgrades nor abstentions, nothing to do
    if not downgrades and not abstentions:
        return abcd

    # Copy
    modified = dict(abcd)

    # Check if D was downgraded (abstentions do NOT strip D)
    d_downgraded = any("D端" in d["signal"] for d in downgrades)
    a_light = modified["A"]["light"]
    b_light = modified["B"]["light"]
    c_light = modified["C"]["light"]
    # Abstain = signal passes through intact; downgrade = strip to 🟢
    d_effective = "🟢" if d_downgraded else modified["D"]["light"]

    # Recompute cross-domain / red counts
    cross_count = 0
    red_count = 0
    for light in [a_light, b_light, c_light, d_effective]:
        if light == "🔴":
            cross_count += 1
            red_count += 1
        elif light == "🟠":
            cross_count += 1

    modified["cross_domain_count"] = cross_count
    modified["red_domain_count"] = red_count
    modified["has_red"] = red_count > 0
    modified["_casc_downgraded"] = d_downgraded
    modified["_casc_downgrades"] = downgrades
    modified["_casc_abstentions"] = abstentions

    return modified


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
        trend = trend_arrow(effr_s, 20) if effr_s else "?"
        action = f"DUR5 {dur5_effr}/5 {'✅' if dur5_effr >= 5 else ''}" if effr_iorb_bp >= -3 else "仅观察"
        rows.append({"priority": "P1", "indicator": "EFFR-IORB 🟠", "value": f"{effr_iorb_bp}bp",
                     "trigger": "−3bp🟠 / 0bp🔴", "distance": status, "dur": f"{dur5_effr}/5",
                     "trend": trend, "action": action})

    # P1: HY OAS complacency
    if hy_oas_bp is not None:
        dist_to_300 = round(300 - hy_oas_bp, 0)
        status = f"距⚠️上沿{dist_to_300:.0f}bp" if hy_oas_bp < 300 else "已脱离自满区"
        trend = trend_arrow(hy_s, 20) if hy_s else "?"
        action = "突破→正常化" if hy_oas_bp >= 300 else "仅观察"
        rows.append({"priority": "P1", "indicator": "HY OAS 自满", "value": f"{hy_oas_bp:.0f}bp",
                     "trigger": "300bp(⚠️上沿)", "distance": status, "dur": "—",
                     "trend": trend, "action": action})

    # P2: Mortgage (with staleness annotation when data > 2d old)
    if mortgage is not None:
        dist_to_650 = round((mortgage - 6.50) * 100, 0) if mortgage >= 6.50 else round((6.50 - mortgage) * 100, 0)
        status = f"已触及+{dist_to_650}bp" if mortgage >= 6.50 else f"距触发{dist_to_650}bp"
        trend = trend_arrow(mtg_s, 20) if mtg_s else "?"
        mtg_cond = abcd["B"]["details"].get("Mortgage", {}).get("cond_met", False)
        action = "条件满足✅" if mtg_cond else "条件不满足(HY<455bp)"
        # Stale annotation: if data > 2d old, append as-of date + momentum band
        mtg_ind = "Mortgage 30Y (PMMS)"
        mtg_ld = last_date(mtg_s)
        if mtg_ld:
            mtg_dt = date.fromisoformat(mtg_ld) if isinstance(mtg_ld, str) else mtg_ld
            mtg_age = (date.today() - mtg_dt).days
            if mtg_age >= 3:
                # Momentum-extrapolated band
                mtg_20d_d = n_day_change(mtg_s, 20)
                mtg_20d_d = round(mtg_20d_d * 100, 0) if mtg_20d_d is not None else None
                band = f"+{mtg_20d_d:.0f}bp/20d" if mtg_20d_d else ""
                mtg_ind = f"Mortgage 30Y (PMMS) ({mtg_ld[-5:]}, {mtg_age}d stale{',' + band if band else ''})"
        rows.append({"priority": "P2", "indicator": mtg_ind, "value": f"{mortgage:.2f}%",
                     "trigger": "6.50%", "distance": status, "dur": "需2周",
                     "trend": trend, "action": action})

    # P2: 5Y5Y
    if t5y5y is not None:
        dist_to_245 = round((2.45 - t5y5y) * 100, 0) if t5y5y < 2.45 else round((t5y5y - 2.45) * 100, 0)
        status = f"已越🟠线+{dist_to_245}bp" if t5y5y >= 2.45 else f"距🟠{dist_to_245}bp"
        trend = trend_arrow(t5y5y_s, 20) if t5y5y_s else "?"
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


def compute_position(abcd: dict, v35: dict, *, casc: dict | None = None) -> dict:
    """Full S1-S5 position computation (v3.5).

    §0.7 关键不变量：S1 读取的 abcd['cross_domain_count'] 是 apply_casc_gate()
    过滤后的值（门后），非 compute_abcd_signals() 的原始值（门前）。
    如果 D 端被 CASC downgrade，D 在此处已被计为 🟢。
    """
    # §0.7 不变量：cross_count 已过 CASC 闸（apply_casc_gate 在 main() 管道中先于本函数执行）
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
    delta_h = pos["Hedge"] - 25
    delta_c = pos["Cash"] - 20
    if any(d != 0 for d in (delta_p, delta_h, delta_c)):
        vec_parts = []
        if delta_p != 0: vec_parts.append(f"P{delta_p:+d}")
        if delta_h != 0: vec_parts.append(f"H{delta_h:+d}")
        if delta_c != 0: vec_parts.append(f"C{delta_c:+d}")
        s1_note += f"（{', '.join(vec_parts)}）"

    steps.append({"step": "起点", "source": f"{prev_regime}基准",
                  "primary": 55, "hedge": 25, "cash": 20,
                  "note": "§0.6 第二层"})

    # --- S0 CASC Gate (§0.7) ---
    casc_downgrades  = casc.get("downgrades", [])  if casc else []
    casc_abstentions = casc.get("abstentions", []) if casc else []
    casc_items = casc_downgrades + casc_abstentions
    if casc_items:
        for ci in casc_items:
            steps.append({"step": "S0 CASC守卫", "source": f"{ci['signal']}({ci['light']})",
                          "primary": 55, "hedge": 25, "cash": 20,
                          "note": f"§0.7：{ci['reason']}"})

    steps.append({"step": "S1 Regime", "source": f"跨域信号={cross_count}",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": s1_note})

    # --- S2 Divergence (第七层：A-B / C-B 背离) ---
    # 规则：A-B Bearish 🔴 触发时 → Primary −5pp 进 Hedge，并取代第三层 A 边际。
    # 理由：A-B 背离的 "A 腿" 就是 A🟠，同源压力只扣一次（"数域不数信号"）；
    # 背离相比纯 A 边际的增量价值是路由——进 Hedge（凸性/对冲信用觉醒），不是 Cash。
    ab_bearish = a_light in ("🟠", "🔴") and b_light in ("⚠️", "🟢", "N/A")
    cb_bearish = c_light in ("🟠", "🔴") and b_light in ("⚠️", "🟢", "N/A")

    if ab_bearish:
        old_p = pos["Primary"]
        pos["Primary"] = max(pos["Primary"] - 5, 5)
        pos["Hedge"]   = pos["Hedge"] + 5
        steps.append({"step": "S2 背离", "source": "A-B Bearish 🔴",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": f"§0.6 第七层(取代第三层)：A-B背离 −5pp Primary → +5pp Hedge (Primary {old_p}→{pos['Primary']})"})
    elif cb_bearish:
        steps.append({"step": "S2 背离", "source": "C-B Bearish 🟠",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": "§0.6 第七层：仅标注'脆弱均衡'，不触发仓位调整"})

    pos["ab_bearish"] = ab_bearish
    pos["cb_bearish"] = cb_bearish

    # --- S3 Margin (第三层：A🟠 DUR5 边际) ---
    # 去重规则：若 A-B Bearish 已触发（ab_bearish=True），S3 被第七层取代，不独立再扣。
    # 原因：两层同源 A🟠；背离比纯边际更富信息（A 紧+B 自满 vs 仅 A 紧），
    # 且路由不同（Hedge vs Cash），不应叠加扣为 Primary−10pp。
    if a_light in ("🟠",) and dur5_effr >= 5 and not ab_bearish:
        old_p = pos["Primary"]
        pos["Primary"] = max(pos["Primary"] - 5, 5)
        pos["Cash"]    = pos["Cash"] + 5
        steps.append({"step": "S3 边际(非背离)", "source": "A🟠 DUR5确认",
                      "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                      "note": f"§0.6 第三层：A端🟠 −5pp Primary → +5pp Cash (无A-B背离)"})

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

    # --- S_VTS 再入场门 (§0.8 Use-2) ---
    # VTS 正常化 ≠ 自动降档；需 VTS 候选 AND 宏观同向缓。
    # 条件: (1) VTS 再入场门=候选(≥3天contango且曾倒挂)
    #       (2) 宏观同向: cross_domain ≤ 2 且无🔴域
    # 动作: +5pp Primary from Cash (轻仓再入场, 非全 regime shift)
    # 守卫: VTS ABSTAIN → 暂停；仍在倒挂 → 门不开
    vts_pos = casc.get("vts", {}) if casc else {}
    vts_gate = vts_pos.get("re_entry_gate", "未启用") if vts_pos else "未启用"
    vts_norm_days = vts_pos.get("normalization_days", 0)

    s_vts_note = f"§0.8 VTS再入场门={vts_gate}"
    if vts_gate == "候选":
        # 宏观同向检查
        macro_easing = cross_count <= 2 and not has_red
        if macro_easing:
            s_vts_note += f" · 宏观同向(cross={cross_count}, no🔴) → 降一档"
            old_prim = pos["Primary"]
            pos["Primary"] = min(pos["Primary"] + 5, 75)
            pos["Cash"]    = max(pos["Cash"] - 5, 0)
            s_vts_note += f" (Primary {old_prim}→{pos['Primary']}%, Cash −5pp)"
        else:
            s_vts_note += f" · 宏观未同向(cross={cross_count}, has_red={has_red}) → 未放行"
    elif vts_gate == "ABSTAIN":
        s_vts_note += " · 缺VIX3M数据 → 暂停,不在缺数据时盲目risk-on"
    elif "倒挂" in vts_gate:
        s_vts_note += " · 仍在倒挂 → 门不开"
    else:
        s_vts_note += f" · 正常化(≤{VTS_NORM_TARGET})={vts_norm_days}d/{VTS_NORM_DAYS}d, 曾倒挂={vts_pos.get('was_inverted', False)}"

    steps.append({"step": "S_VTS 再入场门", "source": f"VTS §0.8",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": s_vts_note})

    # --- S_RCV 利率探针 + 跨资产互锁 (§0.9 + §0.8+0.9 interlock) ---
    # RCV long-led = MOVE 单值看不出的水面下信号。
    # VTS+RCV interlock = 跨资产 mini CASC: agree-front/agree-systemic/divergent
    # 只标、不单独驱动仓位；agree-systemic 时标注为 §0.7 Role B 真正触发点
    rcv_pos = casc.get("rcv", {}) if casc else {}
    rcv_long = rcv_pos.get("long_led", False) if rcv_pos else False
    rcv_char = rcv_pos.get("character", "N/A") if rcv_pos else "N/A"
    rcv_sev  = rcv_pos.get("severity", "N/A") if rcv_pos else "N/A"
    lock = casc.get("vts_rcv_lock", {}) if casc else {}
    lock_state = lock.get("state", "N/A")
    lock_label = lock.get("state_label", "")
    s_rcv_note = f"§0.9 RCV={rcv_char}"
    if rcv_long:
        s_rcv_note += " · long-led失序候选 — MOVE平静+long-led=水面下长端裂(只标)"
    elif lock_state == "agree-systemic":
        s_rcv_note += f" · 双探针agree-systemic — {lock_label}"
    elif lock_state == "agree-front":
        s_rcv_note += f" · 双探针agree-front → {lock_label}"
    elif lock_state == "divergent":
        s_rcv_note += f" · 双探针divergent → {lock_label}"
    elif lock_state == "calm":
        s_rcv_note += " · 双探针平静"
    elif rcv_char == "ABSTAIN":
        s_rcv_note += f" · {rcv_pos.get('degradation','')}"

    steps.append({"step": "S_RCV 利率探针", "source": "RCV §0.9",
                  "primary": pos["Primary"], "hedge": pos["Hedge"], "cash": pos["Cash"],
                  "note": s_rcv_note})

    # --- S5 Weekend Gap ---
    # Check if today is Friday (weekday() == 4)
    import datetime as _dt
    today_wd = _dt.date.today().weekday()
    is_friday = today_wd == 4
    gap_note = "非周末，不执行Gap buffer" if not is_friday else f"周五→执行Gap buffer（P-5/C+5）"
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

def _compute_b_dur(abcd: dict) -> str:
    """B domain DUR confirmation string for core diagnosis."""
    b_light = abcd["B"]["light"]
    if b_light in ("N/A", "⚠️", "🟢"):
        return "—"
    if b_light == "🔴":
        return "即时"
    details = abcd["B"]["details"]
    for ind_name in ["HY OAS", "IG OAS"]:
        ind = details.get(ind_name, {})
        if ind.get("light") == b_light and ind.get("dur_target", 0) > 0:
            c, t = ind.get("dur_count", 0), ind.get("dur_target", 1)
            mark = " ✅" if c >= t else ""
            return f"{c}/{t}{mark}"
    return "—"  # Mortgage conditional or untracked


def _compute_b_consume(abcd: dict, pos: dict) -> str:
    """B domain 仓位消费 status."""
    b_light = abcd["B"]["light"]
    if b_light == "⚠️":
        return "✅"  # ⚠️ feeds R2 regime
    if b_light in ("🟢", "N/A"):
        return "—"
    if b_light == "🔴":
        return "✅"  # instant
    # 🟡/🟠: check DUR
    details = abcd["B"]["details"]
    for ind_name in ["HY OAS", "IG OAS"]:
        ind = details.get(ind_name, {})
        if ind.get("light") == b_light and ind.get("dur_target", 0) > 0:
            return "✅" if ind.get("dur_count", 0) >= ind.get("dur_target", 1) else "⏳"
    return "—"  # from Mortgage conditional


def _compute_d_dur(abcd: dict) -> str:
    """D domain DUR confirmation string."""
    d_light = abcd["D"]["light"]
    if d_light in ("🟢", "🟡", "N/A"):
        return "—"
    if d_light in ("🟠", "🔴"):
        fxy = abcd["D"]["details"].get("FXY 5d", {})
        c, t = fxy.get("dur_count", 0), fxy.get("dur_target", 1)
        if t == 1:
            mark = " ✅" if c >= t else ""
            return f"{c}/1{mark}" if d_light == "🟠" else "即时"
        return "即时"
    return "—"


def _compute_d_consume(abcd: dict) -> str:
    """D domain 仓位消费 status."""
    d_light = abcd["D"]["light"]
    if d_light in ("🟢", "🟡", "N/A"):
        return "—"
    if d_light in ("🟠", "🔴"):
        fxy = abcd["D"]["details"].get("FXY 5d", {})
        c, t = fxy.get("dur_count", 0), fxy.get("dur_target", 1)
        return "✅" if c >= t else "⏳"
    return "—"


def format_abcd_front_matter(
    abcd: dict, pos: dict, *, casc: dict | None = None,
) -> str:
    """ABCD 四端框架前言 — 实时灯色+子指标驱动，不自相矛盾。

    一眼读法不只读聚合灯色——必须读子指标状态，防止
    「Mortgage 🟡 把聚合灯拉成 🟡、前言却抄了信用走阔的台词」。
    """
    a_light = abcd["A"]["light"]
    b_light = abcd["B"]["light"]
    c_light = abcd["C"]["light"]
    d_light = abcd["D"]["light"]

    b_details = abcd["B"]["details"]
    hy_light = b_details.get("HY OAS", {}).get("light", "N/A")
    ig_light = b_details.get("IG OAS", {}).get("light", "N/A")
    mtg_light = b_details.get("Mortgage", {}).get("light", "N/A")
    mtg_cond_ok = b_details.get("Mortgage", {}).get("cond_met", False)
    hy_val_bp = b_details.get("HY OAS", {}).get("value_bp")

    # §0.7 CASC annotation for D端 — show downgrade/abstain status in-situ
    d_casc_note = ""
    if casc:
        dg_list = casc.get("downgrades", [])
        ab_list = casc.get("abstentions", [])
        if any("D端" in d["signal"] for d in dg_list):
            d_casc_note = " ⚠️[CASC未确认·不计入跨域]"
        elif any("D端" in d["signal"] for d in ab_list):
            d_casc_note = " ⚠️[CASC ABSTAIN·低置信]"

    # ── 一眼读法 ──
    a_read = {
        "🟢": "资金管道宽松，缓冲垫充裕。",
        "🟡": "资金管道微收，边际不再宽松。",
        "🟠": "资金管道偏紧，微观流动性不再舒服。",
        "🔴": "资金管道紧，市场缓冲垫明显变薄。",
    }.get(a_light, "A端数据缺失。")

    # B端: 必须区分「信用利差真实走阔」 vs 「自满/收窄」
    _credit_widening = hy_light not in ("N/A", "⚠️", "🟢") or ig_light not in ("N/A", "⚠️", "🟢")
    _credit_complacent = (hy_light == "⚠️" and ig_light in ("⚠️", "🟢"))
    if hy_light == "N/A" and ig_light == "N/A":
        b_read = "B端数据缺失。"
    elif _credit_widening:
        b_read = {
            "🟡": "信用利差开始走阔，关注是否持续。",
            "🟠": "信用融资条件明显恶化，风险从估值层传到资产负债表层。",
            "🔴": "信用市场进入压力区间，系统性风险在重定价。",
        }.get(b_light, "信用利差有所抬升。")
    elif _credit_complacent:
        b_read = "信用利差仍在自满区、继续收窄，市场尚未对企业信用恶化定价。"
    elif mtg_light in ("🟡", "🟠") and not mtg_cond_ok:
        b_read = "信用利差仍在自满区、继续收窄，按揭利率偏高但条件未满足。"
    else:
        b_read = "信用融资条件健康，利差低位。"

    # C端 🔴 必须接线BEI: 区分"纯真实利率推升" vs "通胀+真实利率共振"
    c_details = abcd["C"]["details"]
    bei_light = c_details.get("10Y BEI", {}).get("light", "N/A")
    if c_light == "🔴":
        if bei_light in ("🟠", "🔴"):
            c_read = "长端贴现率/真实利率压力已很高，通胀预期同步抬升、逼近失锚。"
        else:
            c_read = "长端贴现率/真实利率压力已很高，通胀预期反而下行——纯真实利率故事。"
    else:
        c_read = {
            "🟢": "长端通胀预期/真实利率平稳，贴现率无压力。",
            "🟡": "长端利率定价有所抬升，开始施压久期。",
            "🟠": "长端贴现率/真实利率压力明显，先打久期、先打估值。",
        }.get(c_light, "C端数据缺失。")
    d_read = {
        "🟢": "外汇与跨境风险扩散暂未启动。",
        "🟡": "外部汇率波动抬升，需要关注。",
        "🟠": "日元/外汇压力开始扩散，carry unwind 风险上升。",
        "🔴": "海外冲击正在反向传回全球风险资产。",
    }.get(d_light, "D端数据缺失。")

    # ── 综合判定 ──
    has_c = c_light in ("🟠", "🔴")
    has_a = a_light in ("🟠", "🔴")
    # B端压力判定: 信用利差真实走阔才算 (不含Mortgage驱动的假🟡)
    has_b_credit = _credit_widening and hy_val_bp is not None and hy_val_bp >= 480
    has_b_weak   = b_light in ("🟡", "🟠", "🔴") and not _credit_complacent
    has_d = d_light in ("🟠", "🔴")

    if has_c and has_a and has_b_credit:
        summary = "A紧 + C红 + B扩 → 从估值压缩升级为信用融资压力+基本面风险，需警惕系统性。"
    elif has_c and has_a and _credit_complacent and not has_d:
        summary = "A紧 + C红 + B自满(未走阔) → 估值压缩，尚未进入信用主导。"
    elif has_c and has_a and not has_b_weak and not has_d:
        summary = (
            "当前出现 A紧 + C红、但 B未扩、D未动 → "
            "优先解读为贴现率冲击与结构性重估，而非全面信用收缩或全球外部冲击。"
        )
    elif has_c and not has_a and not has_b_weak:
        summary = "C红先至 → 先估值压缩、先内部轮动，尚未进入信用主导的系统性去风险。"
    elif has_b_credit and has_d:
        summary = "信用恶化 + 外部冲击扩散 → 局部问题可能变成全球联动。"
    elif has_c and has_a and not has_b_credit:
        summary = "贴现率压力 + 流动性边际收紧，但信用市场尚未恶化 → 先内部轮动，暂不触发系统性。"
    else:
        summary = f"A={a_light} B={b_light} C={c_light} D={d_light} — 四端信号待传导方向确认。"

    lines = []
    lines.append("## ABCD 四端框架 · 固定前言")
    lines.append("")
    lines.append("| 端 | 灯 | 一眼读法 |")
    lines.append("|----|------|---------|")
    lines.append(f"| A 美元资金管道 | {a_light} | {a_read} |")
    lines.append(f"| B 信用融资条件 | {b_light} | {b_read} |")
    lines.append(f"| C 长端利率定价 | {c_light} | {c_read} |")
    lines.append(f"| D 外汇风险扩散 | {d_light}{d_casc_note} | {d_read} |")
    lines.append("")
    lines.append(f"> **综合判定**：{summary}")
    lines.append("")
    lines.append("**传导顺序**：C先红（贴现率压估值）→ A再紧（流动性缓冲变薄）→ 若B不坏（内部轮动）→ 若B转坏+信用走阔（系统性）→ 若D再动（全球联动）。")
    lines.append("")
    return "\n".join(lines)


def format_paper_trade_md(
    abcd: dict, pos: dict, v35: dict,
    data_date: str, *,
    vintages: dict | None = None,
    casc: dict | None = None,
) -> str:
    """Auto-generate paper_trade log with computed position from §0.6."""
    import datetime as _dt
    start = _dt.date(2026, 5, 27)
    today = _dt.date.fromisoformat(data_date)
    # Count trading days from start (approximate: skip weekends)
    day_num = 1
    d = start
    while d < today:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            day_num += 1
    if today < start:
        day_num = 0

    primary = pos["Primary"]
    hedge   = pos["Hedge"]
    cash    = pos["Cash"]

    lines = []
    lines.append(f"# Paper Trade 日志 — {data_date}")
    lines.append("")
    vintage_str = data_source_vintage_str(vintages) if vintages else ""
    src_note = f" | 数据：{vintage_str}" if vintage_str else ""
    lines.append(f"> 框架: v3.5 | Day: {day_num}/30{src_note} | 仓位由 daily 信号机械推导 (§0.6)")
    lines.append("")

    # ABCD 四端前言（参考模板，不取代原有信号输出）
    lines.append(format_abcd_front_matter(abcd, pos, casc=casc))
    lines.append("")
    lines.append("## 今日信号")
    lines.append("")
    # §0.7 CASC trace — regime annotation when ABSTAIN props up the read
    regime_annot = ""
    if casc and casc.get("abstentions"):
        n_ab = len(casc["abstentions"])
        regime_annot = f" [含{n_ab}个CASC-ABSTAIN低置信]"
    lines.append(f"- Regime: {pos['label']}{regime_annot}")
    a_light = abcd["A"]["light"]
    b_light = abcd["B"]["light"]
    c_light = abcd["C"]["light"]
    d_light = abcd["D"]["light"]
    b_annot = f"+⚠️" if b_light == "⚠️" or abcd["B"]["details"].get("HY OAS", {}).get("light") == "⚠️" else ""
    # §0.7 CASC trace — show downgrade/abstain in ABC灯 line
    d_casc_annot = ""
    if casc:
        if any("D端" in d["signal"] for d in casc.get("downgrades", [])):
            d_casc_annot = "[CASC:未确认·不计入]"
        elif any("D端" in d["signal"] for d in casc.get("abstentions", [])):
            d_casc_annot = "[CASC:ABSTAIN]"
    lines.append(f"- ABC 灯: A={a_light} B={b_light}{b_annot} C={c_light} D={d_light} {d_casc_annot}".rstrip())
    # Active domains for signal description
    active = []
    for dk in ["A", "B", "C", "D"]:
        light = abcd[dk]["light"]
        if light in ("🟠", "🔴"):
            active.append(f"{dk}={light}")
    active_detail = " + ".join(active) if active else "—"
    active_str = " + ".join(active) if active else "无活跃信号"
    lines.append(f"- 跨域信号: {abcd['cross_domain_count']} ({active_detail})")

    hyg_5d = v35.get("hyg_5d_ret_pct")
    hyg_5d_str = f"{hyg_5d:+.1f}%" if hyg_5d is not None else "N/A"
    hyg_trig = "触发了" if v35.get("hyg_trigger") else "未触发"
    lines.append(f"- HYG 5d Δ: {hyg_5d_str}（{hyg_trig}）")
    lines.append(f"- 假设仓位: Primary={primary}% Hedge={hedge}% Cash={cash}%")
    vts_triggered = any(s['step'] == 'S_VTS 再入场门' and '降一档' in s.get('note', '') for s in pos['steps'])
    rcv_long_triggered = any(s['step'] == 'S_RCV 利率探针' and '长端失序候选' in s.get('note', '') for s in pos['steps'])
    lock = casc.get("vts_rcv_lock", {})
    lock_state = lock.get("state", "")
    lock_tag = {"agree-front": "→双探针:front", "agree-systemic": "→双探针:systemic⚠️", "divergent": "→双探针:divergent"}.get(lock_state, "")
    lines.append(f"- 推导链: {active_str} → {pos['regime_key']} 基准 → S1{'→S2 背离' if pos.get('ab_bearish') else ''}{'→S3 边际' if any(s['step']=='S3 边际' for s in pos['steps']) else ''}{'→VTS再入场' if vts_triggered else ''}{'→RCV探针' if rcv_long_triggered else ''}{lock_tag} → P={primary}% H={hedge}% C={cash}%")
    # CASC summary
    if casc:
        casc_avail = casc.get("legs_available", 0)
        casc_conf  = casc.get("confirmation_count", 0)
        c_label    = casc.get("c_label", "") or "C端无压力"
        jp_flag    = "触发" if casc.get("jp_intervention_suspect") else "未触发"
        lines.append(f"- CASC §0.7: 确认{casc_conf}/{casc_avail} · C端={c_label} · 干预={jp_flag}")
        # VTS summary
        vts_pt = casc.get("vts", {})
        if vts_pt and vts_pt.get("ratio_vix_vix3m") is not None:
            vts_gate_c = vts_pt.get('re_entry_gate', '未启用')
            vts_nd     = vts_pt.get('normalization_days', 0)
            vts_wi     = vts_pt.get('was_inverted', False)
            vts_extra  = ""
            if vts_gate_c not in ("候选", "ABSTAIN") and "倒挂" not in str(vts_gate_c):
                vts_extra = f" · 正常化(≤{VTS_NORM_TARGET})={vts_nd}d/{VTS_NORM_DAYS}d{' (曾倒挂)' if vts_wi else ''}"
            lines.append(f"- VTS §0.8: 期限结构={vts_pt.get('structure','N/A')} ({vts_pt['ratio_vix_vix3m']:.3f}) · 再入场={vts_gate_c}{vts_extra}")
        # RCV summary
        rcv_pt = casc.get("rcv", {})
        if rcv_pt and not rcv_pt.get("abstain", True):
            lines.append(f"- RCV §0.9: 形态={rcv_pt.get('character','N/A')} · severity={rcv_pt.get('severity','N/A')} · tilt={rcv_pt.get('tilt','N/A')}")
        elif rcv_pt and rcv_pt.get("abstain"):
            lines.append(f"- RCV §0.9: ABSTAIN — {rcv_pt.get('degradation','')}")
        # VTS+RCV interlock
        lock_pt = casc.get("vts_rcv_lock", {})
        if lock_pt and lock_pt.get("state", "N/A") != "N/A":
            lines.append(f"- 双探针互锁 §0.8+0.9: {lock_pt.get('state','N/A')} — {lock_pt.get('state_label','')}")
        for ab in casc.get("abstentions", []):
            lines.append(f"  - ABSTAIN: {ab['signal']} — {ab['reason']}")
        for dg in casc.get("downgrades", []):
            lines.append(f"  - 🚫 {dg['signal']}: {dg['reason']}")
    lines.append("")

    # 触发检查
    lines.append("## 触发检查")
    lines.append("")
    lines.append("| 信号 | 状态 | 备注 |")
    lines.append("|------|------|------|")
    hyg_s = f"!! 触发 !! {hyg_5d_str}" if v35.get("hyg_trigger") else f"未触发 | {hyg_5d_str}"
    lines.append(f"| HYG <-1.5% | {hyg_s} |")
    fxy_5d = v35.get("fxy_5d_ret_pct")
    fxy_s = f"!! 触发 !! {fxy_5d:+.1f}%" if v35.get("fxy_trigger") else f"未触发 | {fxy_5d:+.1f}%" if fxy_5d is not None else "未触发 | N/A"
    lines.append(f"| FXY >+2.5% | {fxy_s} |")
    dd_s = f"!! 触发 !! 20dΔ={v35.get('hy_oas_20d_delta_bp', 0):+.0f}bp" if v35.get("drawdown_warning") else f"未触发 | 20dΔ={v35.get('hy_oas_20d_delta_bp', 0):+.0f}bp"
    lines.append(f"| Drawdown Warning | {dd_s} |")
    spy_ok = not v35.get("spy_below_200ma", False) if v35.get("spy_below_200ma") is not None else True
    spy_s = "!! 触发 !!" if not spy_ok else "未触发"
    lines.append(f"| SPY < 200MA | {spy_s} | — |")
    lines.append("")

    # 仓位推导明细
    lines.append("## 仓位推导 (§0.6)")
    lines.append("")
    lines.append("| Step | 来源 | Primary | Hedge | Cash | 说明 |")
    lines.append("|------|------|---------|-------|------|------|")
    for step in pos["steps"]:
        lines.append(f"| {step['step']} | {step['source']} | {step['primary']}% | {step['hedge']}% | {step['cash']}% | {step['note']} |")
    lines.append(f"| **终点** | — | **{primary}%** | **{hedge}%** | **{cash}%** | {pos['label']} |")
    lines.append("")

    # 备注
    lines.append("## 备注")
    lines.append("")
    lines.append("- ")
    lines.append("")
    lines.append("---")
    lines.append(f"")
    lines.append(f"*Paper Trade Day {day_num}/30 | 仓位自动推导 (§0.6) | 协议: v3.5/paper_trade_协议.md*")

    return "\n".join(lines)


def format_text_report(
    curve: dict, hy: dict, v35: dict, fw: dict, liq: dict, abcd: dict, pos: dict,
    prox: list[dict], checklist: list[str],
    data_date: str,
    rate_path: dict | None = None,
    casc: dict | None = None,
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
    # §0.7 CASC trace — regime annotation when ABSTAIN props up the read
    regime_annot = ""
    if casc and casc.get("abstentions"):
        n_ab = len(casc["abstentions"])
        regime_annot = f" [含{n_ab}个CASC-ABSTAIN低置信]"
    lines.append(f"  Regime: {pos['label']}{regime_annot}  |  跨域信号: {abcd['cross_domain_count']}")
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
    lines.append(f"  Drawdown Warning: {dd_s}  (HY OAS={v35['hy_oas_pct']*100:.0f}bp, 20dΔ={v35['hy_oas_20d_delta_bp']:+.1f}bp)")
    ex_s = f"!! {len(v35['extreme_hit'])} ACTIVE !!" if v35["extreme_hit"] else "OK"
    lines.append(f"  Extreme Meltdown: {ex_s}  (VIX={v35['vix']}, SOFR-IORB={v35['sofr_iorb_bp']}bp)")

    # --- CASC (§0.7) ---
    if casc:
        lines.append("")
        lines.append("-" * 48)
        lines.append("  CASC §0.7 跨资产应力确认")
        lines.append("-" * 48)
        for leg_name in ["VIX", "MOVE", "HY OAS 20dΔ", "FX"]:
            leg = casc["legs"].get(leg_name, {})
            if leg_name == "VIX":
                val_s = f"{leg.get('value', 'N/A')}" if leg.get('value') is not None else "N/A"
                mut_s = "MUTATED" if leg.get("mutated") else "calm"
                vts_s = f" VTS={leg.get('vts_structure','N/A')}" if leg.get('vts_ratio') is not None else ""
                lines.append(f"  VIX:        {val_s:>6s} ({leg.get('state', 'N/A'):4s}) Δ5d={leg.get('delta_5d', 'N/A')} [{mut_s}]{vts_s}")
            elif leg_name == "MOVE":
                mv_src = leg.get("source", "MOVE")
                val_s = f"{leg.get('value', 'N/A')}" if leg.get('value') is not None else "N/A"
                mut_s = "MUTATED" if leg.get("mutated") else "calm"
                lines.append(f"  MOVE ({mv_src}): {val_s:>6s} ({leg.get('state', 'N/A'):4s}) Δ5d={leg.get('delta_5d', 'N/A')} [{mut_s}]")
            elif leg_name == "HY OAS 20dΔ":
                lines.append(f"  HY OAS 20dΔ: {leg.get('delta_bp', 'N/A'):+.1f}bp {'[CONFIRMED]' if leg.get('confirmed') else '[—]'}")
            else:
                fx_src = leg.get("source", "FXY")
                fx_thr = ">+2.5%" if fx_src == "FXY" else "<-2.5%"
                fx_d5  = leg.get('delta_5d')
                fxv_s = f"{fx_d5:+.1f}%" if fx_d5 is not None else "N/A"
                mut_s = "MUTATED" if leg.get("mutated") else "calm"
                lines.append(f"  FX ({fx_src} {fx_thr}): {fxv_s:>8s} [{mut_s}]")
        casc_avail = casc.get("legs_available", 0)
        casc_conf  = casc.get("confirmation_count", 0)
        c_label    = casc.get("c_label", "") or "C端无压力"
        jp_flag    = "触发" if casc.get("jp_intervention_suspect") else "未触发"
        lines.append(f"  [确认 {casc_conf}/{casc_avail} · C端={c_label} · 干预守卫={jp_flag}]")
        # VTS status
        vts = casc.get("vts", {})
        if vts:
            vts_r = vts.get("ratio_vix_vix3m")
            vts_rs = f"({vts_r:.3f})" if vts_r is not None else "(N/A)"
            lines.append(f"  [VTS §0.8: {vts.get('structure','N/A')}{vts_rs} · 再入场={vts.get('re_entry_gate','未启用')}]")
        # RCV status
        rcv = casc.get("rcv", {})
        if rcv and not rcv.get("abstain", True):
            rv2  = f"{rcv['rv_2y']:.1f}" if rcv.get('rv_2y') is not None else "N/A"
            rv10 = f"{rcv['rv_10y']:.1f}" if rcv.get('rv_10y') is not None else "N/A"
            rv30 = f"{rcv['rv_30y']:.1f}" if rcv.get('rv_30y') is not None else "N/A"
            lines.append(f"  [RCV §0.9: 2y={rv2}/10y={rv10}/30y={rv30} bp年化 · 形态={rcv.get('character','N/A')} · sev={rcv.get('severity','N/A')}]")
        elif rcv and rcv.get("abstain"):
            lines.append(f"  [RCV §0.9: ABSTAIN — {rcv.get('degradation','')}]")
        # VTS+RCV interlock
        lock_txt = casc.get("vts_rcv_lock", {})
        if lock_txt and lock_txt.get("state", "N/A") != "N/A":
            lines.append(f"  [双探针互锁 §0.8+0.9: {lock_txt.get('state','N/A')} — {lock_txt.get('state_label','')}]")
        # Abstentions (no downgrade, signal passes through)
        for ab in casc.get("abstentions", []):
            lines.append(f"  ⚠️ ABSTAIN: {ab['signal']} · {ab['reason']}")
        # Downgrades
        for dg in casc.get("downgrades", []):
            lines.append(f"  🚫 降级: {dg['signal']} → {dg['reason']}")

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
    if liq.get("reserves_t") is not None:
        lines.append(f"  Reserves:  ${liq['reserves_t']:.2f}T")

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

    # 观察项: 利率路径(代理) — 纯显示，不进 regime / 仓位
    if rate_path:
        lines.append("")
        lines.append(f"  {rate_path['display_str']}")

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


def _format_nowcast_section(nowcast: dict) -> list[str]:
    """Generate C_RealYield_Nowcast markdown section."""
    L = []

    # Degradation check
    if nowcast.get("data_status") == "missing_us10y":
        L.append("## C_RealYield_Nowcast 实际利率实时估算")
        L.append("")
        L.append("> ⚠️ **C_RealYield_Nowcast: missing_us10y** — 缺少 US10Y 数据（^TNX/DGS10 均不可用），Nowcast 不可用。")
        L.append("")
        return L
    if nowcast.get("data_status") == "missing_bei10":
        L.append("## C_RealYield_Nowcast 实际利率实时估算")
        L.append("")
        L.append("> ⚠️ **C_RealYield_Nowcast: missing_bei10** — 缺少 10Y BEI 数据（T10YIE 不可用），Nowcast 不可用。")
        L.append("")
        return L

    L.append("## C_RealYield_Nowcast 实际利率实时估算")
    L.append("")

    # Main table
    nc = nowcast
    ryn = nc.get("real_yield_nowcast")
    dfii = nc.get("dfii10_official")
    gap = nc.get("real_yield_gap")
    d1 = nc.get("nowcast_delta_1d")
    d5 = nc.get("nowcast_delta_5d")
    cooling = nc.get("cooling_counter", 0)
    cooling_target = nc.get("cooling_target", 3)
    data_status = nc.get("data_status", "ok")

    L.append("| 指标 | 值 |")
    L.append("|------|----|")
    L.append(f"| US10Y 最新 | {nc['us10y_latest']}% (来源: {nc.get('us10y_source','?')}, {nc.get('us10y_latest_date','?')[-5:]}) |")
    L.append(f"| 10Y BEI 最新 | {nc['bei10_latest']}% (来源: {nc.get('bei10_source','?')}, {nc.get('bei10_latest_date','?')[-5:]}) |")
    ryn_raw = nc.get("real_yield_nowcast_raw")
    if ryn is not None and ryn_raw is not None:
        ryn_str = f"{ryn:.2f}% (原始 {ryn_raw:.2f}%, 已校准)"
    elif ryn is not None:
        ryn_str = f"{ryn:.2f}%"
    else:
        ryn_str = "N/A"
    L.append(f"| **Real Yield Nowcast** | **{ryn_str}** |")
    dfii_str = f"{dfii:.2f}%" if dfii is not None else "N/A"
    L.append(f"| 官方 DFII10 | {dfii_str} ({nc.get('dfii10_date','?')[-5:] if nc.get('dfii10_date') else '?'}) |")
    if gap is not None:
        L.append(f"| Nowcast − Official | {gap:+.2f}pct ({gap*100:+.0f}bp) |")
    else:
        L.append(f"| Nowcast − Official | N/A |")
    # Basis calibration row
    basis_median = nc.get("basis_median")
    if basis_median is not None:
        bs = nc.get("basis_std") or 0.0
        basis_n = nc.get("basis_n_obs", 0)
        basis_d = nc.get("basis_last_date", "?")[-5:]
        stability = "stable" if (bs < 0.03) else "volatile"
        L.append(f"| 基差校准 | {basis_median*100:+.1f}bp (^TNX−T10YIE vs DFII10, {basis_n}d median, σ={bs*100:.1f}bp, {stability}) |")
    warming_1d = nc.get("nowcast_delta_1d_warming", False)
    warming_5d = nc.get("nowcast_delta_5d_warming", False)
    if d1 is not None:
        d1_str = f"{d1:+.2f}pct ({d1*100:+.0f}bp)"
        if warming_1d:
            d1_str += " · 首跑 warming(DFII10 proxy)"
    else:
        d1_str = "N/A (历史<1d)"
    L.append(f"| 1日变化 | {d1_str} |")
    if d5 is not None:
        d5_str = f"{d5:+.2f}pct ({d5*100:+.0f}bp)"
        if warming_5d:
            d5_str += " · warming(DFII10 proxy)"
    else:
        d5_str = "N/A (历史<5d)"
    L.append(f"| 5日变化 | {d5_str} |")
    L.append(f"| 绝对水平 | {nc.get('nowcast_level_light','N/A')} {nc.get('nowcast_level_label','N/A')} |")
    L.append(f"| 方向 | {nc.get('nowcast_direction_light','⚪')} {nc.get('nowcast_direction','N/A')} |")
    L.append(f"| Nowcast cooling | {cooling}/{cooling_target} |")

    # Data status
    status_labels = {
        "ok": "✅ stable",
        "bei_stale": "⚠️ BEI stale",
        "dfii_stale": "⚠️ DFII10 stale; using nowcast for directional interpretation only",
        "missing_us10y": "❌ missing US10Y",
        "missing_bei10": "❌ missing BEI",
    }
    L.append(f"| 数据状态 | {status_labels.get(data_status, data_status)} |")
    L.append("")

    # Interpretation paragraph
    interpretation = _build_nowcast_interpretation(nowcast)
    L.append(f"**解释**：{interpretation}")
    L.append("")

    # Degradation note
    if nc.get("degradation_reason"):
        L.append(f"> ⚠️ {nc['degradation_reason']}")
        L.append("")

    # Asset map
    asset_map = nc.get("asset_map", [])
    if asset_map:
        L.append("### 资产含义")
        L.append("")
        L.append("| 资产 | 当前解释 |")
        L.append("|------|----------|")
        for a in asset_map:
            L.append(f"| {a['asset']} | {a['note']} |")
        L.append("")

    return L


def _build_nowcast_interpretation(nowcast: dict) -> str:
    """Build one-sentence interpretation of nowcast vs official DFII10."""
    ryn = nowcast.get("real_yield_nowcast")
    dfii = nowcast.get("dfii10_official")
    direction = nowcast.get("nowcast_direction", "N/A")
    level = nowcast.get("nowcast_level_label", "N/A")
    divergence = nowcast.get("divergence_status", "N/A")

    if ryn is None:
        return "Nowcast 不可用。"

    parts = []
    # Check if direction data is meaningful (not default/warming)
    d_meaningful = nowcast.get("nowcast_delta_1d") is not None and not nowcast.get("nowcast_delta_1d_warming", False)

    if dfii is not None:
        parts.append(f"官方 DFII10 仍处于 {dfii:.2f}%。")

        if dfii >= 2.00 and d_meaningful and direction in ("明显回落", "小幅回落"):
            parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%，显示实际利率已边际回落。C端绝对压力仍在，但贴现率边际压力开始缓和。")
        elif dfii >= 2.00 and d_meaningful and direction in ("明显上行", "小幅上行"):
            parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%，同步指向实际利率继续上行，C端压力仍在强化。")
        elif dfii >= 2.00 and d_meaningful:
            # Direction is neutral (基本持平) → don't fabricate "改善" or "上行"
            parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%，方向基本持平。实际利率仍在高压区，等待方向明朗化。")
        elif dfii >= 2.00:
            # No meaningful direction data yet (首跑 warming)
            parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%，实际利率仍处高压区。方向数据尚在累积中（<5d历史），暂时无法判断边际方向。")
        else:
            parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%。C端{level}。")
    else:
        parts.append(f"Real Yield Nowcast 为 {ryn:.2f}%（{level}）。官方 DFII10 缺失，仅用 Nowcast 参考方向。")

    if divergence == "nowcast_diverges_from_official":
        parts.append("Nowcast 与官方值显著偏离，需关注后续确认。")

    # Append caveat if direction data is warming
    if not nowcast.get("nowcast_delta_1d") is None and nowcast.get("nowcast_delta_1d_warming"):
        if parts and "方向数据尚在累积" not in parts[-1]:
            parts.append("方向数据基于DFII10近似（Nowcast历史<5d），待实盘累积后切换为Nowcast自身方向。")

    return "".join(parts)


def format_markdown_report(
    curve: dict, hy: dict, v35: dict, fw: dict, liq: dict, abcd: dict, pos: dict,
    prox: list[dict], checklist: list[str],
    data_date: str, *,
    vintages: dict | None = None,
    stale_warnings: list[str] | None = None,
    rate_path: dict | None = None,
    casc: dict | None = None,
    nowcast: dict | None = None,
) -> str:
    """Markdown report in ABCD v3.5 诊断简报 format."""
    lines = []
    lines.append("# ABCD 诊断简报（日更版）")
    lines.append("")
    vintage_str = data_source_vintage_str(vintages) if vintages else ""
    src_line = f"数据：{vintage_str} | SOP：v3.5 | 两轨制：ABS/DUR=生效，ROLL=评估" if vintage_str else \
        f"数据：FRED + Yahoo Finance | SOP：v3.5 | 两轨制：ABS/DUR=生效，ROLL=评估"
    lines.append(f"> {src_line}")
    lines.append("")

    # ── Auxiliary degradation banner (from fetch_data.py manifest check) ──
    _aux_banner = _read_aux_banner()
    if _aux_banner:
        lines.append(f"> ⚠️ **辅助序列降级** — {_aux_banner}")
        lines.append("")

    # ====== ABCD 四端固定前言（参考模板，不取代原有信号输出）=======
    lines.append(format_abcd_front_matter(abcd, pos, casc=casc))
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
        "B": _compute_b_dur(abcd),
        "C": c_dur_str,
        "D": _compute_d_dur(abcd),
    }
    consume_map = {
        "A": "✅" if dur5_effr >= 5 else "❌",
        "B": _compute_b_consume(abcd, pos),
        "C": "✅" if dur5_dfii >= 5 else "❌",
        "D": _compute_d_consume(abcd),
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
    lines.append(f"| Drawdown Warning | {dd} | HY OAS={v35['hy_oas_pct']*100:.0f}bp, 20dΔ={v35['hy_oas_20d_delta_bp']:+.1f}bp |")
    hyg_s = f"!! {v35['hyg_5d_ret_pct']:+.1f}% !!" if v35["hyg_trigger"] else f"OK ({v35['hyg_5d_ret_pct']:+.1f}%)" if v35['hyg_5d_ret_pct'] is not None else "N/A"
    fxy_s = f"!! {v35['fxy_5d_ret_pct']:+.1f}% !!" if v35["fxy_trigger"] else f"OK ({v35['fxy_5d_ret_pct']:+.1f}%)" if v35['fxy_5d_ret_pct'] is not None else "N/A"
    spy_s = f"!! SPY={v35['spy_price']} < 200MA={v35['spy_200ma']} !!" if v35["spy_below_200ma"] else f"OK"
    lines.append(f"| HYG 5d <-1.5% | {hyg_s} | HYG={v35['hyg_price']} |")
    lines.append(f"| FXY 5d >+2.5% | {fxy_s} | FXY={v35['fxy_price']} |")
    lines.append(f"| SPY < 200MA | {spy_s} | — |")
    lines.append(f"| Extreme Meltdown | {ex} | VIX={v35['vix']}, SOFR-IORB={v35['sofr_iorb_bp']}bp |")
    lines.append("")

    # ====== §0.7 跨资产应力确认 CASC ======
    if casc:
        lines.append("## 跨资产应力确认 CASC (§0.7)")
        lines.append("")
        lines.append("| 腿 | 标的 | 当前值 | 5dΔ | 形态 | 突变? | 当前态 (Watch) |")
        lines.append("|----|------|--------|------|------|-------|----------------|")
        for leg_name in ["VIX", "MOVE", "HY OAS 20dΔ", "FX"]:
            leg = casc["legs"].get(leg_name, {})
            if leg_name == "VIX":
                leg_val = leg.get('value')
                val_str = f"{leg_val}" if leg_val is not None else "N/A"
                d5_str  = f"{leg.get('delta_5d', 'N/A'):+.1f}" if leg.get('delta_5d') is not None else "N/A"
                vts_str = leg.get("vts_structure", "N/A")
                # §0.8: VTS structure + ratio for richer display
                vts_ratio = leg.get("vts_ratio")
                if vts_ratio is not None:
                    vts_str = f"{vts_str} ({vts_ratio:.3f})"
                mut_str = "是" if leg.get("mutated") else "—"
                raw_state = leg.get("state", "N/A")
                # Annotate if state is elevated but mutation not confirmed:
                # CASC VIX 腿确认需要 5dΔ≥+5pt OR VTS倒挂
                mutated = leg.get("mutated", False)
                if not mutated and raw_state in ("抬升", "应力", "恐慌"):
                    missing = []
                    d5 = leg.get("delta_5d")
                    if d5 is None or d5 < CASC_VIX_MUTATION:
                        missing.append(f"Δ5d<{CASC_VIX_MUTATION}")
                    if not vts_ratio or vts_ratio < VTS_INVERTED:
                        missing.append("缺VTS倒挂")
                    st_str = f"{raw_state}·{'&'.join(missing)}" if missing else raw_state
                else:
                    st_str = raw_state
            elif leg_name == "MOVE":
                mv_src = leg.get("source", "MOVE")
                val_str = f"{leg.get('value', 'N/A')}" if leg.get('value') is not None else "N/A"
                d5_str  = f"{leg.get('delta_5d', 'N/A'):+.1f}" if leg.get('delta_5d') is not None else "N/A"
                vts_str = "—"
                mut_str = "是" if leg.get("mutated") else "—"
                st_str  = leg.get("state", "N/A")
            elif leg_name == "HY OAS 20dΔ":
                val_str = f"{leg.get('delta_bp', 'N/A'):+.1f}bp"
                d5_str  = "—"
                vts_str = "—"
                mut_str = "走阔✅" if leg.get("confirmed") else "—"
                st_str  = "—"
            else:  # FX
                fx_src   = leg.get("source", "FXY")
                fx_thr   = ">+2.5%" if fx_src == "FXY" else "<-2.5%"
                val_str  = f"{leg.get('value', 'N/A')}" if leg.get('value') is not None else "N/A"
                fx_d5    = leg.get('delta_5d')
                d5_str   = f"{fx_d5:+.1f}%" if fx_d5 is not None else "N/A"
                vts_str  = "—"
                mut_str  = "是" if leg.get("mutated") else "—"
                st_str   = f"{'抬升' if leg.get('mutated') else '平静'} (Watch {fx_thr})"
            lines.append(f"| {leg_name} | {'VIX' if leg_name == 'VIX' else mv_src if leg_name == 'MOVE' else 'HY OAS' if 'HY' in leg_name else fx_src} | {val_str} | {d5_str} | {vts_str} | {mut_str} | {st_str} |")
        lines.append("")

        # CASC summary line
        casc_avail = casc.get("legs_available", 0)
        casc_conf  = casc.get("confirmation_count", 0)
        c_label    = casc.get("c_label", "") or "C端无压力"
        jp_flag    = "触发" if casc.get("jp_intervention_suspect") else "未触发"
        abst_list  = casc.get("abstentions", [])
        lines.append(f"> [CASC 确认 {casc_conf}/{casc_avail} · C端={c_label} · 干预守卫={jp_flag}]")
        if abst_list:
            for ab in abst_list:
                lines.append(f"> ⚠️ ABSTAIN: {ab['signal']} — {ab['reason']}")
        # Explicit downgrade audit
        for dg in casc.get("downgrades", []):
            lines.append(f"> 🚫 降级: {dg['signal']} — {dg['reason']}")

        # ── §0.8 VTS status line ──
        vts = casc.get("vts", {})
        if vts:
            vts_struct    = vts.get("structure", "N/A")
            vts_ratio_val = vts.get("ratio_vix_vix3m")
            vts_ratio_str = f"{vts_ratio_val:.3f}" if vts_ratio_val is not None else "N/A"
            vts_front     = vts.get("front_structure", "N/A")
            vts_fr_ratio  = vts.get("ratio_vix9d_vix")
            vts_gate      = vts.get("re_entry_gate", "未启用")
            vts_norm_d    = vts.get("normalization_days", 0)
            vts_was_inv   = vts.get("was_inverted", False)
            norm_part     = f" · 正常化(≤{VTS_NORM_TARGET})={vts_norm_d}d/{VTS_NORM_DAYS}d{' (曾倒挂)' if vts_was_inv else ''}" if vts_gate not in ("候选", "ABSTAIN") and "倒挂" not in str(vts_gate) else ""
            lines.append(f"> [VTS §0.8: 期限结构={vts_struct}({vts_ratio_str}) · 前端={vts_front}({f'{vts_fr_ratio:.3f}' if vts_fr_ratio is not None else 'N/A'}) · 再入场门={vts_gate}{norm_part}]")
        # ── §0.9 RCV status line (利率探针, 并排 VTS 股票探针) ──
        rcv = casc.get("rcv", {})
        if rcv and not rcv.get("abstain", True):
            rv2  = f"{rcv['rv_2y']:.1f}" if rcv.get('rv_2y') is not None else "N/A"
            rv10 = f"{rcv['rv_10y']:.1f}" if rcv.get('rv_10y') is not None else "N/A"
            rv30 = f"{rcv['rv_30y']:.1f}" if rcv.get('rv_30y') is not None else "N/A"
            z2  = f"z={rcv['z_2y']:.1f}" if rcv.get('z_2y') is not None else ""
            z10 = f"z={rcv['z_10y']:.1f}" if rcv.get('z_10y') is not None else ""
            z30 = f"z={rcv['z_30y']:.1f}" if rcv.get('z_30y') is not None else ""
            r_ratio = f"{rcv['ratio_2y_30y']:.3f}" if rcv.get('ratio_2y_30y') is not None else "N/A"
            zr      = f"z={rcv['z_ratio']:.1f}" if rcv.get('z_ratio') is not None else ""
            lines.append(f"> [RCV §0.9: RV 2y={rv2}({z2}) / 10y={rv10}({z10}) / 30y={rv30}({z30}) bp · 形态={rcv.get('character','N/A')} · sev={rcv.get('severity','N/A')} · tilt={rcv.get('tilt','N/A')} · 2y/30y={r_ratio}({zr})]")
            if rcv.get("degradation"):
                lines.append(f"> ⚠️ {rcv['degradation']}")
        elif rcv and rcv.get("abstain"):
            lines.append(f"> [RCV §0.9: ABSTAIN — {rcv.get('degradation','可得tenor<2')}]")
        # ── VTS+RCV interlock line ──
        lock_md = casc.get("vts_rcv_lock", {})
        if lock_md and lock_md.get("state", "N/A") != "N/A":
            lines.append(f"> [双探针互锁 §0.8+0.9: {lock_md.get('state','N/A')} — {lock_md.get('state_label','')}]")
        # ── 空行 ──
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

    # ====== C_RealYield_Nowcast ======
    if nowcast is not None:
        lines.extend(_format_nowcast_section(nowcast))
        lines.append("")

    # ====== 观察项 ======
    lines.append("## 观察项")
    lines.append("")
    if rate_path:
        lines.append(f"- {rate_path['display_str']}")
    else:
        lines.append("- 利率路径(代理): N/A(未提供)")
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
    if liq.get("reserves_t") is not None:
        lines.append(f"| Reserves | ${liq['reserves_t']:.2f}T | — |")
    # Yahoo vintage warning: VIX/CASC/VTS all depend on Yahoo, T>=2 is a confidence hit
    if stale_warnings is None:
        stale_warnings = []
    if vintages and vintages.get("yahoo_tn", 0) >= 2:
        yahoo_warning = (
            f"⚠️  Yahoo 数据滞后 {vintages['yahoo_tn']} 个交易日"
            f" ({vintages.get('yahoo_date','?')[-5:]})"
            f" — VIX/CASC/VTS/互锁结论基于过期数据，置信度打折；建议重跑 fetch_data.py"
        )
        stale_warnings.insert(0, yahoo_warning)
    # Stale warnings (frequency-aware)
    if stale_warnings:
        lines.append("")
        lines.append("## ⚠️ 数据完整性")
        lines.append("")
        for w in stale_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("---")
    lines.append(f"*ABCD v3.5.1 — mechanized mapping. v3.5.1 drawdown warning = not directional sell. Sources: FRED + Yahoo Finance.*")

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
    data_date_raw = last_date(hy_data) or date.today().isoformat()
    # Ensure data_date is never a weekend
    data_date = _clamp_weekday(date.fromisoformat(data_date_raw)).isoformat()
    run_date = date.today().isoformat()    # 文件命名用：报告实际生成日期

    # Compute vintages (FRED vs Yahoo) and stale warnings
    vintages = compute_vintages(raw)
    stale_warnings = check_staleness(raw)

    # Compute all regimes
    curve    = compute_curve_regime(raw)
    hy_stress = compute_hy_stress(raw)
    v35      = compute_v35_triggers(raw)
    fw       = compute_framework(raw)
    liq      = compute_liquidity(raw)
    rate_path = compute_rate_path_proxy(raw)
    abcd     = compute_abcd_signals(raw)

    # §0.7 CASC — 跨资产应力确认层 (在 regime 判定前作为降级闸)
    casc     = compute_casc(raw, v35, abcd)
    abcd     = apply_casc_gate(abcd, casc)
    pos      = compute_position(abcd, v35, casc=casc)
    prox     = compute_trigger_proximity(abcd, raw)
    chk      = compute_checklist(abcd, pos)

    # C_RealYield_Nowcast — 实际利率实时估算（独立于原有C端判定）
    nowcast  = compute_real_yield_nowcast(raw)

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
        md = format_markdown_report(curve, hy_stress, v35, fw, liq, abcd, pos, prox, chk, data_date,
                                     vintages=vintages, stale_warnings=stale_warnings, rate_path=rate_path,
                                     casc=casc, nowcast=nowcast)
        print(md)

        # Save daily report
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"daily_{run_date}.md"
        (REPORT_DIR / fname).write_text(md, encoding="utf-8")
        print(f"\n[Saved to report/{fname}]")
        # Also archive
        ym = run_date[:7]  # YYYY-MM
        arch_dir = ARCHIVE_DIR / ym
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / fname).write_text(md, encoding="utf-8")
        print(f"[Archived to daily_archive/{ym}/{fname}]")

        # Auto-generate risk dashboard (MD + PNG)
        import subprocess
        dash_script = Path(__file__).resolve().parent / "generate_risk_dashboard.py"
        subprocess.run([sys.executable, "-X", "utf8", str(dash_script), "--date", run_date],
                       capture_output=True, timeout=60)
        print(f"[Generated risk dashboard (MD + PNG)]")

        # Auto-generate risk evolution flowchart HTML -> daily_archive (legacy)
        flowchart_script = Path(__file__).resolve().parent / "generate_risk_flowchart.py"
        subprocess.run([sys.executable, "-X", "utf8", str(flowchart_script), "--date", run_date],
                       capture_output=True, timeout=30)
        print(f"[Generated risk flowchart -> daily_archive]")

        # ── New: Event-driven flowchart PNG (white-background) ──
        tools_dir = Path(__file__).resolve().parent / "tools"
        # Step A: Extract event_state from risk_dashboard MD
        extract_script = tools_dir / "extract_risk_events.py"
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(extract_script), "--date", run_date],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            print(f"[Extracted risk event_state]")
            # Step B: Generate white-background flowchart PNG
            png_script = tools_dir / "generate_flowchart_png.py"
            r2 = subprocess.run(
                [sys.executable, "-X", "utf8", str(png_script), "--date", run_date],
                capture_output=True, timeout=30,
            )
            if r2.returncode == 0:
                print(f"[Generated risk flowchart PNG]")
            else:
                print(f"[WARN] Flowchart PNG failed: {r2.stderr.decode(errors='replace')[:200]}")
        else:
            print(f"[WARN] Event extraction failed: {r.stderr.decode(errors='replace')[:200]}")

        return 0

    # --- Default: text report ---
    print(format_text_report(curve, hy_stress, v35, fw, liq, abcd, pos, prox, chk, data_date, rate_path=rate_path, casc=casc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
