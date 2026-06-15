"""
Generate plausible synthetic data for the dashboard's first deploy.

This is replaced by real data once the GitHub Actions workflow runs against FRED.
The synthetic data uses random walks calibrated to realistic recent levels,
not historical accuracy — purely so the dashboard renders something on first paint.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

DAYS = 365 * 3
END = datetime(2026, 5, 5, tzinfo=timezone.utc)
DATES = [(END - timedelta(days=DAYS - i)).strftime("%Y-%m-%d") for i in range(DAYS + 1)]
BUSINESS_DATES = [d for d in DATES if datetime.strptime(d, "%Y-%m-%d").weekday() < 5]


def random_walk(start: float, drift: float, vol: float, n: int, floor=None, ceil=None):
    """Simple random walk with mean reversion bias."""
    out = [start]
    for _ in range(n - 1):
        step = drift + random.gauss(0, vol)
        nxt = out[-1] + step
        if floor is not None:
            nxt = max(floor, nxt)
        if ceil is not None:
            nxt = min(ceil, nxt)
        out.append(nxt)
    return out


def step_series(steps: list[tuple[str, float]], dates: list[str]) -> list[dict]:
    """Build a step function from (date, value) anchors."""
    out = []
    si = 0
    for d in dates:
        while si + 1 < len(steps) and dates.index(d) >= dates.index(steps[si + 1][0]):
            si += 1
        out.append({"date": d, "value": steps[si][1]})
    return out


def to_series(values: list[float], dates: list[str]) -> list[dict]:
    return [{"date": d, "value": round(v, 4)} for d, v in zip(dates, values)]


def make_synthetic() -> dict:
    n = len(BUSINESS_DATES)

    # ---------------------------------------------------------
    # Layer 1 — Plumbing
    # ---------------------------------------------------------

    # Fed funds target curve - rough recent path (5.50 → step down to ~4.00)
    rate_path = []
    target_upper_steps = []
    for i, d in enumerate(BUSINESS_DATES):
        dt = datetime.strptime(d, "%Y-%m-%d")
        # Hike cycle 2023, plateau, cuts late 2024+
        if dt < datetime(2023, 8, 1):
            r = 5.0 + (dt - datetime(2023, 1, 1)).days / 365 * 0.5
        elif dt < datetime(2024, 9, 1):
            r = 5.50
        elif dt < datetime(2025, 6, 1):
            # Gradual cuts
            r = 5.50 - (dt - datetime(2024, 9, 1)).days / 270 * 1.25
        else:
            r = 4.25 - (dt - datetime(2025, 6, 1)).days / 365 * 0.25
        target_upper_steps.append(min(5.50, max(3.75, r)))
        rate_path.append(r)

    sofr_vals = [r - 0.07 + random.gauss(0, 0.005) for r in rate_path]
    iorb_vals = [r - 0.10 for r in target_upper_steps]
    effr_vals = [r - 0.08 + random.gauss(0, 0.003) for r in rate_path]
    target_lower_vals = [r - 0.25 for r in target_upper_steps]

    # RRP balance — drained from $2.5T to ~$150B
    rrp_vals = []
    for i, d in enumerate(BUSINESS_DATES):
        dt = datetime.strptime(d, "%Y-%m-%d")
        if dt < datetime(2023, 6, 1):
            base = 2300 - (dt - datetime(2023, 1, 1)).days * 0.5
        elif dt < datetime(2024, 6, 1):
            base = 2000 - (dt - datetime(2023, 6, 1)).days * 4.5
        else:
            base = 200 + 50 * math.sin(i / 30)
        rrp_vals.append(max(50, base + random.gauss(0, 30)))

    # Reserve balances — bounced around $3.0–3.5T
    reserves_vals = random_walk(3300, -0.2, 25, n, floor=2700, ceil=3700)

    # TGA — volatile, $300–800B
    tga_vals = random_walk(550, 0, 15, n, floor=200, ceil=900)

    # Fed total assets - declining QT
    walcl_vals = random_walk(7800000, -800, 5000, n, floor=6600000, ceil=8200000)

    # ---------------------------------------------------------
    # Layer 2 — Risk appetite
    # ---------------------------------------------------------

    # HY OAS - tightened from ~5% to ~2.7%
    hy_vals = []
    for i in range(n):
        prog = i / n
        base = 5.0 - prog * 2.3
        hy_vals.append(max(2.5, base + random.gauss(0, 0.15)))

    # IG OAS - tightened from ~1.5% to ~0.8%
    ig_vals = []
    for i in range(n):
        prog = i / n
        base = 1.55 - prog * 0.75
        ig_vals.append(max(0.7, base + random.gauss(0, 0.04)))

    # EM Corp OAS
    em_vals = [hy + 0.5 + random.gauss(0, 0.1) for hy in hy_vals]

    # MOVE - vol spikes
    move_vals = random_walk(110, -0.05, 4, n, floor=70, ceil=180)

    # VIX
    vix_vals = random_walk(17, 0, 1.2, n, floor=11, ceil=40)

    # ---------------------------------------------------------
    # Layer 3 — Framework
    # ---------------------------------------------------------

    # 10Y Treasury - rangebound 3.5-5.0
    dgs10_vals = []
    cur = 3.85
    for i in range(n):
        cur += random.gauss(0.0, 0.04)
        cur = max(3.5, min(5.0, cur))
        dgs10_vals.append(cur)

    # 2Y, 5Y, 30Y constructed relative to 10Y
    dgs2_vals = [r + 0.7 - i / n * 1.5 for i, r in enumerate(dgs10_vals)]
    dgs5_vals = [r + 0.2 - i / n * 0.5 for i, r in enumerate(dgs10_vals)]
    dgs30_vals = [r + 0.1 + i / n * 0.4 for i, r in enumerate(dgs10_vals)]

    # 10Y TIPS - tracks 10Y minus breakeven
    breakeven_vals = random_walk(2.35, 0, 0.02, n, floor=2.0, ceil=2.7)
    tips_vals = [d - b for d, b in zip(dgs10_vals, breakeven_vals)]

    # 5Y5Y forward inflation - more stable
    t5yifr_vals = random_walk(2.30, 0, 0.015, n, floor=2.05, ceil=2.55)

    # Term premium (ACM) - turned positive 2022, climbing
    tp_vals = []
    for i in range(n):
        prog = i / n
        base = -0.30 + prog * 0.85
        tp_vals.append(base + random.gauss(0, 0.05))

    # Gold - secular bull from $1900 to $3400
    gold_vals = []
    cur = 1920
    for i in range(n):
        prog = i / n
        drift = 1.4 + prog * 0.5
        cur += drift + random.gauss(0, 12)
        cur = max(1850, cur)
        gold_vals.append(cur)

    # Mortgage - tracks 10Y + ~200bp spread
    mortgage_vals = [d + 1.85 + random.gauss(0, 0.05) for d in dgs10_vals]

    # Dollar index
    dxy_vals = random_walk(105, 0, 0.3, n, floor=98, ceil=115)

    # BTC - very volatile, secular up
    btc_vals = []
    cur = 22000
    for i in range(n):
        prog = i / n
        drift = 35 + prog * 60
        cur *= 1 + (drift / cur) + random.gauss(0, 0.025)
        cur = max(15000, cur)
        btc_vals.append(cur)

    # Stablecoin market cap $B - 130 → 270
    stable_vals = []
    cur = 130
    for i in range(n):
        prog = i / n
        if prog < 0.15:
            drift = -0.05  # 2023 contraction
        else:
            drift = 0.3
        cur += drift + random.gauss(0, 0.4)
        cur = max(120, cur)
        stable_vals.append(cur)

    # ---------------------------------------------------------
    # Compute derived
    # ---------------------------------------------------------
    sofr_iorb = [(s - i) * 100 for s, i in zip(sofr_vals, iorb_vals)]
    effr_iorb = [(e - i) * 100 for e, i in zip(effr_vals, iorb_vals)]
    mortgage_spread = [(m - d) * 100 for m, d in zip(mortgage_vals, dgs10_vals)]
    hy_ig_ratio = [h / i for h, i in zip(hy_vals, ig_vals)]
    gold_10y = [g / d for g, d in zip(gold_vals, dgs10_vals)]

    # ---------------------------------------------------------
    # Pack
    # ---------------------------------------------------------
    return {
        # L1
        "SOFR": to_series(sofr_vals, BUSINESS_DATES),
        "IORB": to_series(iorb_vals, BUSINESS_DATES),
        "EFFR": to_series(effr_vals, BUSINESS_DATES),
        "DFEDTARU": to_series(target_upper_steps, BUSINESS_DATES),
        "DFEDTARL": to_series(target_lower_vals, BUSINESS_DATES),
        "RRPONTSYD": to_series(rrp_vals, BUSINESS_DATES),
        "WRESBAL": to_series(reserves_vals, BUSINESS_DATES),
        "WTREGEN": to_series(tga_vals, BUSINESS_DATES),
        "WALCL": to_series(walcl_vals, BUSINESS_DATES),
        # L2
        "BAMLH0A0HYM2": to_series(hy_vals, BUSINESS_DATES),
        "BAMLC0A0CM": to_series(ig_vals, BUSINESS_DATES),
        "BAMLEMCBPIOAS": to_series(em_vals, BUSINESS_DATES),
        "VIXCLS": to_series(vix_vals, BUSINESS_DATES),
        "MOVE": to_series(move_vals, BUSINESS_DATES),
        # L3
        "DGS2": to_series(dgs2_vals, BUSINESS_DATES),
        "DGS5": to_series(dgs5_vals, BUSINESS_DATES),
        "DGS10": to_series(dgs10_vals, BUSINESS_DATES),
        "DGS30": to_series(dgs30_vals, BUSINESS_DATES),
        "DFII10": to_series(tips_vals, BUSINESS_DATES),
        "T10YIE": to_series(breakeven_vals, BUSINESS_DATES),
        "T5YIFR": to_series(t5yifr_vals, BUSINESS_DATES),
        "THREEFYTP10": to_series(tp_vals, BUSINESS_DATES),
        "GOLDAMGBD228NLBM": to_series(gold_vals, BUSINESS_DATES),
        "MORTGAGE30US": to_series(mortgage_vals, BUSINESS_DATES),
        "DTWEXBGS": to_series(dxy_vals, BUSINESS_DATES),
        "STABLECOIN_MCAP_B": to_series(stable_vals, BUSINESS_DATES),
        "BTC_USD": to_series(btc_vals, BUSINESS_DATES),
        # Derived
        "SOFR_IORB": to_series(sofr_iorb, BUSINESS_DATES),
        "EFFR_IORB": to_series(effr_iorb, BUSINESS_DATES),
        "MORTGAGE_SPREAD": to_series(mortgage_spread, BUSINESS_DATES),
        "HY_IG_RATIO": to_series(hy_ig_ratio, BUSINESS_DATES),
        "GOLD_10Y_RATIO": to_series(gold_10y, BUSINESS_DATES),
    }


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)

    series = make_synthetic()

    series_path = out_dir / "series.json"
    with series_path.open("w") as f:
        json.dump(series, f, separators=(",", ":"))

    metadata = {
        "generated_at": END.isoformat(),
        "lookback_years": 3,
        "is_demo": True,
        "note": "Synthetic seed data. Real data populated after first GitHub Actions run.",
        "series": [
            {"id": k, "n_obs": len(v), "label": k}
            for k, v in sorted(series.items())
        ],
    }
    with (out_dir / "metadata.json").open("w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Wrote {len(series)} series, {series_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
