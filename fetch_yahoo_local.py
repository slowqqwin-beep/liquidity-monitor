"""
Local Yahoo Finance Data Fetcher
=================================
Runs on your Windows machine (where yfinance works) and saves FXY/HYG/SPY
data to data/yahoo_series.json. Push to GitHub, and the CI pipeline will
use this as fallback when Yahoo blocks GitHub Actions IPs.

Usage:
    python v3.5/fetch_yahoo_local.py              # pull & save
    python v3.5/fetch_yahoo_local.py --push       # pull, save, commit & push
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent / "liquidity-dashboard"
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "yahoo_series.json"

TICKERS = ["FXY", "HYG", "SPY", "GLD", "^VIX", "^VIX3M", "^VIX9D", "^TNX"]
LOOKBACK_DAYS = 365 * 3  # 3 years


def fetch_ticker(ticker: str) -> list[dict]:
    """Pull daily close from Yahoo Finance."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"  [{ticker}] {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')} ...")
    try:
        df = yf.download(
            ticker, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=False,
        )
        if df.empty:
            print(f"  [{ticker}] WARN: empty result")
            return []
        # auto_adjust=False → use Adj Close column
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        import math
        rows = []
        for d, row in df.iterrows():
            v = float(row[price_col].iloc[0])
            if math.isnan(v):
                continue  # skip NaN rows (e.g. today's unsettled data)
            rows.append({"date": str(d.date()), "value": v})
        print(f"  [{ticker}] OK - {len(rows)} rows, last={rows[-1]['date']} @ {rows[-1]['value']:.2f}")
        return rows
    except Exception as e:
        print(f"  [{ticker}] FAIL: {e}")
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch Yahoo Finance data locally")
    parser.add_argument("--push", action="store_true", help="Commit & push to GitHub after fetch")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Fetching {TICKERS} from Yahoo Finance (local yfinance) ...")
    print(f"[INFO] LOOKBACK: {LOOKBACK_DAYS} days")

    result: dict[str, list[dict]] = {}
    for t in TICKERS:
        result[t] = fetch_ticker(t)

    # Save
    OUT_PATH.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    file_kb = OUT_PATH.stat().st_size / 1024
    print(f"\n[DONE] Saved {OUT_PATH} ({file_kb:.1f} KB)")

    total = sum(len(v) for v in result.values())
    if total == 0:
        print("[WARN] All Yahoo tickers returned 0 rows — check network/VPN")
        return 1

    if args.push:
        print("\n[INFO] Committing & pushing to GitHub ...")
        subprocess.run(
            ["git", "add", str(OUT_PATH)],
            cwd=str(ROOT), check=True,
        )
        today = datetime.now().strftime("%Y-%m-%d")
        subprocess.run(
            ["git", "commit", "-m", f"yahoo: local update {today} [FXY/HYG/SPY]"],
            cwd=str(ROOT), check=False,  # allow empty commit
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(ROOT), check=True,
        )
        print("[DONE] Pushed to GitHub.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
