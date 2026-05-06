"""
Liquidity Dashboard Data Fetcher
=================================

Pulls data from FRED, CoinGecko, and Yahoo Finance to populate the dashboard.
Designed to run via GitHub Actions on a daily schedule.

Required environment variables:
    FRED_API_KEY    - Free key from https://fred.stlouisfed.org/docs/api/api_key.html

Optional:
    LOOKBACK_YEARS  - How many years of history to fetch (default 3)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
LOOKBACK_YEARS = int(os.environ.get("LOOKBACK_YEARS", "3"))

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = (datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")

# All FRED series we need, organized by the 3-layer framework.
# Each entry: (fred_id, label, layer, unit, description)
FRED_SERIES: list[dict[str, str]] = [
    # ---------- Layer 1: System / Plumbing Liquidity ----------
    {"id": "SOFR", "label": "SOFR", "layer": "L1", "unit": "%", "desc": "Secured Overnight Financing Rate"},
    {"id": "IORB", "label": "IORB", "layer": "L1", "unit": "%", "desc": "Interest On Reserve Balances"},
    {"id": "EFFR", "label": "EFFR", "layer": "L1", "unit": "%", "desc": "Effective Federal Funds Rate"},
    {"id": "DFEDTARU", "label": "Fed Funds Target (Upper)", "layer": "L1", "unit": "%", "desc": "Fed funds target upper bound"},
    {"id": "DFEDTARL", "label": "Fed Funds Target (Lower)", "layer": "L1", "unit": "%", "desc": "Fed funds target lower bound"},
    {"id": "RRPONTSYD", "label": "ON RRP Balance", "layer": "L1", "unit": "$B", "desc": "Overnight Reverse Repo balance ($B)"},
    {"id": "WRESBAL", "label": "Reserve Balances", "layer": "L1", "unit": "$B", "desc": "Reserves with Fed Reserve Banks ($B)"},
    {"id": "WTREGEN", "label": "Treasury General Account", "layer": "L1", "unit": "$B", "desc": "TGA balance at Fed ($B)"},
    {"id": "WALCL", "label": "Fed Total Assets", "layer": "L1", "unit": "$M", "desc": "Total Fed balance sheet"},
    # ---------- Layer 2: Risk Appetite Liquidity ----------
    {"id": "BAMLH0A0HYM2", "label": "HY OAS", "layer": "L2", "unit": "%", "desc": "ICE BofA US High Yield OAS"},
    {"id": "BAMLC0A0CM", "label": "IG OAS", "layer": "L2", "unit": "%", "desc": "ICE BofA US Corp OAS"},
    {"id": "BAMLEMCBPIOAS", "label": "EM Corp OAS", "layer": "L2", "unit": "%", "desc": "ICE BofA EM Corporate OAS"},
    {"id": "VIXCLS", "label": "VIX", "layer": "L2", "unit": "", "desc": "CBOE Volatility Index"},
    {"id": "TEDRATE", "label": "TED Spread (legacy)", "layer": "L2", "unit": "%", "desc": "Discontinued but historical reference"},
    # ---------- Layer 3: Framework / Sovereign-Debasement Signals ----------
    {"id": "DGS2", "label": "2Y Treasury", "layer": "L3", "unit": "%", "desc": "2-Year Treasury constant maturity"},
    {"id": "DGS5", "label": "5Y Treasury", "layer": "L3", "unit": "%", "desc": "5-Year Treasury"},
    {"id": "DGS10", "label": "10Y Treasury", "layer": "L3", "unit": "%", "desc": "10-Year Treasury"},
    {"id": "DGS30", "label": "30Y Treasury", "layer": "L3", "unit": "%", "desc": "30-Year Treasury"},
    {"id": "DFII10", "label": "10Y TIPS Yield", "layer": "L3", "unit": "%", "desc": "10-Year inflation-indexed (real yield)"},
    {"id": "T10YIE", "label": "10Y Breakeven", "layer": "L3", "unit": "%", "desc": "10Y breakeven inflation"},
    {"id": "T5YIFR", "label": "5Y5Y Forward Inflation", "layer": "L3", "unit": "%", "desc": "Cleanest long-term inflation expectation"},
    {"id": "THREEFYTP10", "label": "10Y Term Premium (ACM)", "layer": "L3", "unit": "%", "desc": "NY Fed ACM term premium estimate"},
    {"id": "GOLDAMGBD228NLBM", "label": "Gold (LBMA AM)", "layer": "L3", "unit": "$/oz", "desc": "London Bullion Market AM Fix"},
    {"id": "MORTGAGE30US", "label": "30Y Mortgage", "layer": "L3", "unit": "%", "desc": "Freddie Mac 30Y fixed mortgage"},
    {"id": "DTWEXBGS", "label": "Broad Dollar Index", "layer": "L3", "unit": "Idx", "desc": "Trade-weighted broad dollar"},
]

# Computed series (derived from the above)
COMPUTED_SERIES = [
    {"id": "GOLD_10Y_RATIO", "label": "Gold / 10Y Yield", "layer": "L3", "unit": "$/% ", "desc": "Gold price divided by 10Y yield - framework switch indicator"},
    {"id": "SOFR_IORB", "label": "SOFR – IORB", "layer": "L1", "unit": "bp", "desc": "Plumbing stress: positive = banks lending into repo"},
    {"id": "EFFR_IORB", "label": "EFFR – IORB", "layer": "L1", "unit": "bp", "desc": "Reserve scarcity: positive = reserves scarce"},
    {"id": "MORTGAGE_SPREAD", "label": "30Y Mortgage – 10Y", "layer": "L3", "unit": "bp", "desc": "Real-economy credit transmission"},
    {"id": "HY_IG_RATIO", "label": "HY / IG Spread Ratio", "layer": "L2", "unit": "x", "desc": "Risk-tier divergence"},
]


# ------------------------------------------------------------------
# FRED helpers
# ------------------------------------------------------------------

def fetch_fred(series_id: str, retries: int = 3) -> list[dict[str, Any]]:
    """Fetch a single FRED series. Returns list of {date, value} dicts."""
    if not FRED_API_KEY:
        print(f"[WARN] No FRED_API_KEY set; skipping {series_id}", file=sys.stderr)
        return []

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": START_DATE,
    }

    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            data = []
            for o in obs:
                v = o.get("value", ".")
                if v in (".", "", None):
                    continue
                try:
                    data.append({"date": o["date"], "value": float(v)})
                except ValueError:
                    continue
            return data
        except Exception as e:
            print(f"[WARN] FRED fetch failed for {series_id} (attempt {attempt+1}): {e}", file=sys.stderr)
            time.sleep(2 ** attempt)

    return []


# ------------------------------------------------------------------
# CoinGecko helpers (Layer 3 - non-sovereign liquidity)
# ------------------------------------------------------------------

def fetch_coingecko_market_cap(coin_id: str, days: int) -> list[dict[str, Any]]:
    """Fetch daily market cap history for a coin. Free tier, no key needed."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": min(days, 365), "interval": "daily"}

    try:
        r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "liquidity-dashboard/1.0"})
        r.raise_for_status()
        caps = r.json().get("market_caps", [])
        return [
            {"date": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"), "value": v / 1e9}
            for ts, v in caps
        ]
    except Exception as e:
        print(f"[WARN] CoinGecko fetch failed for {coin_id}: {e}", file=sys.stderr)
        return []


def fetch_stablecoin_aggregate() -> list[dict[str, Any]]:
    """Sum of major stablecoin market caps in $B - the 'flight from sovereign credit' gauge."""
    days = min(LOOKBACK_YEARS * 365, 365)  # CoinGecko free tier limit
    coins = ["tether", "usd-coin", "dai", "first-digital-usd"]
    cap_by_date: dict[str, float] = {}

    for c in coins:
        data = fetch_coingecko_market_cap(c, days=days)
        for row in data:
            cap_by_date[row["date"]] = cap_by_date.get(row["date"], 0.0) + row["value"]
        time.sleep(2)  # be nice to free API

    return [{"date": d, "value": v} for d, v in sorted(cap_by_date.items())]


def fetch_btc_price() -> list[dict[str, Any]]:
    """Bitcoin price in USD - alternative monetary signal."""
    days = min(LOOKBACK_YEARS * 365, 365)
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    try:
        r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "liquidity-dashboard/1.0"})
        r.raise_for_status()
        prices = r.json().get("prices", [])
        return [
            {"date": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"), "value": v}
            for ts, v in prices
        ]
    except Exception as e:
        print(f"[WARN] BTC fetch failed: {e}", file=sys.stderr)
        return []


# ------------------------------------------------------------------
# MOVE index - try Yahoo via stooq fallback
# ------------------------------------------------------------------

def fetch_stooq_csv(symbol: str, label: str) -> list[dict[str, Any]]:
    """Generic stooq CSV fetcher. No API key required."""
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")
        out = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            d, close = parts[0], parts[4]
            if d < cutoff:
                continue
            try:
                out.append({"date": d, "value": float(close)})
            except ValueError:
                continue
        return out
    except Exception as e:
        print(f"[WARN] {label} fetch from stooq failed: {e}", file=sys.stderr)
        return []


def fetch_move_index() -> list[dict[str, Any]]:
    return fetch_stooq_csv("^move", "MOVE")


def fetch_gold_stooq() -> list[dict[str, Any]]:
    """Gold via Yahoo Finance GC=F (Gold Futures continuous).
    Function name kept for backward compatibility — actually fetches from Yahoo now."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
    params = {"interval": "1d", "range": "5y"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_YEARS)).strftime("%Y-%m-%d")
        out = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if d < cutoff:
                continue
            out.append({"date": d, "value": float(close)})
        print(f"[INFO] Gold from Yahoo: {len(out)} obs")
        return out
    except Exception as e:
        print(f"[WARN] Yahoo gold fetch failed: {e}", file=sys.stderr)
        return []

def to_dict(series: list[dict[str, Any]]) -> dict[str, float]:
    return {row["date"]: row["value"] for row in series}


def compute_derived(all_series: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Compute the cross-series indicators."""
    derived: dict[str, list[dict[str, Any]]] = {}

    # SOFR - IORB (in basis points)
    sofr = to_dict(all_series.get("SOFR", []))
    iorb = to_dict(all_series.get("IORB", []))
    derived["SOFR_IORB"] = [
        {"date": d, "value": (sofr[d] - iorb[d]) * 100}
        for d in sorted(sofr.keys() & iorb.keys())
    ]

    # EFFR - IORB
    effr = to_dict(all_series.get("EFFR", []))
    derived["EFFR_IORB"] = [
        {"date": d, "value": (effr[d] - iorb[d]) * 100}
        for d in sorted(effr.keys() & iorb.keys())
    ]

    # Mortgage spread
    mort = to_dict(all_series.get("MORTGAGE30US", []))
    dgs10 = to_dict(all_series.get("DGS10", []))
    derived["MORTGAGE_SPREAD"] = [
        {"date": d, "value": (mort[d] - dgs10[d]) * 100}
        for d in sorted(mort.keys() & dgs10.keys())
    ]

    # HY / IG spread ratio
    hy = to_dict(all_series.get("BAMLH0A0HYM2", []))
    ig = to_dict(all_series.get("BAMLC0A0CM", []))
    derived["HY_IG_RATIO"] = [
        {"date": d, "value": hy[d] / ig[d]}
        for d in sorted(hy.keys() & ig.keys())
        if ig[d] > 0
    ]

    # Gold / 10Y yield ratio - the framework switch indicator
    gold = to_dict(all_series.get("GOLDAMGBD228NLBM", []))
    derived["GOLD_10Y_RATIO"] = [
        {"date": d, "value": gold[d] / dgs10[d]}
        for d in sorted(gold.keys() & dgs10.keys())
        if dgs10[d] > 0
    ]

    return derived


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> int:
    print(f"[INFO] Fetching data since {START_DATE}")
    all_series: dict[str, list[dict[str, Any]]] = {}

    # FRED data
    for entry in FRED_SERIES:
        sid = entry["id"]
        print(f"[INFO] FRED: {sid}")
        data = fetch_fred(sid)
        all_series[sid] = data
        time.sleep(0.3)  # FRED rate limit is generous but be polite

    # Crypto
    print("[INFO] Stablecoin aggregate (CoinGecko)")
    all_series["STABLECOIN_MCAP_B"] = fetch_stablecoin_aggregate()

    print("[INFO] BTC price (CoinGecko)")
    all_series["BTC_USD"] = fetch_btc_price()

    # MOVE index
    print("[INFO] MOVE index (stooq)")
    all_series["MOVE"] = fetch_move_index()

    print("[INFO] Gold (stooq)")
    all_series["GOLDAMGBD228NLBM"] = fetch_gold_stooq()

    # Derived
    print("[INFO] Computing derived series")
    all_series.update(compute_derived(all_series))

    # Build metadata
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_years": LOOKBACK_YEARS,
        "series": [
            {**entry, "n_obs": len(all_series.get(entry["id"], []))}
            for entry in FRED_SERIES
        ] + [
            {"id": "STABLECOIN_MCAP_B", "label": "Stablecoin Market Cap (USDT+USDC+DAI+FDUSD)",
             "layer": "L3", "unit": "$B", "desc": "Aggregate non-sovereign dollar liquidity",
             "n_obs": len(all_series.get("STABLECOIN_MCAP_B", []))},
            {"id": "BTC_USD", "label": "Bitcoin", "layer": "L3", "unit": "$",
             "desc": "Alternative monetary asset", "n_obs": len(all_series.get("BTC_USD", []))},
            {"id": "MOVE", "label": "MOVE Index", "layer": "L2", "unit": "",
             "desc": "Bond market implied volatility", "n_obs": len(all_series.get("MOVE", []))},
        ] + COMPUTED_SERIES,
    }
    # Add n_obs for computed
    for entry in metadata["series"]:
        if entry.get("n_obs") is None:
            entry["n_obs"] = len(all_series.get(entry["id"], []))

    # Write outputs
    series_path = OUT_DIR / "series.json"
    meta_path = OUT_DIR / "metadata.json"

    with series_path.open("w") as f:
        json.dump(all_series, f, separators=(",", ":"))
    with meta_path.open("w") as f:
        json.dump(metadata, f, indent=2)

    total_obs = sum(len(v) for v in all_series.values())
    print(f"[DONE] {len(all_series)} series, {total_obs} observations")
    print(f"[DONE] Wrote {series_path} ({series_path.stat().st_size / 1024:.1f} KB)")
    print(f"[DONE] Wrote {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
