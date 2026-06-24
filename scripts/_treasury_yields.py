#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared yfinance Treasury yield fetcher — no local CSV dependency.

Used by both sr3_repair_watch.py (KPIs + classification) and
build_sr3_watch_dashboard.py (2s10s chart).

Ticker mapping:
- ^TNX  → 10Y Treasury yield (CBOE index)
- ZT=F  → 2Y T-Note futures, yield ≈ 100 - price
- T10YIE → FRED CSV fallback (no real-time alternative)
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "treasury_yields_cache.json"


def fetch_t10yie() -> Optional[float]:
    """Fetch latest T10YIE from FRED web (no API key needed)."""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode()
        reader = csv.reader(io.StringIO(data))
        next(reader)  # skip header
        last_val = None
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                last_val = float(row[1])
        return round(last_val, 3) if last_val else None
    except Exception:
        return None


def fetch_latest_yields() -> Tuple[Optional[float], Optional[float]]:
    """Return (us10y_pct, us2y_pct) latest values from yfinance."""
    try:
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=5)
        tnx = yf.download("^TNX", start=start.strftime("%Y-%m-%d"),
                          end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        us10y = round(float(tnx["Close"].dropna().iloc[-1]), 2) if not tnx.empty else None
        zt = yf.download("ZT=F", start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        us2y = round(100.0 - float(zt["Close"].dropna().iloc[-1]), 2) if not zt.empty else None
        return us10y, us2y
    except Exception:
        return None, None


def fetch_history(days: int = 400) -> list:
    """Return list of {date, us10y, us2y, spread_bp} from yfinance.
    Cached to CACHE_PATH, refreshed when cache older than 6 hours.
    Falls back to local CSV if yfinance fails.
    """
    now = datetime.now()
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            cache_ts = datetime.fromisoformat(cache.get("fetched_at", "2000-01-01"))
            if (now - cache_ts).total_seconds() < 21600:  # 6h
                series = cache.get("series", [])
                return series[-days:] if len(series) > days else series
        except Exception:
            pass

    try:
        import yfinance as yf
        end = now
        # Fetch in chunks to avoid timeouts
        all_series = []
        chunk_days = 120
        for offset in range(0, days, chunk_days):
            chunk_end = end - timedelta(days=offset)
            chunk_start = chunk_end - timedelta(days=chunk_days + 10)
            tnx = yf.download("^TNX", start=chunk_start.strftime("%Y-%m-%d"),
                              end=chunk_end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
            zt = yf.download("ZT=F", start=chunk_start.strftime("%Y-%m-%d"),
                             end=chunk_end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
            if tnx.empty or zt.empty:
                continue
            tnx = tnx[["Close"]].rename(columns={"Close": "us10y"})
            zt = zt[["Close"]].rename(columns={"Close": "price"})
            merged = tnx.join(zt, how="inner")
            merged["us2y"] = round(100.0 - merged["price"], 2)
            merged["spread_bp"] = round((merged["us10y"] - merged["us2y"]) * 100, 1)
            for idx, row in merged.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                all_series.append({
                    "date": date_str,
                    "ten_y": round(float(row["us10y"]), 3),
                    "two_y": round(float(row["us2y"]), 3),
                    "spread_bp": round(float(row["spread_bp"]), 1),
                })

        if not all_series:
            return _fallback_csv()

        # Deduplicate and sort
        seen = {}
        for s in all_series:
            seen[s["date"]] = s
        series = [seen[k] for k in sorted(seen)]

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({
            "fetched_at": now.isoformat(),
            "series": series,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return series[-days:]
    except Exception:
        return _fallback_csv()


def _fallback_csv() -> list:
    """Try local CSV files as last resort."""
    candidates = [
        PROJECT_ROOT / "data" / "历史数据" / "TVC_US10Y, 1D.csv",
        PROJECT_ROOT / "TVC_US10Y, 1D.csv",
        PROJECT_ROOT / "2s10s.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            import csv
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if not rows or "time" not in rows[0]:
                continue
            # Detect columns
            cols = {"ten": "close", "two": None}
            for h in rows[0].keys():
                hl = h.lower().replace(" ", "")
                if "us02y" in hl or "us2y" in hl:
                    cols["two"] = h
            series = []
            for row in rows:
                d = row.get("time", "")[:10]
                try:
                    ten = float(row.get(cols["ten"], 0))
                except Exception:
                    continue
                try:
                    two = float(row[cols["two"]]) if cols["two"] else None
                except Exception:
                    two = None
                if two is not None:
                    spread = round((ten - two) * 100, 1)
                    series.append({"date": d, "ten_y": round(ten, 3), "two_y": round(two, 3), "spread_bp": spread})
            if series:
                return series
        except Exception:
            continue
    return []
