"""
Real Yield Spread 诊断层 (g-r Overlay)
Tier 1 diagnostic overlay — NOT a trigger, NOT in paper_trade_v3_5_clean.csv.

§0: This module reports "how wide/narrow real yield spread is relative to
     asset earnings yield". It does NOT produce buy/sell/reduce signals.

§5: CodeBuddy red-flag self-check:
     - Never threshold-ize RYS (no "if RYS < X%" triggers)
     - Never merge 2s10s with RYS into one composite score
     - Never fabricate growth data (insufficient → flag, don't fill)
     - Never write to paper_trade_v3_5_clean.csv
"""
import json, csv, pathlib, urllib.request, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "series.json"
OUT_CSV = ROOT / "data" / "real_yield_spread_diagnostic.csv"

# ── Portfolio tickers (user-defined, edit here) ──
PORTFOLIO = ["CRM", "SNOW", "MSFT", "DDOG", "OKTA"]
SPY_TICKER = "SPY"
QQQ_TICKER = "QQQ"


def fetch_pe(ticker: str) -> dict:
    """Fetch trailingPE / forwardPE / earningsGrowth from yfinance.
    Never fabricates missing data — missing = None."""
    result = {"trailingPE": None, "forwardPE": None,
              "earningsGrowth": None, "revenueGrowth": None, "error": None}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        result["trailingPE"] = info.get("trailingPE")
        result["forwardPE"] = info.get("forwardPE")
        result["earningsGrowth"] = info.get("earningsGrowth")
        result["revenueGrowth"] = info.get("revenueGrowth")
    except Exception as e:
        result["error"] = str(e)[:100]
    return result


def get_dfii10() -> float:
    """Read latest DFII10 from series.json."""
    data = json.loads(SERIES.read_text("utf-8"))
    items = data.get("DFII10", [])
    return items[-1]["value"] if items else None


def get_weights() -> dict:
    """Read portfolio weights from existing maintenance flow.
    Falls back to equal weight if no source available."""
    # Placeholder — integrate with actual weight source
    n = len(PORTFOLIO)
    return {t: 1.0 / n for t in PORTFOLIO}


def run():
    today = datetime.now().strftime("%Y-%m-%d")
    dfii10 = get_dfii10()

    # ── Market-level PE ──
    spy_pe = fetch_pe(SPY_TICKER)
    qqq_pe = fetch_pe(QQQ_TICKER)

    # ── Portfolio PE ──
    weights = get_weights()
    portfolio_trailing = {}
    portfolio_forward = {}
    portfolio_growth = {}
    growth_errors = 0

    for ticker in PORTFOLIO:
        pe_data = fetch_pe(ticker)
        portfolio_trailing[ticker] = pe_data["trailingPE"]
        portfolio_forward[ticker] = pe_data["forwardPE"]
        eg = pe_data.get("earningsGrowth")
        portfolio_growth[ticker] = eg
        if eg is None and pe_data.get("error"):
            growth_errors += 1

    # ── Compute RYS ──
    # RYS_market = EarningsYield − DFII10, where EarningsYield = 1/trailingPE
    rys_spy = (1.0 / spy_pe["trailingPE"] * 100 - dfii10) if spy_pe["trailingPE"] else None
    rys_qqq = (1.0 / qqq_pe["trailingPE"] * 100 - dfii10) if qqq_pe["trailingPE"] else None

    # RYS_portfolio = Σ(weight_i × (1/PE_i)) − DFII10
    portfolio_ey = 0.0
    portfolio_ok = True
    for t, w in weights.items():
        pe = portfolio_trailing.get(t)
        if pe:
            portfolio_ey += w * (1.0 / pe * 100)
        else:
            portfolio_ok = False
    rys_portfolio = portfolio_ey - dfii10 if portfolio_ok and dfii10 else None

    # Growth-adjusted (never fabricate — missing = insufficient)
    rys_growth_market = None
    rys_growth_portfolio = None
    growth_market_ok = spy_pe.get("earningsGrowth") is not None
    if growth_market_ok and dfii10:
        rys_growth_market = spy_pe["earningsGrowth"] * 100 - dfii10

    # ── Data quality ──
    missing_growth = growth_errors > 0 or spy_pe.get("earningsGrowth") is None
    if rys_portfolio is None:
        quality = "insufficient"
    elif missing_growth:
        quality = "partial"
    else:
        quality = "ok"

    # ── 20d change (read previous row from CSV if exists) ──
    rys_20d_spy, rys_20d_portfolio = None, None
    if OUT_CSV.exists():
        try:
            with open(OUT_CSV, "r", encoding="utf-8") as f:
                prev_rows = list(csv.DictReader(f))
            if len(prev_rows) >= 20:
                base = prev_rows[-20]
                if rys_spy is not None and base.get("RYS_market_SPY"):
                    rys_20d_spy = round(rys_spy - float(base["RYS_market_SPY"]), 2)
                if rys_portfolio is not None and base.get("RYS_portfolio"):
                    rys_20d_portfolio = round(rys_portfolio - float(base["RYS_portfolio"]), 2)
        except Exception:
            pass

    # ── Build row (only these fields per §3) ──
    row = {
        "date": today,
        "DFII10": round(dfii10, 4) if dfii10 else None,
        "RYS_market_SPY": round(rys_spy, 2) if rys_spy else None,
        "RYS_market_QQQ": round(rys_qqq, 2) if rys_qqq else None,
        "RYS_portfolio": round(rys_portfolio, 2) if rys_portfolio else None,
        "RYS_growth_market": round(rys_growth_market, 2) if rys_growth_market else None,
        "RYS_growth_portfolio": round(rys_growth_portfolio, 2) if rys_growth_portfolio else None,
        "RYS_market_20d_change": rys_20d_spy,
        "RYS_portfolio_20d_change": rys_20d_portfolio,
        "data_quality_flag": quality,
        "notes": f"growth errors: {growth_errors}/{len(PORTFOLIO)+2}" if missing_growth else "",
    }

    # ── Append CSV ──
    file_exists = OUT_CSV.exists()
    with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            w.writeheader()
        w.writerow(row)

    # ── Print diagnostic (no "triggered" language) ──
    print(f"[RYS Diagnostic] {today} | DFII10={row['DFII10']}% | quality={quality}")
    print(f"  RYS Market SPY: {row['RYS_market_SPY']}% | QQQ: {row['RYS_market_QQQ']}%")
    print(f"  RYS Portfolio: {row['RYS_portfolio']}%")
    print(f"  RYS Growth Market: {row['RYS_growth_market']}")
    print(f"  20d change SPY: {row['RYS_market_20d_change']}")
    print(f"  Saved to {OUT_CSV}")

    return row


if __name__ == "__main__":
    run()
